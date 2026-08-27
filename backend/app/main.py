"""MoGuk API 엔트리 — 라우터 include만. 로직은 services/로 위임. [새봄]

- 운영 엔드포인트 `/health`, `/`는 루트(Base 밖). compose 헬스체크·CI 게이트·blue-green
  판정이 소비하므로 경로·응답 계약(status/version/slot/components, 200/503) 변경 금지.
- 비즈니스 API는 `/api/v1/*` (docs/skeleton-v3.md §3).
- 같은 이미지가 API_ROLE=edge|core 로 두 번 기동된다 (§5 edge-api / core-api).
  edge 는 내부 DB 자격증명·호스트명을 갖지 않으며 core 로 호출하지 않는다 (M-22).
"""

import logging
import os

from fastapi import FastAPI

from app.routers import admin, ask, auth, chat, health, learn, notifications, reports
from app.services.system_service import APP_SLOT, APP_VERSION, role, validate_env

# uvicorn 기본 설정은 자체 로거만 잡고 root 에 핸들러를 두지 않아 앱 로그가 유실된다.
# 어댑터 폴백 로그(M-17a 확인 방법)가 stdout 에 남아야 하므로 root 핸들러를 보장한다.
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(levelname)s %(name)s %(message)s")

validate_env()  # core 는 DATABASE_URL 필수 — 미설정 시 여기서 기동 실패 (R1)
API_ROLE = role()  # edge | core

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
