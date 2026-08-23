"""GET /health (루트, 인증 없음) — 로직은 services/system_service.py. [새봄]"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.system_service import health_report

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> JSONResponse:
    status_code, body = health_report()
    return JSONResponse(status_code=status_code, content=body)
