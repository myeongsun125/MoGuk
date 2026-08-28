"""/reports — 위험 보고 (M-08·M-08b). 202 즉시 → jobs 큐. [새봄]

M-08b ①: 접수는 LLM 비의존 결정론 경로 — 원문 무조건 적재 + 202 + submitted.
로컬 LLM(ollama)이 정지해 있어도 신고가 소실되지 않는다. 요약·severity 는
workers/job_runner.py 가 비동기로 채운다.

요청 필드 원문 컬럼명은 001 정본(original_text, R4)을 따른다.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.services import risk_reports

router = APIRouter(prefix="/reports", tags=["reports"])


class ReportRequest(BaseModel):
    original_text: str = Field(min_length=1)
    lang: str | None = None


@router.post("", status_code=202)
def create_report(body: ReportRequest) -> JSONResponse:
    # 원문 적재 + 요약 잡 enqueue + report_submitted 이벤트를 한 트랜잭션으로. LLM 호출 0.
    result = risk_reports.submit_text_report(body.original_text, lang=body.lang)
    return JSONResponse(status_code=202, content=result)


@router.get("/{report_id}")
def get_report(report_id: int) -> dict:
    raise NotImplementedError("[새봄] GET /reports/{id}")
