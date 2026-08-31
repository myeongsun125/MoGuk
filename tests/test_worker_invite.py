"""M-32 — 근로자 초대 발급 POST /admin/workers/invite. [새봄]

검증 대상 계약:
- 토큰 = secrets.token_urlsafe(32) **원값** 저장 — 소비 측 auth.activate 가
  `WHERE i.token = %(token)s` 로 원값 조회하므로 해시 저장 금지
- expires_at = now() + 72h
- emp_no 중복: 미활성 → 재초대(기존 미사용 초대 만료 + 신규 1건) / 활성 → 409
- admin_events 1행: actor=ADMIN_ACTOR_UNAUTHENTICATED, target_type='worker',
  action='worker_invited', detail=emp_no
- invite_url = {BASE_URL}/activate?token=…
- 해석 1: 재초대 시 workers.invited_at 도 now() 갱신
- 해석 2: emp_no 미지정·빈값 → 422, lang 이 001 CHECK 집합 밖 → 422
"""

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import auth as auth_service
from app.services import invites
from app.services.risk_reports import ADMIN_ACTOR_UNAUTHENTICATED

client = TestClient(app, client=("127.0.0.1", 50000))


class FakeCursor:
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.store["calls"].append((sql, params))
        self._last = sql

    def fetchone(self):
        for needle, value in self.store.get("rows", []):
            if needle in self._last:
                return value
        return (self.store.get("default_id", 1),)


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


# 워커 조회 결과 스텁 — (id, activated_at)
NEW_WORKER = [("SELECT id, activated_at FROM workers", None),
              ("INSERT INTO workers", (11,))]
PENDING_WORKER = [("SELECT id, activated_at FROM workers", (7, None))]
ACTIVE_WORKER = [("SELECT id, activated_at FROM workers", (7, "2026-08-30T00:00:00+09:00"))]


@pytest.fixture(autouse=True)
def _base_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/test")
    monkeypatch.setenv("API_ROLE", "core")
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("TENANT_SLUG", raising=False)


# ── 발급 201 · invite_url 형식 ────────────────────────────

def test_invite_creates_worker_and_returns_url(monkeypatch):
    store = _store(rows=NEW_WORKER)
    monkeypatch.setattr(invites.tenancy, "connect", fake_connect(store))

    r = client.post("/api/v1/admin/workers/invite",
                    json={"name": "응웬반아", "emp_no": "A-001", "lang": "vi"})

    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"invite_url"}
    m = re.fullmatch(r"http://localhost/activate\?token=([A-Za-z0-9_-]+)", body["invite_url"])
    assert m, body["invite_url"]
    assert len(m.group(1)) >= 40                       # token_urlsafe(32) → 43자
    assert store["commits"] == 1 and store["connects"] == 1

    w = _params_for(store, "INSERT INTO workers")[0]
    assert w == {"name": "응웬반아", "emp_no": "A-001", "lang": "vi"}
    assert "invited_at" in [s for s in _sqls(store) if "INSERT INTO workers" in s][0]


