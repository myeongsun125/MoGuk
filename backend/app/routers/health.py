"""GET /health (루트, 인증 없음) — 로직은 services/system_service.py. [새봄]

POST /internal/core-heartbeat — core-api → edge-api outbound 하트비트 수신 (M-22). caddy 는 /internal 을
라우팅하지 않으므로 edge_net 내부에서만 도달한다. 송신 측 스케줄러는 새봄 구현.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.system_service import health_report, mark_core_heartbeat

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> JSONResponse:
    status_code, body = health_report()
    return JSONResponse(status_code=status_code, content=body)


@router.post("/internal/core-heartbeat", status_code=204)
def core_heartbeat() -> None:
    mark_core_heartbeat()
