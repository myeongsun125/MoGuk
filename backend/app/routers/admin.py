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
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services import (
    admin_events,
    approval,
    dashboard as dashboard_service,
    documents as documents_service,
    invites,
    risk_reports,
)
from app.services.relay import queue
from app.services.system_service import role

router = APIRouter(prefix="/admin", tags=["admin"])

# M-28c ① 릴레이 경로 — §3 관리자 블록 등재분.
DASHBOARD_PATH = "/api/v1/admin/dashboard"
GLOSSARY_PATH = "/api/v1/admin/glossary"
UNANSWERED_PATH = "/api/v1/admin/unanswered"
UNANSWERED_ANSWER_PATH = "/api/v1/admin/unanswered/{question_id}/answer"
GLOSSARY_APPROVE_PATH = "/api/v1/admin/glossary/{term_id}/approve"
GLOSSARY_REJECT_PATH = "/api/v1/admin/glossary/{term_id}/reject"
EVENTS_PATH = "/api/v1/admin/events"
INVITE_PATH = "/api/v1/admin/workers/invite"
SEND_INVITE_PATH = "/api/v1/admin/workers/{worker_id}/send-invite"
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


class InviteRequest(BaseModel):
    name: str
    emp_no: str
    lang: str
    phone: str | None = None       # M-39 파트2 선택 필드 — 형식 검증 없음(계약), 그대로 저장


@router.post("/workers/invite", status_code=201)
async def invite_worker(body: InviteRequest, request: Request) -> JSONResponse:
    """{name, emp_no, lang, phone?} → 201 {invite_url, worker_id} (M-32 · §3:236 M-39 파트2).

    emp_no 미활성 중복은 재초대(기존 미사용 초대 만료 후 신규 1건), 활성 워커는 409.
    발급마다 admin_events 1행(action='worker_invited').

    M-32b: edge 는 DB 자격이 없으므로 릴레이 큐 경유(M-28c 동형) — 201·409·422 그대로 투과.
    """
    # M-08b ④ — 관리자 POST 4종과 동일한 가드. 릴레이 분기보다 앞이라 edge 에서도
    # 큐에 적재되기 전에 400 이 난다. InviteRequest 는 여분 필드를 조용히 버리므로
    # 원 본문을 따로 읽어 검사한다(파이단틱은 파싱만, 판정은 이 가드가 한다).
    _reject_identity_fields(await _json_body(request))
    if role() == "edge":
        return await _relay(INVITE_PATH, "POST", body.model_dump())
    try:
        result = await asyncio.to_thread(
            invites.create_invite, body.name, body.emp_no, body.lang, body.phone
        )
    except invites.InvalidInviteRequest as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except invites.WorkerAlreadyActive as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return JSONResponse(status_code=201, content=result)


class SendInviteRequest(BaseModel):
    # 총괄 계약(파트1): channel 은 kakao_link 만 유효 — 그 외 값(sms 포함)은 pydantic 422.
    channel: Literal["kakao_link"]


@router.post("/workers/{worker_id}/send-invite", status_code=201)
async def send_worker_invite(
    worker_id: int, body: SendInviteRequest, request: Request
) -> JSONResponse:
    """{channel:'kakao_link'} → 201 {share_url} — 기존 워커 초대 링크 재발급 (파트1).

    발급 규칙·URL 형태는 invites 발급 경로 재사용(미사용 1건 유지·재발급 시 기존 만료·72h).
    워커 없음 404, 이미 활성 409. 가드·릴레이 분기는 invite_worker(M-32b) 동형.
    """
    _reject_identity_fields(await _json_body(request))
    if role() == "edge":
        return await _relay(
            SEND_INVITE_PATH.format(worker_id=worker_id), "POST", {"channel": body.channel}
        )
    try:
        result = await asyncio.to_thread(invites.send_invite, worker_id)
    except invites.WorkerNotFound:
        raise HTTPException(status_code=404, detail="worker not found") from None
    except invites.WorkerAlreadyActive as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return JSONResponse(status_code=201, content=result)


class DocumentUploadRequest(BaseModel):
    title: str
    category: str          # 4종 검증은 서비스가 한다 — 릴레이(비 pydantic) 경로와 단일 판정
    text: str
    filename: str | None = None


@router.post("/documents", status_code=202)
async def upload_document(body: DocumentUploadRequest, request: Request) -> JSONResponse:
    """{title, category, text, filename?} → 202 {id, job_id} (M-41).

    JSON 본문만 받는다 — multipart·신규 의존성 없음(총괄 확정). 접수는 documents 1행 +
    ingest_document 잡 1행뿐(결정론 경로), 적재는 job_runner 가 비동기 수행.
    text 빈 값·category 4종 이탈은 422.
    """
    _reject_identity_fields(await _json_body(request))
    try:
        result = await asyncio.to_thread(
            documents_service.create_document,
            body.title, body.category, body.text, body.filename,
        )
    except documents_service.InvalidDocument as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return JSONResponse(status_code=202, content=result)