def test_invite_url_uses_base_url_env(monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://moguk.example.com/")   # 끝 슬래시 포함
    store = _store(rows=NEW_WORKER)
    monkeypatch.setattr(invites.tenancy, "connect", fake_connect(store))

    r = client.post("/api/v1/admin/workers/invite",
                    json={"name": "n", "emp_no": "A-002", "lang": "in"})

    assert r.json()["invite_url"].startswith("https://moguk.example.com/activate?token=")
    assert "//activate" not in r.json()["invite_url"]              # 중복 슬래시 없음


def test_token_is_stored_raw_not_hashed(monkeypatch):
    """소비 측(auth.activate)이 원값 조회 — 해시 저장하면 활성화가 깨진다."""
    store = _store(rows=NEW_WORKER)
    monkeypatch.setattr(invites.tenancy, "connect", fake_connect(store))

    r = client.post("/api/v1/admin/workers/invite",
                    json={"name": "n", "emp_no": "A-003", "lang": "vi"})

    url_token = r.json()["invite_url"].split("token=")[1]
    stored = _params_for(store, "INSERT INTO invites")[0]["token"]
    assert stored == url_token                                     # 저장값 == 발급값
    assert not stored.startswith("pbkdf2")                         # 해시 형식 아님


# ── 만료 72h ──────────────────────────────────────────────

def test_expires_at_is_now_plus_72h(monkeypatch):
    store = _store(rows=NEW_WORKER)
    monkeypatch.setattr(invites.tenancy, "connect", fake_connect(store))
    client.post("/api/v1/admin/workers/invite",
                json={"name": "n", "emp_no": "A-004", "lang": "vi"})

    sql = [s for s in _sqls(store) if "INSERT INTO invites" in s][0]
    assert "now() + (%(ttl_h)s || ' hours')::interval" in sql
    assert _params_for(store, "INSERT INTO invites")[0]["ttl_h"] == 72
    assert invites.INVITE_TTL_H == 72


# ── emp_no 중복 ───────────────────────────────────────────

def test_reinvite_expires_pending_and_issues_new(monkeypatch):
    """미활성 중복 → 기존 미사용 초대 만료 + 신규 1건. 워커 신규 INSERT 없음."""
    store = _store(rows=PENDING_WORKER)
    monkeypatch.setattr(invites.tenancy, "connect", fake_connect(store))

    r = client.post("/api/v1/admin/workers/invite",
                    json={"name": "n", "emp_no": "A-005", "lang": "vi"})

    assert r.status_code == 201
    sqls = _sqls(store)
    assert not any("INSERT INTO workers" in s for s in sqls)       # 기존 워커 재사용
    exp = [s for s in sqls if "UPDATE invites SET expires_at = now()" in s][0]
    assert "used_at IS NULL" in exp and "expires_at > now()" in exp
    assert _params_for(store, "UPDATE invites SET expires_at")[0] == {"worker_id": 7}
    assert len([s for s in sqls if "INSERT INTO invites" in s]) == 1   # 신규 정확히 1건
    assert _params_for(store, "INSERT INTO invites")[0]["worker_id"] == 7


def test_reinvite_touches_invited_at(monkeypatch):
    """해석 1 — 재초대 시 workers.invited_at 갱신."""
    store = _store(rows=PENDING_WORKER)
    monkeypatch.setattr(invites.tenancy, "connect", fake_connect(store))
    client.post("/api/v1/admin/workers/invite",
                json={"name": "n", "emp_no": "A-006", "lang": "vi"})

    touch = [s for s in _sqls(store) if "UPDATE workers SET invited_at = now()" in s]
    assert len(touch) == 1
    assert _params_for(store, "UPDATE workers SET invited_at")[0] == {"id": 7}


def test_active_worker_returns_409(monkeypatch):
    store = _store(rows=ACTIVE_WORKER)
    monkeypatch.setattr(invites.tenancy, "connect", fake_connect(store))

    r = client.post("/api/v1/admin/workers/invite",
                    json={"name": "n", "emp_no": "A-007", "lang": "vi"})

    assert r.status_code == 409
    sqls = _sqls(store)
    assert not any("INSERT INTO invites" in s for s in sqls)
    assert not any("INSERT INTO admin_events" in s for s in sqls)
    assert store["commits"] == 0                                   # 롤백 — 부분 기록 없음


def test_worker_lookup_locks_row(monkeypatch):
    """emp_no UNIQUE 동시 재초대 경합 — 조회 시 행 잠금."""
    store = _store(rows=PENDING_WORKER)
    monkeypatch.setattr(invites.tenancy, "connect", fake_connect(store))
    client.post("/api/v1/admin/workers/invite",
                json={"name": "n", "emp_no": "A-008", "lang": "vi"})
    assert "FOR UPDATE" in [s for s in _sqls(store) if "SELECT id, activated_at" in s][0]


# ── admin_events 1행 ──────────────────────────────────────

def test_admin_events_row_recorded(monkeypatch):
    store = _store(rows=NEW_WORKER)
    monkeypatch.setattr(invites.tenancy, "connect", fake_connect(store))
    client.post("/api/v1/admin/workers/invite",
                json={"name": "n", "emp_no": "A-009", "lang": "in"})

    rows = _params_for(store, "INSERT INTO admin_events")
    assert len(rows) == 1
    ev = rows[0]
    assert ev["actor"] == ADMIN_ACTOR_UNAUTHENTICATED == "admin:unauthenticated"
    assert ev["target_type"] == "worker" and ev["target_id"] == 11
    assert ev["action"] == "worker_invited" and ev["detail"] == "A-009"
    assert ev["from_state"] is None and ev["to_state"] is None
    assert set(ev) == {"actor", "target_type", "target_id", "action",
                       "from_state", "to_state", "detail"}


def test_no_new_actor_literal():
    """M-15b — actor 리터럴 주입 지점은 risk_reports.py 1곳뿐."""
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    out = subprocess.run(["git", "grep", "-n", "admin:unauthenticated", "--", "backend"],
                         cwd=root, capture_output=True, text=True, encoding="utf-8"
                         ).stdout.strip().splitlines()
    assert len(out) == 1, out
    assert out[0].startswith("backend/app/services/risk_reports.py:")


# ── 해석 2: 요청 형식 422 ─────────────────────────────────

@pytest.mark.parametrize(
    "payload",
    [
        {"name": "n", "emp_no": "", "lang": "vi"},        # emp_no 빈값
        {"name": "n", "emp_no": "   ", "lang": "vi"},     # 공백뿐
        {"name": "n", "lang": "vi"},                      # emp_no 미지정
        {"name": "", "emp_no": "A-1", "lang": "vi"},      # name 빈값(001 NOT NULL)
        {"name": "n", "emp_no": "A-1", "lang": "ko"},     # 001 CHECK 집합 밖
        {"name": "n", "emp_no": "A-1", "lang": "en"},
        {"name": "n", "emp_no": "A-1"},                   # lang 미지정
    ],
)
def test_invalid_request_returns_422(monkeypatch, payload):
    def _boom(*a, **k):
        pytest.fail("검증 실패인데 저장소를 호출했다")

    monkeypatch.setattr(invites.tenancy, "connect", _boom)
    assert client.post("/api/v1/admin/workers/invite", json=payload).status_code == 422


def test_lang_values_match_001_check():
    assert invites.LANG_VALUES == ("vi", "in")


# ── 소비 측 왕복 정합 ─────────────────────────────────────

def test_issued_token_is_consumable_by_activate(monkeypatch):
    """발급 토큰 → auth.activate 왕복. 소비 측 SQL 이 원값으로 조회한다."""
    issue_store = _store(rows=NEW_WORKER)
    monkeypatch.setattr(invites.tenancy, "connect", fake_connect(issue_store))
    url = client.post("/api/v1/admin/workers/invite",
                      json={"name": "n", "emp_no": "A-010", "lang": "vi"}).json()["invite_url"]
    token = url.split("token=")[1]

    import datetime

    future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=72)
    act_store = _store(rows=[
        ("SELECT i.token, i.worker_id", (token, 11, future, None, 11)),
    ])
    act_store["rowcount"] = 1

    class Cur(FakeCursor):
        rowcount = 1

    monkeypatch.setattr(FakeConn, "cursor", lambda self: Cur(self.store))
    monkeypatch.setattr(auth_service.tenancy, "connect", fake_connect(act_store))
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-m32-roundtrip")

    out = auth_service.activate(token, "123456")

    assert set(out) == {"jwt", "refresh"}
    assert _params_for(act_store, "SELECT i.token, i.worker_id")[0] == {"token": token}
    assert _params_for(act_store, "UPDATE invites SET used_at")[0] == {"token": token}


