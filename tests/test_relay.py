"""M-28·M-28a 릴레이 큐·폴러 단위 테스트 — 실서버 불요(ASGITransport/직접 호출). [새봄]

검증 대상 계약:
- M-22: /internal/relay/* 는 edge 에만, core→edge 폴러는 core 에만 (역할 분리)
- M-28: edge 큐 적재 → core long-poll pull → 처리 → respond → edge HTTP 완결
- M-28a: hold_s=20 / batch ≤10 / request_id UUIDv4 멱등 / edge 보류 30s→504 / lease 60s·재배포 1회
"""

import asyncio
import uuid

import httpx
import pytest

from app.main import build_app
from app.services import relay, system_service
from app.workers import relay_poller


@pytest.fixture(autouse=True)
def _base_env(monkeypatch):
    """테스트는 짧은 값으로 — 기본값 검증은 별도 케이스에서 한다."""
    for key in (
        "RELAY_HOLD_S",
        "RELAY_BATCH_MAX",
        "RELAY_EDGE_WAIT_S",
        "RELAY_LEASE_S",
        "RELAY_REDELIVER_MAX",
        "API_ROLE",
        "EDGE_API_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    relay.queue.reset()
    yield
    relay.queue.reset()


def _q() -> relay.RelayQueue:
    return relay.RelayQueue()


# ── M-28a 확정 기본값 ──────────────────────────────────────

def test_relay_m28a_defaults():
    assert relay.hold_s() == 20.0
    assert relay.batch_max() == 10
    assert relay.edge_wait_s() == 30.0
    assert relay.lease_s() == 60.0
    assert relay.redeliver_max() == 1


def test_relay_hold_can_be_set_to_rejected_fallback(monkeypatch):
    """기각안(hold_s=0.5)도 코드 변경 없이 env 로만 전환 가능해야 한다 (M-28a)."""
    monkeypatch.setenv("RELAY_HOLD_S", "0.5")
    assert relay.hold_s() == 0.5


# ── 역할 분리 (M-22) ──────────────────────────────────────

def _mounted_paths(app) -> set[str]:
    """실제 마운트된 경로 집합 — include_router 항목까지 openapi 로 해석한다."""
    return set(app.openapi()["paths"])


def test_relay_router_only_on_edge():
    edge_paths = _mounted_paths(build_app("edge"))
    core_paths = _mounted_paths(build_app("core"))

    assert "/internal/relay/pending" in edge_paths
    assert "/internal/relay/{request_id}/respond" in edge_paths
    assert not any(p.startswith("/internal/relay") for p in core_paths)
    # 비즈니스 API 는 양쪽 공통
    assert "/api/v1/ask" in edge_paths and "/api/v1/ask" in core_paths


def test_relay_poller_only_on_core():
    assert relay.poller_enabled("core") is True
    assert relay.poller_enabled("edge") is False
    assert relay.relay_router_enabled("edge") is True
    assert relay.relay_router_enabled("core") is False


# ── enqueue / request_id ──────────────────────────────────

def test_relay_enqueue_generates_uuid4():
    q = _q()
    item = q.enqueue("POST", "/api/v1/ask", {"question": "q"})

    parsed = uuid.UUID(item.request_id)
    assert parsed.version == 4
    assert item.state == relay.PENDING
    assert item.deliver_count == 0
    assert q.get(item.request_id) is item


def test_relay_item_payload_excludes_internals():
    q = _q()
    item = q.enqueue("POST", "/api/v1/ask", {"question": "q", "lang": "vi"})

    payload = item.as_payload()
    assert set(payload) == {
        "request_id", "method", "path", "body", "enqueued_at", "leased_at", "deliver_count",
    }
    assert payload["leased_at"] is None  # 아직 미배포
    assert payload["body"] == {"question": "q", "lang": "vi"}


# ── pending: 즉시 / long-poll / batch 상한 ────────────────

@pytest.mark.asyncio
async def test_relay_pending_returns_immediately_when_queued():
    q = _q()
    item = q.enqueue("POST", "/api/v1/ask", {"question": "q"})

    batch = await q.poll_pending(hold=5)

    assert [i.request_id for i in batch] == [item.request_id]
    assert item.state == relay.LEASED
    assert item.lease_expires_at is not None


@pytest.mark.asyncio
async def test_relay_long_poll_returns_empty_after_hold():
    q = _q()
    started = asyncio.get_running_loop().time()

    batch = await q.poll_pending(hold=0.2)

    assert batch == []
    assert asyncio.get_running_loop().time() - started >= 0.2


@pytest.mark.asyncio
async def test_relay_long_poll_picks_up_late_arrival():
    q = _q()

    async def _late():
        await asyncio.sleep(0.05)
        q.enqueue("POST", "/api/v1/ask", {"question": "늦게 도착"})

    asyncio.create_task(_late())
    batch = await q.poll_pending(hold=2)

    assert len(batch) == 1


@pytest.mark.asyncio
async def test_relay_batch_max_is_10():
    q = _q()
    for i in range(12):
        q.enqueue("POST", "/api/v1/ask", {"question": f"q{i}"})

    first = await q.poll_pending(hold=1)
    second = await q.poll_pending(hold=1)

    assert len(first) == 10  # M-28a batch ≤ 10
    assert len(second) == 2


@pytest.mark.asyncio
async def test_relay_batch_max_env_override(monkeypatch):
    monkeypatch.setenv("RELAY_BATCH_MAX", "3")
    q = _q()
    for i in range(5):
        q.enqueue("POST", "/api/v1/ask", {"question": f"q{i}"})

    assert len(await q.poll_pending(hold=1)) == 3


# ── respond: 완결 / 멱등 / 미지 ───────────────────────────

def test_relay_respond_idempotent_and_unknown():
    q = _q()
    item = q.enqueue("POST", "/api/v1/ask", {"question": "q"})

    assert q.respond(item.request_id, 200, {"answer": "ok"}) == "ok"
    assert item.state == relay.RESPONDED
    assert item.event.is_set()
    # 중복 respond 는 무시 — 첫 응답이 유지된다
    assert q.respond(item.request_id, 500, {"answer": "덮어쓰기 시도"}) == "duplicate"
    assert item.response == {"status_code": 200, "body": {"answer": "ok"}}

    assert q.respond("00000000-0000-4000-8000-000000000000", 200, {}) == "unknown"


@pytest.mark.asyncio
async def test_relay_wait_returns_response_payload():
    q = _q()
    item = q.enqueue("POST", "/api/v1/ask", {"question": "q"})

    async def _respond():
        await asyncio.sleep(0.05)
        q.respond(item.request_id, 201, {"answer": "완결", "trace_id": "t1"})

    asyncio.create_task(_respond())
    resp = await q.wait_for_response(item, wait=3)

    assert resp == {"status_code": 201, "body": {"answer": "완결", "trace_id": "t1"}}
    assert q.get(item.request_id) is None  # 완결 후 큐에서 제거


# ── 보류 상한 초과 → 504 ──────────────────────────────────

@pytest.mark.asyncio
async def test_relay_edge_wait_exceeded_returns_504():
    q = _q()
    item = q.enqueue("POST", "/api/v1/ask", {"question": "q"})

    resp = await q.wait_for_response(item, wait=0.15)

    assert resp["status_code"] == 504
    assert resp["body"]["reason"] == "edge_wait_exceeded"
    assert resp["body"]["retry"] is True
    assert resp["body"]["request_id"] == item.request_id


# ── 리스 만료 → 재배포 1회 → failed 504 ───────────────────

@pytest.mark.asyncio
async def test_relay_lease_expiry_redelivers_once_then_fails(monkeypatch):
    monkeypatch.setenv("RELAY_LEASE_S", "0.05")
    monkeypatch.setenv("RELAY_REDELIVER_MAX", "1")
    q = _q()
    item = q.enqueue("POST", "/api/v1/ask", {"question": "q"})
    waiter = asyncio.create_task(q.wait_for_response(item, wait=5))

    first = await q.poll_pending(hold=1)
    assert [i.request_id for i in first] == [item.request_id]

    await asyncio.sleep(0.15)  # 1차 리스 만료 → 재배포
    second = await q.poll_pending(hold=1)
    assert [i.request_id for i in second] == [item.request_id]
    assert item.deliver_count == 1

    resp = await waiter  # 2차 리스도 만료 → 한도 초과 → failed
    assert resp["status_code"] == 504
    assert resp["body"]["reason"] == "lease_expired"
    assert item.deliver_count == 2
    assert item.state == relay.FAILED


@pytest.mark.asyncio
async def test_relay_lease_not_expired_stays_leased(monkeypatch):
    monkeypatch.setenv("RELAY_LEASE_S", "60")
    q = _q()
    item = q.enqueue("POST", "/api/v1/ask", {"question": "q"})
    await q.poll_pending(hold=1)

    q.reap_expired()

    assert item.state == relay.LEASED
    assert item.deliver_count == 0
    assert await q.poll_pending(hold=0) == []  # 이미 leased → 중복 배포 없음


# ── HTTP 왕복 (edge 앱 전체) ──────────────────────────────

@pytest.mark.asyncio
async def test_relay_http_roundtrip_completes_original_request(monkeypatch):
    monkeypatch.setenv("API_ROLE", "edge")
    monkeypatch.setenv("RELAY_HOLD_S", "3")
    monkeypatch.setenv("RELAY_EDGE_WAIT_S", "5")
    app = build_app("edge")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://edge"
    ) as client:
        ask_task = asyncio.create_task(
            client.post("/api/v1/ask", json={"question": "프레스 점검?", "lang": "vi"})
        )

        pend = await client.get("/internal/relay/pending")
        assert pend.status_code == 200
        items = pend.json()["items"]
        assert len(items) == 1
        assert items[0]["method"] == "POST" and items[0]["path"] == "/api/v1/ask"
        assert items[0]["body"] == {"question": "프레스 점검?", "lang": "vi"}
        rid = items[0]["request_id"]

        payload = {
            "answer": "안전덮개를 확인하세요.",
            "sources": [{"document_id": 1, "chunk_id": 11, "title": "t", "category": "safety"}],
            "verify": {"score": 0.0, "passed": True, "gated": False},
            "trace_id": "trace-1",
        }
        rr = await client.post(
            f"/internal/relay/{rid}/respond", json={"status_code": 200, "body": payload}
        )
        assert rr.status_code == 200 and rr.json()["result"] == "ok"

        resp = await ask_task

    assert resp.status_code == 200
    assert resp.json() == payload  # §3 응답 스키마 무변경