@router.get("/glossary")
async def list_glossary(status: str | None = approval.GLOSSARY_DEFAULT_STATUS) -> JSONResponse:
    """용어 후보 목록 — 기본 필터 draft. 읽기 전용(전이는 approve/reject 소관)."""
    if role() == "edge":
        path = GLOSSARY_PATH + (f"?status={quote(status)}" if status else "")
        return await _relay(path, "GET", {})
    result = await asyncio.to_thread(approval.list_glossary, status)
    return JSONResponse(status_code=200, content=result)


@router.post("/glossary/{term_id}/approve")
async def approve_glossary(term_id: int, request: Request) -> JSONResponse:
    """draft → approved. 전이마다 admin_events 1행(M-08d)."""
    _reject_identity_fields(await _json_body(request))
    if role() == "edge":
        return await _relay(GLOSSARY_APPROVE_PATH.format(term_id=term_id), "POST", {})
    try:
        result = await asyncio.to_thread(approval.approve_glossary, term_id)
    except approval.TermNotFound:
        raise HTTPException(status_code=404, detail="glossary term not found") from None
    except approval.TransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return JSONResponse(status_code=200, content=result)


@router.post("/glossary/{term_id}/reject")
async def reject_glossary(term_id: int, request: Request) -> JSONResponse:
    """{note?} — draft → rejected. 사유는 admin_events.detail 에 보존(glossary.note 무접촉)."""
    body = await _json_body(request)
    _reject_identity_fields(body)
    note = (body or {}).get("note")
    if role() == "edge":
        return await _relay(GLOSSARY_REJECT_PATH.format(term_id=term_id), "POST", {"note": note})
    try:
        result = await asyncio.to_thread(approval.reject_glossary, term_id, note)
    except approval.TermNotFound:
        raise HTTPException(status_code=404, detail="glossary term not found") from None
    except approval.TransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return JSONResponse(status_code=200, content=result)


@router.get("/events")
async def list_events(
    date: str | None = None,
    target_type: str | None = None,
    limit: int = admin_events.LIMIT_DEFAULT,
    offset: int = 0,
) -> JSONResponse:
    """감사 로그(M-08d ③) — 날짜(Asia/Seoul 일자)·target_type 필터, id desc. 읽기 전용."""
    if role() == "edge":
        q = {"date": date, "target_type": target_type, "limit": limit, "offset": offset}
        query = "&".join(f"{k}={quote(str(v))}" for k, v in q.items() if v not in (None, ""))
        return await _relay(EVENTS_PATH + (f"?{query}" if query else ""), "GET", {})
    result = await asyncio.to_thread(admin_events.list_events, date, target_type, limit, offset)
    return JSONResponse(status_code=200, content=result)


@router.get("/unanswered")
async def list_unanswered(status: str | None = approval.UNANSWERED_DEFAULT_STATUS) -> JSONResponse:
    """무근거 질의 대기 목록(M-05·M-05a 2종 한정) — 기본 필터 open."""
    if role() == "edge":
        path = UNANSWERED_PATH + (f"?status={quote(status)}" if status else "")
        return await _relay(path, "GET", {})
    result = await asyncio.to_thread(approval.list_unanswered, status)
    return JSONResponse(status_code=200, content=result)


class AnswerRequest(BaseModel):
    text: str


@router.post("/unanswered/{question_id}/answer")
async def answer_unanswered(question_id: int, body: AnswerRequest, request: Request) -> JSONResponse:
    """{text} — open → answered + ingest_answer job 적재 (M-05a).

    → {id, status:'answered', answered_at, ingest_job_id}. 적재(documents origin='admin_answer')는
    job_runner 가 비동기로 수행한다. 전이마다 admin_events 1행(M-08d).
    text 누락은 pydantic 422, 공백은 서비스가 422. open 아니면 422·대상 없음 404.
    """
    _reject_identity_fields(await _json_body(request))
    if role() == "edge":
        return await _relay(
            UNANSWERED_ANSWER_PATH.format(question_id=question_id), "POST", {"text": body.text}
        )
    try:
        result = await asyncio.to_thread(approval.answer_unanswered, question_id, body.text)
    except approval.UnansweredNotFound:
        raise HTTPException(status_code=404, detail="unanswered question not found") from None
    except (approval.InvalidAnswer, approval.TransitionError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return JSONResponse(status_code=200, content=result)


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