# ── M-32b / M-08b ④: 신원·서버 도출 필드 가드 (판정 ②c) ──
# IDENTITY_FIELDS 11종 중 초대 본문에 섞일 법한 것들을 실물 상수에서 뽑아 쓴다.

GOOD = {"name": "n", "emp_no": "A-9", "lang": "vi"}


@pytest.mark.parametrize(
    "extra",
    [
        {"actor": "admin:1"},
        {"tenant": "acme"},
        {"tenant_slug": "acme"},
        {"admin_id": 1},
        {"worker_id": 7},
        {"id": 3},
        {"status": "activated"},
        {"actor": "admin:1", "tenant": "acme"},   # 복수 — fields 에 정렬되어 둘 다
    ],
)
def test_identity_fields_in_body_return_400(monkeypatch, extra):
    """M-08b ④ — 무시가 아니라 400. 저장소는 호출되지 않는다."""
    def _boom(*a, **k):
        pytest.fail("가드가 400 을 내야 하는데 저장소를 호출했다")

    monkeypatch.setattr(invites.tenancy, "connect", _boom)
    r = client.post("/api/v1/admin/workers/invite", json={**GOOD, **extra})

    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "forbidden_fields"
    assert detail["fields"] == sorted(extra)          # 걸린 필드 전부 회신


