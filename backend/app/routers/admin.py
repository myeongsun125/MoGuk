"""/admin — 대시보드·승인큐·위험보고·안전일지·문서업로드. [새봄]

위험보고 전이·조회 (M-08·M-08a, 경로 판정 (가) — §3 기존 관리자 블록 그대로):
역할 분기 (M-28c): API_ROLE=edge 는 DB 자격이 없으므로 4종 전부 릴레이 큐 경유,
core 는 저장소 직접 호출. core 폴러도 같은 함수를 쓰며 HTTP 재귀는 없다.
  GET  /admin/reports?status=      목록 (original_text 미포함)
  GET  /admin/reports/{id}         상세 + events[] (원문 열람 → original_viewed 감사)
  POST /admin/reports/{id}/ack     submitted → acknowledged
  POST /admin/reports/{id}/resolve {note?} — acknowledged → resolved
단방향만 허용, 스킵·역행은 422. 행위자는 events.actor 단독 기록(M-15b 미결).
"""

import asyncio
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.services import approval, dashboard as dashboard_service, risk_reports
from app.services.relay import queue
from app.services.system_service import role

router = APIRouter(prefix="/admin", tags=["admin"])

# M-28c ① 릴레이 경로 — §3 관리자 블록 등재분.
DASHBOARD_PATH = "/api/v1/admin/dashboard"
GLOSSARY_PATH = "/api/v1/admin/glossary"
UNANSWERED_PATH = "/api/v1/admin/unanswered"
LIST_PATH = "/api/v1/admin/reports"
DETAIL_PATH = "/api/v1/admin/reports/{report_id}"
ACK_PATH = "/api/v1/admin/reports/{report_id}/ack"
RESOLVE_PATH = "/api/v1/admin/reports/{report_id}/resolve"


async def _relay(path: str, method: str, body: dict) -> JSONResponse:
    """M-28c ②: edge 는 DB 자격이 없다 — 릴레이 큐로 넘기고 core 회신을 그대로 돌려준다.

    identity 는 관리자 인증 부재(M-15b)로 None — actor 는 core 가 단일 지점에서 결정한다.
    """
    item = queue.enqueue(method, path, body, None)
    relayed = await queue.wait_for_response(item)
    return JSONResponse(status_code=relayed["status_code"], content=relayed["body"])


async def _json_body(request: Request) -> dict | None:
    """본문 없음도 허용(ack). 파싱 실패는 None 으로 본다."""
    if not (await request.body()):
        return None
    try:
        return await request.json()
    except Exception:  # noqa: BLE001 — 형식 오류는 아래 검사에서 걸리지 않고 그대로 무시
        return None


def _reject_identity_fields(body: object) -> None:
    """M-08b ④ — 신원·서버 도출 필드가 본문에 오면 400(무시 아님). 저장소 호출 전에 막는다."""
    bad = risk_reports.identity_fields_in(body)
    if bad:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "forbidden_fields",
                "message": "행위자·테넌트·상태는 서버가 결정합니다 — 요청 본문 수신 금지 (M-08b ④)",
                "fields": bad,
            },
        )


@router.get("/dashboard")
async def dashboard() -> JSONResponse:
    """KPI 4종 + 오늘 시간대별 추이 (총괄 확정 0830). 읽기 전용 — 쓰기·이벤트 없음.

    학습 KPI(avg_comprehension·completion_rate·per_worker·per_module)는 학습 모듈 구현 후(V5).
    """
    if role() == "edge":
        return await _relay(DASHBOARD_PATH, "GET", {})
    result = await asyncio.to_thread(dashboard_service.get_dashboard)
    return JSONResponse(status_code=200, content=result)


@router.post("/workers/invite")
def invite_worker(body: dict) -> dict:
    # {name, emp_no, lang} → {invite_url}
    raise NotImplementedError("[새봄] POST /admin/workers/invite")


@router.post("/documents", status_code=202)
def upload_document() -> dict:
    # multipart → 202 (ingest job)
    raise NotImplementedError("[새봄] POST /admin/documents")


@router.get("/glossary")
async def list_glossary(status: str | None = approval.GLOSSARY_DEFAULT_STATUS) -> JSONResponse:
    """용어 후보 목록 — 기본 필터 draft. 읽기 전용(전이는 approve/reject 소관)."""
    if role() == "edge":
        path = GLOSSARY_PATH + (f"?status={quote(status)}" if status else "")
        return await _relay(path, "GET", {})
    result = await asyncio.to_thread(approval.list_glossary, status)
    return JSONResponse(status_code=200, content=result)


