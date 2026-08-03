"""MoGuk API — infra stub (v0)

인프라 리허설(blue-green 전환, 자동 재기동, 배포 게이트)의 기준점이 되는
최소 애플리케이션. 백엔드 본 구현(새봄)이 이 파일을 대체하되,
/health 의 응답 계약(스키마·상태코드)은 유지한다.

계약:
- GET /health → 200 (전 컴포넌트 정상) | 503 (핵심 컴포넌트 이상)
- 응답 필드: status, version, slot(blue/green), components{api,db,llm}
"""

import os
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse

APP_VERSION = os.getenv("APP_VERSION", "0.1.0-dev")
APP_SLOT = os.getenv("APP_SLOT", "dev")  # blue | green | dev — 무중단 전환 검증용 식별자
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://moguk:moguk@db:5432/moguk"
)

app = FastAPI(title="MoGuk API (infra stub)", version=APP_VERSION)


def check_db() -> dict:
    """DB 연결·응답을 점검한다. 실패해도 예외를 밖으로 던지지 않는다."""
    t0 = time.perf_counter()
    try:
        import psycopg

        with psycopg.connect(DATABASE_URL, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        }
    except Exception as exc:  # noqa: BLE001 — health는 원인 유형만 노출
        return {"status": "fail", "error": type(exc).__name__}


@app.get("/health")
def health() -> JSONResponse:
    db = check_db()
    healthy = db["status"] == "ok"
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ok" if healthy else "degraded",
            "version": APP_VERSION,
            "slot": APP_SLOT,
            "components": {
                "api": {"status": "ok"},
                "db": db,
                "llm": {"status": "not_wired"},  # 어댑터 연결 시 갱신 (새봄 파트)
            },
        },
    )


@app.get("/")
def root() -> dict:
    return {"service": "MoGuk", "version": APP_VERSION, "slot": APP_SLOT}