@pytest.mark.asyncio
async def test_relay_http_respond_unknown_id_404(monkeypatch):
    monkeypatch.setenv("API_ROLE", "edge")
    app = build_app("edge")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://edge"
    ) as client:
        r = await client.post(
            "/internal/relay/00000000-0000-4000-8000-000000000000/respond",
            json={"status_code": 200, "body": {}},
        )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_relay_http_edge_ask_times_out_with_504(monkeypatch):
    monkeypatch.setenv("API_ROLE", "edge")
    monkeypatch.setenv("RELAY_EDGE_WAIT_S", "0.15")
    app = build_app("edge")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://edge"
    ) as client:
        r = await client.post("/api/v1/ask", json={"question": "q", "lang": "vi"})

    assert r.status_code == 504
    assert r.json()["retry"] is True


# ── core 폴러 ─────────────────────────────────────────────

def test_poller_dispatch_maps_ask(monkeypatch):
    seen = {}

    class _Res:
        answer = "ok"
        sources = []
        verify = {"score": 0.0, "passed": True, "gated": False}
        trace_id = "t9"

    def _run_ask(question, lang, worker_id=None, relay_meta=None):
        seen.update(question=question, lang=lang, worker_id=worker_id)
        return _Res()

    monkeypatch.setattr("app.agents.graph.run_ask", _run_ask)

    status, body = relay_poller.dispatch("POST", "/api/v1/ask", {"question": "q", "lang": "vi"})

    assert status == 200
    assert set(body) == {"answer", "sources", "verify", "trace_id"}
    assert seen == {"question": "q", "lang": "vi", "worker_id": None}


