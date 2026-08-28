"""/internal/relay/* — M-28 릴레이 계약 (edge 전용). [새봄]

WORKORDER §5 초안 3종 중 core 가 호출하는 2개만 엔드포인트다.
enqueue 는 edge 내부 함수(services/relay.queue.enqueue) — 외부 미노출.

  GET  /internal/relay/pending            core outbound 폴링 (long-poll, batch)
  POST /internal/relay/{request_id}/respond   core → edge 회신 → 원 HTTP 응답 완결

접근 제어: routers/health.py 의 `/internal/core-heartbeat` 와 동일 관례 —
caddy 가 `/internal` 을 라우팅하지 않으므로 edge_net 내부에서만 도달한다.
앱 레벨 인증은 없다(한계). 이 라우터는 API_ROLE=edge 에서만 마운트된다(M-22 역할 분리).
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services.relay import queue

router = APIRouter(prefix="/internal/relay", tags=["relay"])


class RespondBody(BaseModel):
    status_code: int = 200
    body: dict | list | str | int | float | bool | None = None


@router.get("/pending")
async def pending() -> dict:
    """long-poll — 일감이 있으면 즉시, 없으면 RELAY_HOLD_S 대기 후 빈 배열."""
    batch = await queue.poll_pending()
    return {"items": [item.as_payload() for item in batch]}


@router.post("/{request_id}/respond")
def respond(request_id: str, body: RespondBody) -> JSONResponse:
    result = queue.respond(request_id, body.status_code, body.body)
    if result == "unknown":
        return JSONResponse(status_code=404, content={"detail": "unknown request_id", "request_id": request_id})
    # 멱등: 이미 완결된 건도 200 (M-28a request_id 멱등)
    return JSONResponse(status_code=200, content={"result": result, "request_id": request_id})
