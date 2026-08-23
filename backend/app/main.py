"""MoGuk API 엔트리 — 라우터 include만. 로직은 services/로 위임. [새봄]

- 운영 엔드포인트 `/health`, `/`는 루트(Base 밖). compose 헬스체크·CI 게이트·blue-green
  판정이 소비하므로 경로·응답 계약(status/version/slot/components, 200/503) 변경 금지.
- 비즈니스 API는 `/api/v1/*` (docs/skeleton-v3.md §3).
- 같은 이미지가 API_ROLE=edge|core 로 두 번 기동된다 (§5 edge-api / core-api).
"""

import os

from fastapi import FastAPI

from app.routers import admin, ask, auth, chat, health, learn, notifications, reports
from app.services.system_service import APP_SLOT, APP_VERSION

API_ROLE = os.getenv("API_ROLE", "edge")  # edge | core

app = FastAPI(title=f"MoGuk API ({API_ROLE})", version=APP_VERSION)

# 루트 운영 엔드포인트
app.include_router(health.router)

# 비즈니스 API
API_V1 = "/api/v1"
for r in (auth, learn, ask, reports, chat, notifications, admin):
    app.include_router(r.router, prefix=API_V1)


@app.get("/")
def root() -> dict:
    return {"service": "MoGuk", "role": API_ROLE, "version": APP_VERSION, "slot": APP_SLOT}
