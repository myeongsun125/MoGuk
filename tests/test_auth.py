"""V3-2 인증·하트비트 단위 테스트 — 네트워크·DB 없음(전부 스텁). [새봄]

검증 대상 계약:
- skeleton §3: POST /auth/activate {token,pin} → {jwt,refresh,lang}(M-35, lang=workers.lang)
  · POST /auth/login {emp_no,pin} → {jwt,refresh} (2키 유지)
- M-15: 일회성 초대 토큰(만료·1회 소진) → PIN 해시만 저장 → JWT+리프레시
- 001 정본: workers(pin_hash·activated_at) / invites(token PK·expires_at·used_at)
- 실패 응답 무구분: 계정·토큰 존재 여부가 401 로 드러나지 않는다
- M-22: 신원·DB 는 core 소유 — edge 는 릴레이 경유. 하트비트는 core→edge outbound 만
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone

import httpx
import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from app.main import app, build_app
from app.services import auth as auth_service
from app.workers import heartbeat, relay_poller

client = TestClient(app, client=("127.0.0.1", 50000))

# 실제 JWT_SECRET 은 secrets.token_urlsafe(32) (WORKORDER §2) — 테스트도 32B 이상으로 둔다
SECRET = "test-secret-not-a-real-key-0123456789abcdef"
NOW = datetime.now(timezone.utc)


# ── 가짜 DB ───────────────────────────────────────────────

class FakeCursor:
    def __init__(self, store):
        self.store = store
        self.rowcount = store.get("rowcount", 1)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.store["calls"].append((sql, params))
        self._last = sql
        self.rowcount = self.store.get("rowcount", 1)

    def fetchone(self):
        for needle, value in self.store.get("rows", []):
            if needle in self._last:
                return value
        return None


class FakeConn:
    def __init__(self, store):
        self.store = store

    def cursor(self):
        return FakeCursor(self.store)

    def commit(self):
        self.store["commits"] = self.store.get("commits", 0) + 1


def fake_connect(store):
    from contextlib import contextmanager

    @contextmanager
    def _connect(slug=None):
        store["connects"] = store.get("connects", 0) + 1
        yield FakeConn(store)

    return _connect


def _store(**kw):
    base = {"calls": [], "rows": [], "commits": 0}
    base.update(kw)
    return base


def _sqls(store):
    return [c[0] for c in store["calls"]]


def _params_for(store, needle):
    return [c[1] for c in store["calls"] if needle in c[0]]


@pytest.fixture(autouse=True)
def _base_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/test")
    monkeypatch.setenv("API_ROLE", "core")
    monkeypatch.delenv("TENANT_SLUG", raising=False)
    monkeypatch.delenv("JWT_ACCESS_TTL_S", raising=False)
    monkeypatch.delenv("JWT_REFRESH_TTL_S", raising=False)
    monkeypatch.delenv("HEARTBEAT_INTERVAL_S", raising=False)
    # 테스트 속도 — PBKDF2 반복수를 낮춘다(형식·대조 로직은 동일)
    monkeypatch.setattr(auth_service, "PBKDF2_ITERATIONS", 1000)


def _invite_store(*, used_at=None, expires_at=None, worker_id=7, lang="vi"):
    """_SELECT_INVITE 열 순서 — (i.token, i.worker_id, i.expires_at, i.used_at, w.id, w.lang)."""
    expires_at = NOW + timedelta(days=1) if expires_at is None else expires_at
    return _store(
        rows=[("FROM invites", ("tok-1", worker_id, expires_at, used_at, worker_id, lang))]
    )


# ── PIN 해시 (평문 저장 금지) ─────────────────────────────

def test_pin_hash_format_and_verify():
    h = auth_service.hash_pin("1234")
    algo, iters, salt_b64, hash_b64 = h.split("$")

    assert algo == "pbkdf2_sha256"
    assert int(iters) > 0
    assert "1234" not in h                      # 평문 미포함
    assert auth_service.verify_pin("1234", h) is True
    assert auth_service.verify_pin("9999", h) is False


def test_pin_hash_salted_per_call():
    assert auth_service.hash_pin("1234") != auth_service.hash_pin("1234")


@pytest.mark.parametrize("stored", [None, "", "plaintext", "bcrypt$x$y$z", "pbkdf2_sha256$a$b"])
def test_verify_pin_rejects_malformed(stored):
    assert auth_service.verify_pin("1234", stored) is False


def test_activate_stores_hash_not_plaintext(monkeypatch):
    store = _invite_store()
    monkeypatch.setattr(auth_service.tenancy, "connect", fake_connect(store))

    auth_service.activate("tok-1", "4321")

    params = _params_for(store, "UPDATE workers SET pin_hash")[0]
    assert params["pin_hash"] != "4321"
    assert params["pin_hash"].startswith("pbkdf2_sha256$")
    assert auth_service.verify_pin("4321", params["pin_hash"]) is True


# ── 초대 토큰: 1회 소진 · 만료 ────────────────────────────

def test_activate_consumes_invite_in_one_transaction(monkeypatch):
    store = _invite_store()
    monkeypatch.setattr(auth_service.tenancy, "connect", fake_connect(store))

    out = auth_service.activate("tok-1", "4321")

    assert set(out) == {"jwt", "refresh", "lang"}          # M-35
    assert out["lang"] == "vi" and out["lang"] in {"vi", "in"}
    assert isinstance(out["jwt"], str) and isinstance(out["refresh"], str)
    sqls = _sqls(store)
    assert any("UPDATE workers SET pin_hash" in s for s in sqls)
    assert any("UPDATE invites SET used_at" in s for s in sqls)
    assert store["connects"] == 1 and store["commits"] == 1


def test_activate_rejects_reused_token(monkeypatch):
    store = _invite_store(used_at=NOW - timedelta(minutes=1))
    monkeypatch.setattr(auth_service.tenancy, "connect", fake_connect(store))

    with pytest.raises(auth_service.AuthError):
        auth_service.activate("tok-1", "4321")
    assert not any("UPDATE workers" in s for s in _sqls(store))


def test_activate_rejects_expired_token(monkeypatch):
    store = _invite_store(expires_at=NOW - timedelta(seconds=1))
    monkeypatch.setattr(auth_service.tenancy, "connect", fake_connect(store))

    with pytest.raises(auth_service.AuthError):
        auth_service.activate("tok-1", "4321")


def test_activate_rejects_unknown_token(monkeypatch):
    monkeypatch.setattr(auth_service.tenancy, "connect", fake_connect(_store(rows=[])))

    with pytest.raises(auth_service.AuthError):
        auth_service.activate("nope", "4321")


def test_activate_race_loses_when_invite_already_consumed(monkeypatch):
    """동시 활성화 — UPDATE ... WHERE used_at IS NULL 이 0행이면 실패."""
    store = _invite_store()
    store["rowcount"] = 0
    monkeypatch.setattr(auth_service.tenancy, "connect", fake_connect(store))

    with pytest.raises(auth_service.AuthError):
        auth_service.activate("tok-1", "4321")


# ── login: 실패 무구분 ────────────────────────────────────

def test_login_success(monkeypatch):
    h = auth_service.hash_pin("1234")
    store = _store(rows=[("FROM workers WHERE emp_no", (11, h))])
    monkeypatch.setattr(auth_service.tenancy, "connect", fake_connect(store))

    out = auth_service.login("E-11", "1234")

    assert set(out) == {"jwt", "refresh"}
    assert auth_service.decode_token(out["jwt"])["wid"] == 11


def test_login_failures_are_indistinguishable(monkeypatch):
    """계정 미존재와 PIN 불일치가 같은 401·같은 메시지로 나온다."""
    h = auth_service.hash_pin("1234")

    monkeypatch.setattr(auth_service.tenancy, "connect", fake_connect(_store(rows=[])))
    missing = client.post("/api/v1/auth/login", json={"emp_no": "none", "pin": "1234"})

    monkeypatch.setattr(
        auth_service.tenancy, "connect",
        fake_connect(_store(rows=[("FROM workers WHERE emp_no", (11, h))])),
    )
    wrong = client.post("/api/v1/auth/login", json={"emp_no": "E-11", "pin": "9999"})

    assert missing.status_code == wrong.status_code == 401
    assert missing.json() == wrong.json() == {"detail": auth_service.AUTH_FAILED_MESSAGE}


def test_login_never_returns_pin_hash(monkeypatch):
    h = auth_service.hash_pin("1234")
    monkeypatch.setattr(
        auth_service.tenancy, "connect",
        fake_connect(_store(rows=[("FROM workers WHERE emp_no", (11, h))])),
    )

    body = client.post("/api/v1/auth/login", json={"emp_no": "E-11", "pin": "1234"}).json()

    assert set(body) == {"jwt", "refresh"}
    assert "pbkdf2" not in str(body)


# ── JWT ───────────────────────────────────────────────────

def test_token_pair_claims_and_ttl():
    pair = auth_service.issue_token_pair(5, "axis_demo")
    access = auth_service.decode_token(pair["jwt"])
    refresh = auth_service.decode_token(pair["refresh"], expect_typ="refresh")

    assert access["wid"] == 5 and access["tenant"] == "axis_demo"
    assert access["sub"] == "worker:5" and access["typ"] == "access"
    assert refresh["typ"] == "refresh"
    assert access["jti"] != refresh["jti"]
    assert 0 < access["exp"] - access["iat"] <= auth_service.DEFAULT_ACCESS_TTL_S
    assert refresh["exp"] - refresh["iat"] == auth_service.DEFAULT_REFRESH_TTL_S


def test_ttl_env_override(monkeypatch):
    monkeypatch.setenv("JWT_ACCESS_TTL_S", "60")
    pair = auth_service.issue_token_pair(5, "t")
    claims = auth_service.decode_token(pair["jwt"])
    assert claims["exp"] - claims["iat"] == 60


def test_access_token_rejected_where_refresh_expected():
    pair = auth_service.issue_token_pair(5, "t")
    with pytest.raises(auth_service.AuthError, match="typ mismatch"):
        auth_service.decode_token(pair["jwt"], expect_typ="refresh")


def test_forged_and_expired_tokens_rejected():
    forged = pyjwt.encode({"wid": 1, "typ": "access", "sub": "worker:1",
                           "iat": int(time.time()), "exp": int(time.time()) + 60},
                          "wrong-secret-0123456789abcdef0123456789", algorithm="HS256")
    with pytest.raises(auth_service.AuthError):
        auth_service.decode_token(forged)

    past = int(time.time()) - 10
    expired = pyjwt.encode({"wid": 1, "typ": "access", "sub": "worker:1",
                            "iat": past - 60, "exp": past}, SECRET, algorithm="HS256")
    with pytest.raises(auth_service.AuthError):
        auth_service.decode_token(expired)


def test_alg_none_rejected():
    """alg 혼동 방지 — 서명 없는 토큰은 거부."""
    unsigned = pyjwt.encode({"wid": 1, "typ": "access", "sub": "worker:1",
                             "iat": int(time.time()), "exp": int(time.time()) + 60},
                            key="", algorithm="none")
    with pytest.raises(auth_service.AuthError):
        auth_service.decode_token(unsigned)


def test_refresh_rotation_issues_new_pair():
    pair = auth_service.issue_token_pair(9, "axis_demo")
    time.sleep(1.05)  # iat 초 단위 — 새 jti·새 exp 를 구분하기 위해
    rotated = auth_service.rotate(pair["refresh"])

    assert set(rotated) == {"jwt", "refresh"}
    assert rotated["jwt"] != pair["jwt"] and rotated["refresh"] != pair["refresh"]
    old = auth_service.decode_token(pair["refresh"], expect_typ="refresh")
    new = auth_service.decode_token(rotated["refresh"], expect_typ="refresh")
    assert new["jti"] != old["jti"] and new["wid"] == 9


def test_refresh_endpoint_rejects_access_token():
    pair = auth_service.issue_token_pair(9, "t")
    r = client.post("/api/v1/auth/refresh", json={"refresh": pair["jwt"]})
    assert r.status_code == 401 and r.json() == {"detail": auth_service.AUTH_FAILED_MESSAGE}


# ── 보호 엔드포인트 ───────────────────────────────────────

def test_protected_endpoint_200_with_jwt():
    pair = auth_service.issue_token_pair(21, "axis_demo")
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {pair['jwt']}"})

    assert r.status_code == 200
    assert r.json() == {"worker_id": 21, "tenant": "axis_demo", "typ": "access"}


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer "}, {"Authorization": "Basic abc"},
     {"Authorization": "Bearer not.a.jwt"}],
)
def test_protected_endpoint_401(headers):
    r = client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 401
    assert r.json() == {"detail": auth_service.AUTH_FAILED_MESSAGE}


def test_protected_endpoint_rejects_refresh_token():
    pair = auth_service.issue_token_pair(21, "t")
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {pair['refresh']}"})
    assert r.status_code == 401


def test_activate_then_login_then_protected(monkeypatch):
    """WORKORDER V3-2 확인 방법: activate → login → JWT 로 보호 엔드포인트 200."""
    store = _invite_store(worker_id=33, lang="in")
    monkeypatch.setattr(auth_service.tenancy, "connect", fake_connect(store))
    act = client.post("/api/v1/auth/activate", json={"token": "tok-1", "pin": "4321"})
    assert act.status_code == 200
    assert set(act.json()) == {"jwt", "refresh", "lang"}   # M-35 — 라우터 통과 후에도 3키
    assert act.json()["lang"] == "in"                      # 001 CHECK vi|in 다른 값도 그대로

    pin_hash = _params_for(store, "UPDATE workers SET pin_hash")[0]["pin_hash"]
    monkeypatch.setattr(
        auth_service.tenancy, "connect",
        fake_connect(_store(rows=[("FROM workers WHERE emp_no", (33, pin_hash))])),
    )
    log_in = client.post("/api/v1/auth/login", json={"emp_no": "E-33", "pin": "4321"})
    assert log_in.status_code == 200
    assert set(log_in.json()) == {"jwt", "refresh"}        # login 은 M-35 대상 아님

    me = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {log_in.json()['jwt']}"}
    )
    assert me.status_code == 200 and me.json()["worker_id"] == 33
    assert client.get("/api/v1/auth/me").status_code == 401  # 무토큰


# ── 릴레이 배선 (M-22) ────────────────────────────────────

def test_dispatch_supports_auth_paths(monkeypatch):
    store = _invite_store(worker_id=44)
    monkeypatch.setattr(auth_service.tenancy, "connect", fake_connect(store))

    status, body = relay_poller.dispatch(
        "POST", "/api/v1/auth/activate", {"token": "tok-1", "pin": "4321"}
    )
    assert status == 200 and set(body) == {"jwt", "refresh", "lang"}   # M-35

    h = auth_service.hash_pin("1234")
    monkeypatch.setattr(
        auth_service.tenancy, "connect",
        fake_connect(_store(rows=[("FROM workers WHERE emp_no", (44, h))])),
    )
    status, body = relay_poller.dispatch(
        "POST", "/api/v1/auth/login", {"emp_no": "E-44", "pin": "1234"}
    )
    assert status == 200 and set(body) == {"jwt", "refresh"}


def test_dispatch_auth_failure_is_401_without_reason(monkeypatch):
    monkeypatch.setattr(auth_service.tenancy, "connect", fake_connect(_store(rows=[])))

    status, body = relay_poller.dispatch(
        "POST", "/api/v1/auth/login", {"emp_no": "none", "pin": "1234"}
    )

    assert status == 401 and body == {"detail": auth_service.AUTH_FAILED_MESSAGE}


@pytest.mark.asyncio
async def test_auth_relay_roundtrip_edge_to_core(monkeypatch):
    """edge POST /auth/login → 릴레이 → core dispatch → respond → 200."""
    monkeypatch.setenv("API_ROLE", "edge")
    monkeypatch.setenv("RELAY_HOLD_S", "3")
    monkeypatch.setenv("RELAY_EDGE_WAIT_S", "5")
    from app.services import relay

    relay.queue.reset()
    h = auth_service.hash_pin("1234")
    monkeypatch.setattr(
        auth_service.tenancy, "connect",
        fake_connect(_store(rows=[("FROM workers WHERE emp_no", (55, h))])),
    )

    edge = build_app("edge")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=edge), base_url="http://edge"
    ) as c:
        posted = asyncio.create_task(
            c.post("/api/v1/auth/login", json={"emp_no": "E-55", "pin": "1234"})
        )
        items = (await c.get("/internal/relay/pending")).json()["items"]
        assert len(items) == 1 and items[0]["path"] == "/api/v1/auth/login"

        status, payload = relay_poller.dispatch(items[0]["method"], items[0]["path"], items[0]["body"])
        await c.post(
            f"/internal/relay/{items[0]['request_id']}/respond",
            json={"status_code": status, "body": payload},
        )
        resp = await posted

    assert resp.status_code == 200 and set(resp.json()) == {"jwt", "refresh"}
    relay.queue.reset()


# ── 하트비트 (M-22 · M-22a) ───────────────────────────────

def test_heartbeat_defaults_and_env(monkeypatch):
    assert heartbeat.interval_s() == 30.0
    assert heartbeat.edge_api_url() == "http://edge-api:8000"
    monkeypatch.setenv("HEARTBEAT_INTERVAL_S", "5")
    assert heartbeat.interval_s() == 5.0
    monkeypatch.setenv("HEARTBEAT_INTERVAL_S", "0")
    assert heartbeat.interval_s() == 30.0  # 0 이하는 기본값 폴백


@pytest.mark.asyncio
async def test_heartbeat_posts_to_existing_receiver(monkeypatch):
    """신규 /internal 엔드포인트 없이 기존 core-heartbeat 수신부를 호출한다."""
    seen = {}

    class _Client:
        async def post(self, url, timeout=None):
            seen["url"] = url
            return httpx.Response(204, request=httpx.Request("POST", url))

    assert await heartbeat.beat_once(_Client()) == 204
    assert seen["url"] == "http://edge-api:8000/internal/core-heartbeat"


@pytest.mark.asyncio
async def test_heartbeat_loop_repeats_and_stops(monkeypatch):
    monkeypatch.setenv("HEARTBEAT_INTERVAL_S", "0.01")
    calls = {"n": 0}

    async def _beat(client):
        calls["n"] += 1
        return 204

    monkeypatch.setattr(heartbeat, "beat_once", _beat)
    stop = asyncio.Event()
    task = asyncio.create_task(heartbeat.run_heartbeat(stop))
    for _ in range(200):
        if calls["n"] >= 3:
            break
        await asyncio.sleep(0.01)
    stop.set()
    await asyncio.wait_for(task, timeout=3)

    assert calls["n"] >= 3


@pytest.mark.asyncio
async def test_heartbeat_backs_off_on_failure(monkeypatch):
    monkeypatch.setattr(heartbeat, "BACKOFF_MIN_S", 0.01)
    monkeypatch.setattr(heartbeat, "BACKOFF_MAX_S", 0.02)
    calls = {"n": 0}

    async def _boom(client):
        calls["n"] += 1
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(heartbeat, "beat_once", _boom)
    stop = asyncio.Event()
    task = asyncio.create_task(heartbeat.run_heartbeat(stop))
    for _ in range(200):
        if calls["n"] >= 2:
            break
        await asyncio.sleep(0.01)
    stop.set()
    await asyncio.wait_for(task, timeout=3)

    assert calls["n"] >= 2  # 실패해도 루프가 죽지 않는다


def test_heartbeat_updates_core_relay_freshness(monkeypatch):
    """edge /health 의 core_relay 판정은 무변경 — 수신 시각만 갱신된다."""
    from app.services import system_service

    monkeypatch.setattr(system_service, "_core_heartbeat_at", None)
    edge = TestClient(build_app("edge"), client=("127.0.0.1", 50000))
    monkeypatch.setenv("API_ROLE", "edge")

    before = edge.get("/health").json()["components"]["core_relay"]
    assert before["status"] == "unknown"

    assert edge.post("/internal/core-heartbeat").status_code == 204

    after = edge.get("/health").json()["components"]["core_relay"]
    assert after["status"] == "ok" and after["age_s"] < 60
