"""/admin — 대시보드·승인큐·위험보고·안전일지·문서업로드. [새봄]"""

from fastapi import APIRouter

router = APIRouter(prefix="/admin", tags=["admin"])


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
    raise NotImplementedError("[새봄] GET /admin/reports?status=")


@router.post("/reports/{report_id}/ack")
def ack_report(report_id: int) -> dict:
    raise NotImplementedError("[새봄] POST /admin/reports/{id}/ack")


@router.post("/reports/{report_id}/resolve")
def resolve_report(report_id: int, body: dict | None = None) -> dict:
    # {note?}
    raise NotImplementedError("[새봄] POST /admin/reports/{id}/resolve")


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
