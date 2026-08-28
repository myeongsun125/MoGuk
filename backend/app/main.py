"""MoGuk API 엔트리 — 라우터 include만. 로직은 services/로 위임. [새봄]

- 운영 엔드포인트 `/health`, `/`는 루트(Base 밖). compose 헬스체크·CI 게이트·blue-green
  판정이 소비하므로 경로·응답 계약(status/version/slot/components, 200/503) 변경 금지.
- 비즈니스 API는 `/api/v1/*` (docs/skeleton-v3.md §3).
- 같은 이미지가 API_ROLE=edge|core 로 두 번 기동된다 (§5 edge-api / core-api).
  edge 는 내부 DB 자격증명·호스트명을 갖지 않으며 core 로 호출하지 않는다 (M-22).
- 역할 분리 (M-28·M-28a): `/internal/relay/*` 는 edge 에만 마운트하고,
  core→edge outbound 폴러는 core 에만 기동한다.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.routers import admin, ask, auth, chat, health, learn, notifications, relay, reports
from app.services.relay import (
    INTERNAL_PREFIX,
    is_internal_client,
    poller_enabled,
    relay_router_enabled,
)
from app.services.system_service import APP_SLOT, APP_VERSION, role, validate_env

# uvicorn 기본 설정은 자체 로거만 잡고 root 에 핸들러를 두지 않아 앱 로그가 유실된다.
# 어댑터 폴백 로그(M-17a 확인 방법)가 stdout 에 남아야 하므로 root 핸들러를 보장한다.
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(levelname)s %(name)s %(message)s")

log = logging.getLogger(__name__)

validate_env()  # core 는 DATABASE_URL 필수 — 미설정 시 여기서 기동 실패 (R1)
API_ROLE = role()  # edge | core
API_V1 = "/api/v1"


def _lifespan(api_role: str):
    """core 에서만 릴레이 폴러를 띄운다. 종료 시그널에 정상 종료."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = None
        stop = asyncio.Event()
        if poller_enabled(api_role):
            from app.workers.relay_poller import run_poller

            task = asyncio.create_task(run_poller(stop))
        try:
            yield
        finally:
            if task is not None:
                stop.set()
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as exc:  # noqa: BLE001 — 종료 경로에서 예외를 삼킨다
                    log.warning("relay poller 종료 중 예외: %s", type(exc).__name__)

    return lifespan


def build_app(api_role: str) -> FastAPI:
    app = FastAPI(
        title=f"MoGuk API ({api_role})", version=APP_VERSION, lifespan=_lifespan(api_role)
    )

    # 루트 운영 엔드포인트
    app.include_router(health.router)

    # 릴레이 (M-28) — edge 전용. caddy 가 /internal 을 라우팅하지 않는다.
    if relay_router_enabled(api_role):
        app.include_router(relay.router)

        @app.middleware("http")
        async def internal_only(request: Request, call_next):
            """M-22a: /internal/* 은 loopback·사설 대역 소스만. 그 외 403.

            판정은 request.client.host 만 본다 — X-Forwarded-For 는 위조 가능하고,
            caddy 가 /internal 을 라우팅하지 않으므로 프록시 경유 자체가 비정상이다.
            """
            if request.url.path.startswith(INTERNAL_PREFIX):
                host = request.client.host if request.client else None
                if not is_internal_client(host):
                    log.warning("M-22a: /internal 외부 접근 거부 client=%s path=%s", host, request.url.path)
                    return JSONResponse(status_code=403, content={"detail": "internal only"})
            return await call_next(request)

    # 비즈니스 API
    for r in (auth, learn, ask, reports, chat, notifications, admin):
        app.include_router(r.router, prefix=API_V1)

    @app.get("/")
    def root() -> dict:
        return {"service": "MoGuk", "role": api_role, "version": APP_VERSION, "slot": APP_SLOT}

    return app


app = build_app(API_ROLE)
