"""/health 컴포넌트 체크 — routers/health.py 에서 호출. 역할(API_ROLE)별로 판정 기준이 다르다. [새봄]

공통 응답 필드(변경 시 병갑과 합의): status, version, slot(blue/green), components
- core-api: components{api, db, llm} · 200/503 판정 = components.db (DB 미설정 시 기동 실패가 정답)
- edge-api: components{api, core_relay} · DB 체크 없음 — edge 는 core 로 연결할 수 없다(M-22).
  core_relay = core-api 가 outbound 로 보내는 하트비트(POST /internal/core-heartbeat)의 신선도만 본다.
  200/503 판정 = self(api) 뿐. 하트비트가 오래됐으면 status="degraded" 로 표면화하되 200 유지.
"""

import os
import time

APP_VERSION = os.getenv("APP_VERSION", "0.1.0-dev")
APP_SLOT = os.getenv("APP_SLOT", "dev")  # blue | green | dev — 무중단 전환 검증용 식별자

CORE_RELAY_STALE_S = float(os.getenv("CORE_RELAY_STALE_S", "90"))


def role() -> str:
    return os.getenv("API_ROLE", "edge")  # edge | core


def _require_env(name: str) -> str:
    # 기본값 없음 — 미설정이면 기동 실패가 정답 (skeleton-v3 R1, 감사 A-04)
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"required env {name} is not set (see .env.example)")
    return value


def validate_env() -> None:
    """프로세스 기동 시 1회 — core 역할은 DATABASE_URL 필수. edge 는 내부 DB 자격증명을 가지지 않는다."""
    if role() == "core":
        _require_env("DATABASE_URL")


# ── core-api 컴포넌트 ─────────────────────────────────────────

def check_db() -> dict:
    """DB 연결·응답을 점검한다. 실패해도 예외를 밖으로 던지지 않는다."""
    t0 = time.perf_counter()
    try:
        import psycopg

        with psycopg.connect(_require_env("DATABASE_URL"), connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        }
    except Exception as exc:  # noqa: BLE001 — health는 원인 유형만 노출
        return {"status": "fail", "error": type(exc).__name__}


def check_llm() -> dict:
    """ollama 모델 탑재 여부로 ok|degraded 판정 (M-03). 200/503 판정에는 관여하지 않는다 — 기준은 db 뿐."""
    try:
        from app.services.llm_adapter import probe

        return probe()
    except Exception as exc:  # noqa: BLE001 — health 는 원인 유형만 노출
        return {"status": "fail", "error": type(exc).__name__}


# ── edge-api 컴포넌트 ─────────────────────────────────────────

_core_heartbeat_at: float | None = None


def mark_core_heartbeat() -> None:
    """core-api → edge-api outbound 하트비트 수신 시각 기록 (단방향 규칙의 유일한 도달 경로)."""
    global _core_heartbeat_at
    _core_heartbeat_at = time.time()


def check_core_relay() -> dict:
    if _core_heartbeat_at is None:
        return {"status": "unknown", "age_s": None}
    age = round(time.time() - _core_heartbeat_at, 1)
    return {"status": "ok" if age <= CORE_RELAY_STALE_S else "stale", "age_s": age}


# ── 판정 ─────────────────────────────────────────────────────

def health_report() -> tuple[int, dict]:
    """(http_status, body)."""
    base = {"version": APP_VERSION, "slot": APP_SLOT, "role": role()}
    if role() == "core":
        db = check_db()
        healthy = db["status"] == "ok"
        return (200 if healthy else 503), {
            "status": "ok" if healthy else "degraded",
            **base,
            "components": {"api": {"status": "ok"}, "db": db, "llm": check_llm()},
        }
    relay = check_core_relay()
    return 200, {
        "status": "ok" if relay["status"] == "ok" else "degraded",
        **base,
        "components": {"api": {"status": "ok"}, "core_relay": relay},
    }