def test_poller_dispatch_unknown_path():
    """디스패치 대상은 /ask·/reports 2종 — 그 외는 404 (M-08b 배선 후)."""
    status, body = relay_poller.dispatch("POST", "/api/v1/chat", {})
    assert status == 404
    assert "디스패치 대상 아님" in body["detail"]


@pytest.mark.asyncio
async def test_poller_handle_item_posts_respond(monkeypatch):
    monkeypatch.setattr(
        relay_poller, "dispatch", lambda m, p, b, meta=None: (200, {"answer": "ok"})
    )
    sent = {}

    class _Client:
        async def post(self, url, json=None, timeout=None):
            sent.update(url=url, json=json)
            return httpx.Response(200, request=httpx.Request("POST", url))

    await relay_poller.handle_item(_Client(), {"request_id": "rid-1", "method": "POST", "path": "/api/v1/ask", "body": {}})

    assert sent["url"].endswith("/internal/relay/rid-1/respond")
    assert sent["json"] == {"status_code": 200, "body": {"answer": "ok"}}


@pytest.mark.asyncio
async def test_poller_dispatch_failure_responds_500(monkeypatch):
    def _boom(m, p, b, meta=None):
        raise RuntimeError("db down")

    monkeypatch.setattr(relay_poller, "dispatch", _boom)
    sent = {}

    class _Client:
        async def post(self, url, json=None, timeout=None):
            sent.update(json=json)
            return httpx.Response(200, request=httpx.Request("POST", url))

    await relay_poller.handle_item(_Client(), {"request_id": "rid-2", "method": "POST", "path": "/api/v1/ask", "body": {}})

    assert sent["json"]["status_code"] == 500
    assert sent["json"]["body"]["error"] == "RuntimeError"


