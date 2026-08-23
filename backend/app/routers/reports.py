"""/reports — 위험 보고 (M-08). 202 즉시 → jobs 큐. [새봄]"""

from fastapi import APIRouter

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("", status_code=202)
def create_report() -> dict:
    # {text} | multipart(audio) → 202 {report_id}
    raise NotImplementedError("[새봄] POST /reports")


@router.get("/{report_id}")
def get_report(report_id: int) -> dict:
    raise NotImplementedError("[새봄] GET /reports/{id}")
