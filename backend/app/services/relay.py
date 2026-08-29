"""M-28·M-28a 실시간 요청 릴레이 — edge 인메모리 큐. [새봄]

M-22 절대 준수: edge 는 core 를 호출하지 않는다. 모든 이동은 core→edge outbound 이며
edge 는 큐에 쌓고 기다릴 뿐이다. edge 는 DB 자격증명이 없으므로 큐는 프로세스 인메모리다.

흐름 (M-28):
  근로자 요청 → edge 핸들러가 enqueue(내부 함수, 외부 엔드포인트 아님) → 대기
  core 폴러 → GET /internal/relay/pending (long-poll) → 처리 → POST .../respond
  → edge 가 대기 중이던 HTTP 응답을 완결

파라미터 (M-28a 확정값 — env 키로 노출, .env.example·compose 등재는 BG 후속):
- RELAY_HOLD_S=20        long-poll 홀드 상한 (기각안 폴백 0.5 도 이 키로 설정 가능)
- RELAY_BATCH_MAX=10     pending 1회 반환 상한
- RELAY_EDGE_WAIT_S=30   근로자 요청 보류 상한 — 초과 시 504
- RELAY_LEASE_S=60       core 리스 유효 시간
- RELAY_REDELIVER_MAX=1  리스 만료 시 재배포 허용 횟수 (초과 → failed → 504)

hold(20s) 는 보류(30s)·리스(60s) 와 독립이다 (M-28a 원문).

M-28b 인증 컨텍스트 전파: item 최상위 identity(dict|None) = edge 검증 후의 {wid, tenant} 만.
원 JWT·Authorization 헤더는 릴레이 경계 미통과, body 혼입 금지(M-08b ④ 정합).
M-28a 파라미터 5종·큐 메커니즘·/internal 3종은 무접촉 — pending 응답에 필드 1개 additive 확장뿐.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# M-22a: /internal/* 은 loopback + RFC1918(도커 브리지·core_net) 소스만 허용한다.
INTERNAL_NETWORKS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
)
INTERNAL_PREFIX = "/internal/"


def is_internal_client(host: str | None) -> bool:
    """M-22a 판정 — request.client.host 만 본다. X-Forwarded-For 는 신뢰하지 않는다."""
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False  # 호스트명·비 IP 는 거부
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return any(ip.version == net.version and ip in net for net in INTERNAL_NETWORKS)


# ── M-28a 파라미터 ────────────────────────────────────────

DEFAULT_HOLD_S = 20.0
DEFAULT_BATCH_MAX = 10
DEFAULT_EDGE_WAIT_S = 30.0
DEFAULT_LEASE_S = 60.0
DEFAULT_REDELIVER_MAX = 1

# 만료 회수·완결 감지 주기. 이벤트 기반 대신 짧은 틱으로 두어 루프 간 결합을 만들지 않는다.
TICK_S = 0.05

PENDING = "pending"
LEASED = "leased"
RESPONDED = "responded"
FAILED = "failed"


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        log.warning("relay: env %s=%r 가 숫자가 아님 — 기본값 %s 사용", name, raw, default)
        return default


def _env_int(name: str, default: int, *, allow_zero: bool = False) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        log.warning("relay: env %s=%r 가 정수가 아님 — 기본값 %s 사용", name, raw, default)
        return default
    if value < 0 or (value == 0 and not allow_zero):
        log.warning("relay: env %s=%r 가 범위 밖 — 기본값 %s 사용", name, raw, default)
        return default
    return value


def hold_s() -> float:
    return _env_float("RELAY_HOLD_S", DEFAULT_HOLD_S)


def batch_max() -> int:
    return _env_int("RELAY_BATCH_MAX", DEFAULT_BATCH_MAX)


def edge_wait_s() -> float:
    return _env_float("RELAY_EDGE_WAIT_S", DEFAULT_EDGE_WAIT_S)


def lease_s() -> float:
    return _env_float("RELAY_LEASE_S", DEFAULT_LEASE_S)


def redeliver_max() -> int:
    return _env_int("RELAY_REDELIVER_MAX", DEFAULT_REDELIVER_MAX, allow_zero=True)


# ── 역할 분리 (M-22) ──────────────────────────────────────

def relay_router_enabled(api_role: str) -> bool:
    """/internal/relay/* 는 edge 에만 존재한다 — core 에는 노출하지 않는다."""
    return api_role == "edge"


def poller_enabled(api_role: str) -> bool:
    """core→edge outbound 폴러는 core 에만 기동한다."""
    return api_role == "core"


# ── 큐 ────────────────────────────────────────────────────

@dataclass
class RelayItem:
    request_id: str
    method: str
    path: str
    body: dict
    enqueued_at: float
    # M-28b ①: edge 가 require_worker 검증 후 claims 에서 뽑은 {wid, tenant} 만.
    # 원 JWT·Authorization 헤더는 릴레이 경계를 넘지 않는다. 미인증 경로는 None(④).
    identity: dict | None = None
    state: str = PENDING
    lease_expires_at: float | None = None
    leased_at: float | None = None      # 측정 #4 릴레이 왕복 계측
    responded_at: float | None = None   # 측정 #4 릴레이 왕복 계측
    deliver_count: int = 0
    response: dict | None = None  # {"status_code": int, "body": Any}
    event: asyncio.Event = field(default_factory=asyncio.Event)

    def as_payload(self) -> dict:
        """core 폴러에 넘기는 표현 — 대기 객체·내부 상태는 뺀다."""
        return {
            "request_id": self.request_id,
            "method": self.method,
            "path": self.path,
            "body": self.body,
            "enqueued_at": self.enqueued_at,
            "leased_at": self.leased_at,
            "deliver_count": self.deliver_count,
            "identity": self.identity,   # M-28b ③: additive 확장 1필드
        }


def timeout_response(request_id: str, reason: str) -> dict:
    return {
        "status_code": 504,
        "body": {
            "detail": "요청 처리가 지연되었습니다. 잠시 후 다시 시도해 주세요.",
            "reason": reason,
            "request_id": request_id,
            "retry": True,
        },
    }


class RelayQueue:
    """edge 프로세스 인메모리 큐. 단일 프로세스·단일 이벤트루프 전제."""

    def __init__(self) -> None:
        self._items: dict[str, RelayItem] = {}

    # -- 내부 함수 (외부 엔드포인트 아님 — WORKORDER §5) --
    def enqueue(
        self, method: str, path: str, body: dict, identity: dict | None = None
    ) -> RelayItem:
        item = RelayItem(
            request_id=str(uuid.uuid4()),  # UUIDv4, edge 발급 (M-28a)
            method=method,
            path=path,
            body=body,
            enqueued_at=time.time(),
            identity=identity,             # M-28b ①
        )
        self._items[item.request_id] = item
        log.info("relay: enqueue %s %s request_id=%s", method, path, item.request_id)
        return item

    def get(self, request_id: str) -> RelayItem | None:
        return self._items.get(request_id)

    def snapshot(self) -> list[RelayItem]:
        return list(self._items.values())

    def reset(self) -> None:
        self._items.clear()

    # -- 리스 만료 회수 --
    def reap_expired(self, now: float | None = None) -> list[RelayItem]:
        """만료된 리스를 pending 복귀 또는 failed 처리. 되돌린 항목을 반환."""
        now = time.time() if now is None else now
        touched: list[RelayItem] = []
        limit = redeliver_max()
        for item in self._items.values():
            if item.state != LEASED or item.lease_expires_at is None:
                continue
            if item.lease_expires_at > now:
                continue
            item.deliver_count += 1
            item.lease_expires_at = None
            if item.deliver_count > limit:
                item.state = FAILED
                item.response = timeout_response(item.request_id, "lease_expired")
                item.event.set()
                log.warning(
                    "relay: 재배포 한도 초과 — request_id=%s deliver_count=%s > %s",
                    item.request_id, item.deliver_count, limit,
                )
            else:
                item.state = PENDING
                log.warning(
                    "relay: 리스 만료 → 재배포 request_id=%s deliver_count=%s",
                    item.request_id, item.deliver_count,
                )
            touched.append(item)
        return touched

    # -- core 폴러: long-poll --
    def take_pending(self, now: float | None = None) -> list[RelayItem]:
        """pending 항목을 batch 상한까지 leased 로 전환해 반환 (대기 없음)."""
        now = time.time() if now is None else now
        limit = batch_max()
        expires = now + lease_s()
        taken: list[RelayItem] = []
        for item in self._items.values():
            if len(taken) >= limit:
                break
            if item.state != PENDING:
                continue
            item.state = LEASED
            item.lease_expires_at = expires
            item.leased_at = now
            taken.append(item)
        return taken

    async def poll_pending(self, hold: float | None = None) -> list[RelayItem]:
        """일감이 있으면 즉시, 없으면 최대 hold 초 대기 후 빈 목록."""
        hold = hold_s() if hold is None else hold
        deadline = time.monotonic() + hold
        while True:
            self.reap_expired()
            batch = self.take_pending()
            if batch:
                return batch
            if time.monotonic() >= deadline:
                return []
            await asyncio.sleep(min(TICK_S, max(0.0, deadline - time.monotonic())))

    # -- core 폴러: 회신 --
    def respond(self, request_id: str, status_code: int, body: Any) -> str:
        """'ok' | 'duplicate' | 'unknown'. 멱등 — 이미 완결된 건은 무시한다."""
        item = self._items.get(request_id)
        if item is None:
            return "unknown"
        if item.state in (RESPONDED, FAILED):
            log.info("relay: 중복 respond 무시 request_id=%s state=%s", request_id, item.state)
            return "duplicate"
        item.state = RESPONDED
        item.lease_expires_at = None
        item.responded_at = time.time()
        item.response = {"status_code": status_code, "body": body}
        item.event.set()
        return "ok"

    # -- edge 핸들러: 보류 --
    async def wait_for_response(self, item: RelayItem, wait: float | None = None) -> dict:
        """respond 도착 시 즉시 해제. 보류 상한 초과 시 504."""
        wait = edge_wait_s() if wait is None else wait
        deadline = time.monotonic() + wait
        try:
            while True:
                self.reap_expired()
                if item.event.is_set() and item.response is not None:
                    return item.response
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                try:
                    await asyncio.wait_for(item.event.wait(), timeout=min(TICK_S, left))
                except asyncio.TimeoutError:
                    continue
            item.state = FAILED
            item.response = timeout_response(item.request_id, "edge_wait_exceeded")
            log.warning("relay: 보류 상한 초과 request_id=%s wait=%ss", item.request_id, wait)
            return item.response
        finally:
            # 완결된 건은 큐에 남기지 않는다 (인메모리 누수 방지)
            self._items.pop(item.request_id, None)


queue = RelayQueue()