@pytest.mark.asyncio
async def test_poller_loop_backs_off_and_stops(monkeypatch):
    """연결 실패해도 루프는 죽지 않고, stop 이벤트로 정상 종료한다."""
    monkeypatch.setattr(relay_poller, "BACKOFF_MIN_S", 0.01)
    monkeypatch.setattr(relay_poller, "BACKOFF_MAX_S", 0.02)
    calls = {"n": 0}

    async def _fail(client):
        calls["n"] += 1
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(relay_poller, "poll_once", _fail)

    stop = asyncio.Event()
    task = asyncio.create_task(relay_poller.run_poller(stop))
    for _ in range(100):  # 재시도 2회 관측될 때까지 (상한 있음)
        if calls["n"] >= 2:
            break
        await asyncio.sleep(0.01)
    stop.set()
    await asyncio.wait_for(task, timeout=2)

    assert calls["n"] >= 2  # 실패 후에도 재시도했다


def test_poller_edge_api_url_default(monkeypatch):
    monkeypatch.delenv("EDGE_API_URL", raising=False)
    assert relay_poller.edge_api_url() == "http://edge-api:8000"
    monkeypatch.setenv("EDGE_API_URL", "http://edge-api:8000/")
    assert relay_poller.edge_api_url() == "http://edge-api:8000"


# ── M-22a: /internal/* 접근 제한 미들웨어 ─────────────────

def _edge_client(client_addr: tuple[str, int]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=build_app("edge"), client=client_addr),
        base_url="http://edge",
    )


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "10.0.5.7", "172.18.0.3", "192.168.1.10", "::1", "::ffff:10.1.2.3"],
)
def test_is_internal_client_allows_loopback_and_rfc1918(host):
    assert relay.is_internal_client(host) is True


@pytest.mark.parametrize(
    "host",
    ["203.0.113.5", "8.8.8.8", "172.32.0.1", "2001:db8::1", "testclient", "", None],
)
def test_is_internal_client_rejects_public_and_non_ip(host):
    assert relay.is_internal_client(host) is False


@pytest.mark.asyncio
async def test_internal_allowed_from_private_ip(monkeypatch):
    monkeypatch.setenv("API_ROLE", "edge")
    monkeypatch.setenv("RELAY_HOLD_S", "0")
    async with _edge_client(("172.18.0.4", 40000)) as client:
        r = await client.get("/internal/relay/pending")
    assert r.status_code == 200
    assert r.json() == {"items": []}


@pytest.mark.asyncio
async def test_internal_forbidden_from_public_ip(monkeypatch):
    monkeypatch.setenv("API_ROLE", "edge")
    monkeypatch.setenv("RELAY_HOLD_S", "0")
    async with _edge_client(("203.0.113.5", 40000)) as client:
        r = await client.get("/internal/relay/pending")
        r2 = await client.post(
            "/internal/relay/00000000-0000-4000-8000-000000000000/respond",
            json={"status_code": 200, "body": {}},
        )
    assert r.status_code == 403 and r.json() == {"detail": "internal only"}
    assert r2.status_code == 403  # respond 도 동일하게 차단


