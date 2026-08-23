"""/health 컴포넌트 체크 — main.py/routers/health.py에서 호출. [새봄]

계약(변경 시 병갑과 합의):
- 200 = components.db ok / 503 = db fail
- 응답 필드: status, version, slot(blue/green), components{api, db, llm}
"""

import os
import time

APP_VERSION = os.getenv("APP_VERSION", "0.1.0-dev")
APP_SLOT = os.getenv("APP_SLOT", "dev")  # blue | green | dev — 무중단 전환 검증용 식별자


def _require_env(name: str) -> str:
    # 기본값 없음 — 미설정이면 기동 실패가 정답 (skeleton-v3 R1, 감사 A-04)
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"required env {name} is not set (see .env.example)")
    return value


DATABASE_URL = _require_env("DATABASE_URL")


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


def check_llm() -> dict:
    # 어댑터(services/llm_adapter.py) 연결 시 ollama 모델 탑재 여부로 ok|degraded 판정 [새봄]
    return {"status": "not_wired"}


def health_report() -> tuple[int, dict]:
    """(http_status, body). 판정 기준은 components.db."""
    db = check_db()
    healthy = db["status"] == "ok"
    body = {
        "status": "ok" if healthy else "degraded",
        "version": APP_VERSION,
        "slot": APP_SLOT,
        "components": {
            "api": {"status": "ok"},
            "db": db,
            "llm": check_llm(),
        },
    }
    return (200 if healthy else 503), body