def test_guard_uses_the_shared_identity_field_set():
    """가드 대상 집합은 M-08b ④ 단일 상수 — 초대용으로 새로 만들지 않는다."""
    from app.services.risk_reports import IDENTITY_FIELDS, identity_fields_in

    assert identity_fields_in({**GOOD, "actor": "x"}) == ["actor"]
    assert "actor" in IDENTITY_FIELDS and "tenant" in IDENTITY_FIELDS


def test_clean_body_still_returns_201(monkeypatch):
    """가드 추가가 정상 경로를 막지 않는다 — 여분 필드 없는 본문은 그대로 201."""
    store = _store(rows=NEW_WORKER)
    monkeypatch.setattr(invites.tenancy, "connect", fake_connect(store))

    r = client.post("/api/v1/admin/workers/invite", json=GOOD)

    assert r.status_code == 201, r.text
    assert set(r.json()) == {"invite_url"}


@pytest.mark.asyncio
async def test_edge_identity_guard_fires_before_relay_enqueue(monkeypatch):
    """edge 에서도 400 — 릴레이 큐에 적재되지 않는다(가드가 분기보다 앞)."""
    import asyncio

    import httpx

    from app.main import build_app
    from app.services import relay

    monkeypatch.setenv("API_ROLE", "edge")
    monkeypatch.setenv("RELAY_EDGE_WAIT_S", "0.2")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    relay.queue.reset()
    edge_app = build_app("edge")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=edge_app), base_url="http://edge"
    ) as edge_client:
        r = await asyncio.wait_for(
            edge_client.post("/api/v1/admin/workers/invite", json={**GOOD, "actor": "admin:1"}),
            timeout=5,
        )

    assert r.status_code == 400, r.text
    assert r.json()["detail"]["fields"] == ["actor"]
    assert relay.queue.snapshot() == []      # 큐 미적재 — 보류·504 로 흘러가지 않는다
    relay.queue.reset()


@pytest.mark.asyncio
async def test_edge_clean_body_still_enqueues(monkeypatch):
    """대조군 — 정상 본문은 edge 에서 여전히 큐에 적재된다(가드가 과잉 차단하지 않는다)."""
    import asyncio

    import httpx

    from app.main import build_app
    from app.services import relay

    monkeypatch.setenv("API_ROLE", "edge")
    monkeypatch.setenv("RELAY_HOLD_S", "3")
    monkeypatch.setenv("RELAY_EDGE_WAIT_S", "5")
    relay.queue.reset()
    edge_app = build_app("edge")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=edge_app), base_url="http://edge"
    ) as edge_client:
        task = asyncio.create_task(
            edge_client.post("/api/v1/admin/workers/invite", json=GOOD)
        )
        pend = await edge_client.get("/internal/relay/pending")
        items = pend.json()["items"]
        assert len(items) == 1 and items[0]["body"] == GOOD
        await edge_client.post(
            f"/internal/relay/{items[0]['request_id']}/respond",
            json={"status_code": 201, "body": {"invite_url": "http://localhost/activate?token=t"}},
        )
        resp = await task

    assert resp.status_code == 201
    relay.queue.reset()