@router.post("/glossary/{term_id}/approve")
def approve_glossary(term_id: int) -> dict:
    raise NotImplementedError("[새봄] POST /admin/glossary/{id}/approve")


@router.post("/glossary/{term_id}/reject")
def reject_glossary(term_id: int) -> dict:
    raise NotImplementedError("[새봄] POST /admin/glossary/{id}/reject")


@router.get("/unanswered")
async def list_unanswered(status: str | None = approval.UNANSWERED_DEFAULT_STATUS) -> JSONResponse:
    """무근거 질의 대기 목록(M-05·M-05a 2종 한정) — 기본 필터 open."""
    if role() == "edge":
        path = UNANSWERED_PATH + (f"?status={quote(status)}" if status else "")
        return await _relay(path, "GET", {})
    result = await asyncio.to_thread(approval.list_unanswered, status)
    return JSONResponse(status_code=200, content=result)


@router.post("/unanswered/{question_id}/answer")
def answer_unanswered(question_id: int, body: dict) -> dict:
    # {text} → ingest_answer job → documents(origin='admin_answer') 편입 (M-05)
    raise NotImplementedError("[새봄] POST /admin/unanswered/{id}/answer")


@router.get("/reports")
async def list_reports(status: str | None = None) -> JSONResponse:
    # M-08b 기재 필드 — original_text 미포함
    if role() == "edge":
        path = LIST_PATH + (f"?status={quote(status)}" if status else "")
        return await _relay(path, "GET", {})
    result = await asyncio.to_thread(risk_reports.list_reports, status)
    return JSONResponse(status_code=200, content=result)


@router.get("/reports/{report_id}")
async def report_detail(report_id: int) -> JSONResponse:
    """상세 + events[]. 원문을 실어 보내므로 original_viewed 감사 이벤트를 남긴다(M-08a)."""
    if role() == "edge":
        return await _relay(DETAIL_PATH.format(report_id=report_id), "GET", {})
    try:
        result = await asyncio.to_thread(risk_reports.get_report_detail, report_id)
    except risk_reports.ReportNotFound:
        raise HTTPException(status_code=404, detail="report not found") from None
    return JSONResponse(status_code=200, content=result)


@router.post("/reports/{report_id}/ack")
async def ack_report(report_id: int, request: Request) -> JSONResponse:
    _reject_identity_fields(await _json_body(request))
    if role() == "edge":
        return await _relay(ACK_PATH.format(report_id=report_id), "POST", {})
    try:
        result = await asyncio.to_thread(risk_reports.acknowledge, report_id)
    except risk_reports.ReportNotFound:
        raise HTTPException(status_code=404, detail="report not found") from None
    except risk_reports.TransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return JSONResponse(status_code=200, content=result)


@router.post("/reports/{report_id}/resolve")
async def resolve_report(report_id: int, request: Request) -> JSONResponse:
    """{note?} — acknowledged → resolved. 정정은 새 보고 + 원 보고 참조(역행 없음)."""
    body = await _json_body(request)
    _reject_identity_fields(body)
    note = (body or {}).get("note")
    if role() == "edge":
        return await _relay(RESOLVE_PATH.format(report_id=report_id), "POST", {"note": note})
    try:
        result = await asyncio.to_thread(risk_reports.resolve, report_id, note)
    except risk_reports.ReportNotFound:
        raise HTTPException(status_code=404, detail="report not found") from None
    except risk_reports.TransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return JSONResponse(status_code=200, content=result)


@router.get("/conversations/risk")
def risk_conversations() -> list:
    # 요약만
    raise NotImplementedError("[새봄] GET /admin/conversations/risk")


@router.get("/conversations/{conversation_id}/full")
def conversation_full(conversation_id: int) -> dict:
    # 원문 — access_logs 기록 (M-07)
    raise NotImplementedError("[새봄] GET /admin/conversations/{id}/full")


@router.get("/safety/ledger")
def safety_ledger(course_id: int, period: str):
    # → PDF|HTML (modules/safety.render_edu_ledger, M-14)
    raise NotImplementedError("[새봄] GET /admin/safety/ledger")
