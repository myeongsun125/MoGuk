"""core→edge 하트비트 스케줄러 (core 전용). [새봄]

M-22: 방향은 언제나 core → edge. edge 는 core 를 호출하지 않는다.
기존 수신부(`POST /internal/core-heartbeat`, routers/health.py)를 그대로 쓰며
**신규 /internal 엔드포인트를 만들지 않는다**(M-22a 경계 유지).

edge `/health` 의 `core_relay` 판정 로직은 무변경 — `CORE_RELAY_STALE_S`(기본 90) 안에
갱신되기만 하면 ok 다. 확인 방법(age_s < 60)을 여유 있게 만족하도록 기본 주기를 30s 로 둔다.

env: EDGE_API_URL(기존 키, 기본 http://edge-api:8000)
     HEARTBEAT_INTERVAL_S(신규, 기본 30 — .env.example 등재는 BG 후속)
"""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

log = logging.getLogger(__name__)

DEFAULT_INTERVAL_S = 30.0
POST_TIMEOUT_S = 5.0
BACKOFF_MIN_S = 1.0
BACKOFF_MAX_S = 30.0


def edge_api_url() -> str:
    return (os.getenv("EDGE_API_URL") or "http://edge-api:8000").rstrip("/")


def interval_s() -> float:
    raw = os.getenv("HEARTBEAT_INTERVAL_S")
    if not raw:
        return DEFAULT_INTERVAL_S
    try:
        value = float(raw)
    except ValueError:
        log.warning("heartbeat: env HEARTBEAT_INTERVAL_S=%r 가 숫자가 아님 — 기본값 사용", raw)
        return DEFAULT_INTERVAL_S
    if value <= 0:
        log.warning("heartbeat: env HEARTBEAT_INTERVAL_S=%r 가 0 이하 — 기본값 사용", raw)
        return DEFAULT_INTERVAL_S
    return value


async def beat_once(client: httpx.AsyncClient) -> int:
    """edge 수신부 1회 호출. 상태코드 반환(예외는 호출부가 처리)."""
    r = await client.post(
        f"{edge_api_url()}/internal/core-heartbeat", timeout=POST_TIMEOUT_S
    )
    r.raise_for_status()
    return r.status_code


async def run_heartbeat(stop: asyncio.Event) -> None:
    """기동~정지까지 주기 전송. 실패는 1s→30s 백오프, 성공 시 주기로 복귀."""
    backoff = BACKOFF_MIN_S
    log.info("heartbeat: 시작 (edge=%s, interval=%ss)", edge_api_url(), interval_s())
    async with httpx.AsyncClient() as client:
        while not stop.is_set():
            try:
                await beat_once(client)
                wait = interval_s()
                backoff = BACKOFF_MIN_S
            except Exception as exc:  # noqa: BLE001 — 연결 실패도 루프를 끊지 않는다
                log.warning(
                    "heartbeat: 전송 실패 %s — %ss 후 재시도", type(exc).__name__, backoff
                )
                wait = backoff
                backoff = min(backoff * 2, BACKOFF_MAX_S)
            try:
                await asyncio.wait_for(stop.wait(), timeout=wait)
            except asyncio.TimeoutError:
                pass
    log.info("heartbeat: 정상 종료")
