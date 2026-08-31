"""/reports — 위험 보고 (M-08·M-08b). 202 즉시 → jobs 큐. [새봄]

M-08b ①: 접수는 LLM 비의존 결정론 경로 — 원문 무조건 적재 + 202 + submitted.
로컬 LLM(ollama)이 정지해 있어도 신고가 소실되지 않는다. 요약·severity 는
workers/job_runner.py 가 비동기로 채운다.

M-08b ④ 계약:
  요청 {original_text, lang, source?='text'} → 응답 202 {id, status, created_at}
  - source 집합은 001 CHECK('voice'|'text')가 정본. 'voice' 는 audio 없이 성립하지 않아
    현재 501(V5 STT 도입 시 해제).
  - 테넌트·reporter 는 인증 컨텍스트에서 서버가 도출한다. 요청 본문에 오면 **400 거부**
    (무시 아님 — 위조 방지, M-04 정합). 허용 필드 화이트리스트 밖은 전부 거부.

역할 분기 (M-28·M-22):
- API_ROLE=edge: 릴레이 큐에 적재 → core 회신 대기 → 원 응답 완결. edge 는 DB 자격이 없다.
- API_ROLE=core: 저장소 직접 호출. core 폴러도 같은 함수를 쓰며 HTTP 재귀는 없다.
"""

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.routers.auth import optional_identity, require_worker
from app.services import risk_reports
from app.services.relay import queue
from app.services.system_service import role

router = APIRouter(prefix="/reports", tags=["reports"])

PATH = "/api/v1/reports"
DETAIL_PATH = "/api/v1/reports/{report_id}"          # M-28c ① 릴레이 경로
CONFIRM_PATH = "/api/v1/reports/{report_id}/confirm"

# M-08b ④ 허용 필드 화이트리스트 — 이 밖의 키(tenant/tenant_slug/worker_id/reporter 등)는 400
ALLOWED_FIELDS = frozenset({"original_text", "lang", "source"})


class ReportRequest(BaseModel):
    original_text: str = Field(min_length=1)
    lang: str | None = None
    source: Literal["voice", "text"] = "text"  # 001 CHECK 집합이 정본


class ConfirmRequest(BaseModel):
    result: Literal["confirmed", "corrected"]
    corrected_text: str | None = None


def _reject_unknown_fields(raw: object) -> None:
    if not isinstance(raw, dict):
        return
    unknown = sorted(set(raw) - ALLOWED_FIELDS)
    if unknown:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "forbidden_fields",
                "message": (
                    "테넌트·보고자 식별자는 서버가 인증 컨텍스트에서 도출합니다 — "
                    "요청 본문 수신 금지 (M-08b ④)"
                ),
                "fields": unknown,
                "allowed": sorted(ALLOWED_FIELDS),
            },
        )


@router.post("", status_code=202)
async def create_report(
    body: ReportRequest,
    request: Request,
    identity: dict | None = Depends(optional_identity),
) -> JSONResponse:
    _reject_unknown_fields(await request.json())

    if body.source == risk_reports.SOURCE_VOICE:
        raise HTTPException(
            status_code=501,
            detail={
                "error": "voice_intake_not_available",
                "message": "음성 접수는 STT(V5) 도입 후 해제됩니다 — audio 없는 voice 접수는 성립하지 않습니다.",
            },
        )

    if role() == "edge":
        item = queue.enqueue("POST", PATH, body.model_dump(), identity)
        relayed = await queue.wait_for_response(item)
        return JSONResponse(status_code=relayed["status_code"], content=relayed["body"])

    # 원문 적재 + 요약 잡 enqueue + report_submitted 이벤트를 한 트랜잭션으로. LLM 호출 0.
    result = await asyncio.to_thread(
        risk_reports.submit_text_report,
        body.original_text, body.lang, body.source, (identity or {}).get("wid"),
    )
    return JSONResponse(status_code=202, content=result)


@router.get("/{report_id}")
async def get_report(
    report_id: int, identity: dict | None = Depends(optional_identity)
) -> JSONResponse:
    """근로자 상태 조회 — 5필드 한정. events[]·original_text 미포함.

    본인 조회는 original_viewed 감사 비대상(총괄 확정).
    M-28c ①②: edge 는 DB 자격이 없으므로 릴레이 경유(GET 은 body 없음 → 빈 dict).
    """
    if role() == "edge":
        item = queue.enqueue("GET", DETAIL_PATH.format(report_id=report_id), {}, identity)
        relayed = await queue.wait_for_response(item)
        return JSONResponse(status_code=relayed["status_code"], content=relayed["body"])

    try:
        result = await asyncio.to_thread(risk_reports.get_report_public, report_id)
    except risk_reports.ReportNotFound:
        raise HTTPException(status_code=404, detail="report not found") from None
    return JSONResponse(status_code=200, content=result)


@router.post("/{report_id}/confirm")
async def confirm_report(
    report_id: int,
    body: ConfirmRequest,
    request: Request,
    claims: dict = Depends(require_worker),
) -> JSONResponse:
    """M-08c 보고자 확인 루프 — 비차단. actor = worker:<wid>(M-28b identity 소비).

    인증 필수(M-37) — 헤더 부재·위조·만료는 require_worker 가 401 로 끊는다.
    "비차단"은 접수·관리자 노출이 보고자 확인을 기다리지 않는다는 뜻이고(M-08c ①)
    확인 요청 자체의 인증 요구와는 무관하다.
    """
    identity = {"wid": claims["wid"], "tenant": claims.get("tenant")}
    raw = await request.json()
    bad = risk_reports.identity_fields_in(raw)
    if bad:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "forbidden_fields",
                "message": "보고자 식별자는 서버가 도출합니다 — 요청 본문 수신 금지 (M-08b ④)",
                "fields": bad,
            },
        )

    if role() == "edge":
        item = queue.enqueue(
            "POST", CONFIRM_PATH.format(report_id=report_id), body.model_dump(), identity
        )
        relayed = await queue.wait_for_response(item)
        return JSONResponse(status_code=relayed["status_code"], content=relayed["body"])

    try:
        result = await asyncio.to_thread(
            risk_reports.confirm,
            report_id, body.result, body.corrected_text, (identity or {}).get("wid"),
        )
    except risk_reports.ReportNotFound:
        raise HTTPException(status_code=404, detail="report not found") from None
    return JSONResponse(status_code=200, content=result)