@pytest.mark.asyncio
async def test_internal_ignores_forwarded_for_spoofing(monkeypatch):
    """X-Forwarded-For 로 사설 IP 를 위장해도 통과하지 않는다."""
    monkeypatch.setenv("API_ROLE", "edge")
    monkeypatch.setenv("RELAY_HOLD_S", "0")
    async with _edge_client(("203.0.113.5", 40000)) as client:
        r = await client.get(
            "/internal/relay/pending",
            headers={"X-Forwarded-For": "127.0.0.1", "X-Real-IP": "10.0.0.1"},
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_internal_heartbeat_also_guarded(monkeypatch):
    """/internal/core-heartbeat 도 같은 접두라 동일 규칙을 받는다."""
    monkeypatch.setenv("API_ROLE", "edge")
    # 하트비트 수신 시각은 모듈 전역 — 다른 테스트로 새지 않도록 teardown 에서 복원한다.
    monkeypatch.setattr(system_service, "_core_heartbeat_at", None)
    async with _edge_client(("203.0.113.5", 40000)) as client:
        blocked = await client.post("/internal/core-heartbeat")
    async with _edge_client(("10.0.0.9", 40000)) as client:
        allowed = await client.post("/internal/core-heartbeat")
    assert blocked.status_code == 403
    assert allowed.status_code == 204


@pytest.mark.asyncio
async def test_business_paths_unaffected_by_guard(monkeypatch):
    """/api/v1/*·/health 는 공인 IP 에서도 통과 — 미들웨어는 /internal 만 본다."""
    monkeypatch.setenv("API_ROLE", "edge")
    monkeypatch.setenv("RELAY_EDGE_WAIT_S", "0.1")
    async with _edge_client(("203.0.113.5", 40000)) as client:
        health = await client.get("/health")
        ask = await client.post("/api/v1/ask", json={"question": "q", "lang": "vi"})
    assert health.status_code == 200
    assert ask.status_code == 504  # 릴레이 보류 초과 — 403 이 아니다


# ── A-2: trace.relay 계측 (내부 전용) ─────────────────────

@pytest.mark.asyncio
async def test_relay_item_records_leased_and_responded_timestamps():
    q = _q()
    item = q.enqueue("POST", "/api/v1/ask", {"question": "q"})
    assert item.leased_at is None and item.responded_at is None

    batch = await q.poll_pending(hold=1)
    assert batch[0].leased_at is not None
    assert item.leased_at >= item.enqueued_at

    q.respond(item.request_id, 200, {"answer": "ok"})
    assert item.responded_at is not None and item.responded_at >= item.leased_at

    payload = item.as_payload()
    assert payload["leased_at"] == item.leased_at


def test_poller_passes_relay_meta_to_run_ask(monkeypatch):
    seen = {}

    class _Res:
        answer = "ok"
        sources = []
        verify = {"score": 0.0, "passed": True, "gated": False}
        trace_id = "t"

    def _run_ask(question, lang, worker_id=None, relay_meta=None):
        seen["relay_meta"] = relay_meta
        return _Res()

    monkeypatch.setattr("app.agents.graph.run_ask", _run_ask)

    status, body = relay_poller.dispatch(
        "POST", "/api/v1/ask", {"question": "q"}, {"enqueued_at": 1.0, "leased_at": 2.0}
    )

    assert status == 200
    assert seen["relay_meta"] == {"enqueued_at": 1.0, "leased_at": 2.0}
    # 응답 body 는 §3 4필드만 — relay 계측은 들어가지 않는다
    assert set(body) == {"answer", "sources", "verify", "trace_id"}


@pytest.mark.asyncio
async def test_poller_handle_item_forwards_timestamps(monkeypatch):
    seen = {}

    def _dispatch(method, path, body, relay_meta=None):
        seen["relay_meta"] = relay_meta
        return 200, {"answer": "ok"}

    monkeypatch.setattr(relay_poller, "dispatch", _dispatch)

    class _Client:
        async def post(self, url, json=None, timeout=None):
            return httpx.Response(200, request=httpx.Request("POST", url))

    await relay_poller.handle_item(
        _Client(),
        {
            "request_id": "rid",
            "method": "POST",
            "path": "/api/v1/ask",
            "body": {},
            "enqueued_at": 100.0,
            "leased_at": 101.5,
        },
    )

    assert seen["relay_meta"] == {"enqueued_at": 100.0, "leased_at": 101.5}
