"""/admin — 대시보드·승인큐·위험보고·안전일지·문서업로드. [새봄]

위험보고 전이·조회 (M-08·M-08a, 경로 판정 (가) — §3 기존 관리자 블록 그대로):
  GET  /admin/reports?status=      목록 (original_text 미포함)
  GET  /admin/reports/{id}         상세 + events[] (원문 열람 → original_viewed 감사)
  POST /admin/reports/{id}/ack     submitted → acknowledged
  POST /admin/reports/{id}/resolve {note?} — acknowledged → resolved
단방향만 허용, 스킵·역행은 422. 행위자는 events.actor 단독 기록(M-15b 미결).
"""

from fastapi import APIRouter, HTTPException, Request

from app.services import risk_reports

router = APIRouter(prefix="/admin", tags=["admin"])


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
def dashboard() -> dict:
    # → {workers, avg_comprehension, completion_rate, open_reports, weekly_trend[], per_worker[], per_module[]}
    raise NotImplementedError("[새봄] GET /admin/dashboard")


@router.post("/workers/invite")
def invite_worker(body: dict) -> dict:
    # {name, emp_no, lang} → {invite_url}
    raise NotImplementedError("[새봄] POST /admin/workers/invite")


@router.post("/documents", status_code=202)
def upload_document() -> dict:
    # multipart → 202 (ingest job)
    raise NotImplementedError("[새봄] POST /admin/documents")


@router.get("/glossary")
def list_glossary(status: str = "draft") -> list:
    raise NotImplementedError("[새봄] GET /admin/glossary?status=")


@router.post("/glossary/{term_id}/approve")
def approve_glossary(term_id: int) -> dict:
    raise NotImplementedError("[새봄] POST /admin/glossary/{id}/approve")


@router.post("/glossary/{term_id}/reject")
def reject_glossary(term_id: int) -> dict:
    raise NotImplementedError("[새봄] POST /admin/glossary/{id}/reject")


@router.get("/unanswered")
def list_unanswered() -> list:
    raise NotImplementedError("[새봄] GET /admin/unanswered")


@router.post("/unanswered/{question_id}/answer")
def answer_unanswered(question_id: int, body: dict) -> dict:
    # {text} → ingest_answer job → documents(origin='admin_answer') 편입 (M-05)
    raise NotImplementedError("[새봄] POST /admin/unanswered/{id}/answer")


@router.get("/reports")
def list_reports(status: str | None = None) -> list:
    # M-08b 기재 필드 — original_text 미포함
    return risk_reports.list_reports(status)


@router.get("/reports/{report_id}")
def report_detail(report_id: int) -> dict:
    """상세 + events[]. 원문을 실어 보내므로 original_viewed 감사 이벤트를 남긴다(M-08a)."""
    try:
        return risk_reports.get_report_detail(report_id)
    except risk_reports.ReportNotFound:
        raise HTTPException(status_code=404, detail="report not found") from None


@router.post("/reports/{report_id}/ack")
async def ack_report(report_id: int, request: Request) -> dict:
    _reject_identity_fields(await _json_body(request))
    try:
        return risk_reports.acknowledge(report_id)
    except risk_reports.ReportNotFound:
        raise HTTPException(status_code=404, detail="report not found") from None
    except risk_reports.TransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/reports/{report_id}/resolve")
async def resolve_report(report_id: int, request: Request) -> dict:
    """{note?} — acknowledged → resolved. 정정은 새 보고 + 원 보고 참조(역행 없음)."""
    body = await _json_body(request)
    _reject_identity_fields(body)
    try:
        return risk_reports.resolve(report_id, (body or {}).get("note"))
    except risk_reports.ReportNotFound:
        raise HTTPException(status_code=404, detail="report not found") from None
    except risk_reports.TransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


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
