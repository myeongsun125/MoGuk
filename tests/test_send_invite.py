"""send-invite 파트1 — POST /admin/workers/{id}/send-invite (총괄 계약 확정 0902). [새봄]

검증 대상 계약:
- 요청 {channel:'kakao_link'} → 201 {share_url} — URL 형태는 기존 invite_url 과 동일
  (build_invite_url 재사용: {BASE_URL}/activate?token=…)
- channel 은 kakao_link 만 유효 — sms 등 그 외 값·미지정은 pydantic 422 (sms 는 로드맵)
- 발급 규칙 재사용: 미사용 초대 즉시 만료 + 신규 1건, TTL 72h, invited_at 갱신(해석 1),
  admin_events 1행(action='worker_invited')
- 워커 없음 404, 이미 활성 409(기존 규칙 유지), 가드는 invite_worker 동형(M-08b ④)

fake cursor(test_worker_invite 동형) — 네트워크·DB 실호출 없음.
"""

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
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


# 워커 조회 결과 스텁 — (id, emp_no, activated_at)
PENDING = [("SELECT id, emp_no, activated_at FROM workers", (7, "A-001", None))]
MISSING = [("SELECT id, emp_no, activated_at FROM workers", None)]
ACTIVE = [("SELECT id, emp_no, activated_at FROM workers",
           (7, "A-001", "2026-08-30T00:00:00+09:00"))]

KAKAO = {"channel": "kakao_link"}


@pytest.fixture(autouse=True)
def _base_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/test")
    monkeypatch.setenv("API_ROLE", "core")
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("TENANT_SLUG", raising=False)


# ── kakao_link 정상 발급 → share_url 형태 ─────────────────

def test_send_invite_returns_share_url(monkeypatch):
    store = _store(rows=PENDING)
    monkeypatch.setattr(invites.tenancy, "connect", fake_connect(store))

    r = client.post("/api/v1/admin/workers/7/send-invite", json=KAKAO)

    assert r.status_code == 201, r.text
    body = r.json()
    assert set(body) == {"share_url"}
    m = re.fullmatch(r"http://localhost/activate\?token=([A-Za-z0-9_-]+)", body["share_url"])
    assert m, body["share_url"]
    assert len(m.group(1)) >= 40                       # token_urlsafe(32) → 43자
    assert store["commits"] == 1 and store["connects"] == 1


def test_share_url_uses_base_url_env_like_invite_url(monkeypatch):
    """share_url 은 기존 invite_url 과 동일 형태 — BASE_URL 조합기 재사용."""
    monkeypatch.setenv("BASE_URL", "https://moguk.example.com/")   # 끝 슬래시 포함
    store = _store(rows=PENDING)
    monkeypatch.setattr(invites.tenancy, "connect", fake_connect(store))

    url = client.post("/api/v1/admin/workers/7/send-invite", json=KAKAO).json()["share_url"]

    assert url.startswith("https://moguk.example.com/activate?token=")
    assert "//activate" not in url                                 # 중복 슬래시 없음


def test_token_stored_raw_matches_share_url(monkeypatch):
    """소비 측(auth.activate)은 원값 조회 — 저장값 == share_url 토큰."""
    store = _store(rows=PENDING)
    monkeypatch.setattr(invites.tenancy, "connect", fake_connect(store))

    url = client.post("/api/v1/admin/workers/7/send-invite", json=KAKAO).json()["share_url"]

    stored = _params_for(store, "INSERT INTO invites")[0]["token"]
    assert stored == url.split("token=")[1]


# ── 재발급 규칙 재사용 (기존 만료 + 신규 1건 + 72h + invited_at) ──

def test_resend_expires_pending_and_issues_one(monkeypatch):
    store = _store(rows=PENDING)
    monkeypatch.setattr(invites.tenancy, "connect", fake_connect(store))

    client.post("/api/v1/admin/workers/7/send-invite", json=KAKAO)

    sqls = _sqls(store)
    exp = [s for s in sqls if "UPDATE invites SET expires_at = now()" in s][0]
    assert "used_at IS NULL" in exp and "expires_at > now()" in exp
    assert _params_for(store, "UPDATE invites SET expires_at")[0] == {"worker_id": 7}
    assert len([s for s in sqls if "INSERT INTO invites" in s]) == 1   # 신규 정확히 1건
    assert _params_for(store, "INSERT INTO invites")[0]["worker_id"] == 7
    assert not any("INSERT INTO workers" in s for s in sqls)           # 워커 신규 생성 없음


def test_resend_keeps_72h_ttl_and_touches_invited_at(monkeypatch):
    store = _store(rows=PENDING)
    monkeypatch.setattr(invites.tenancy, "connect", fake_connect(store))

    client.post("/api/v1/admin/workers/7/send-invite", json=KAKAO)

    sql = [s for s in _sqls(store) if "INSERT INTO invites" in s][0]
    assert "now() + (%(ttl_h)s || ' hours')::interval" in sql
    assert _params_for(store, "INSERT INTO invites")[0]["ttl_h"] == 72
    touch = [s for s in _sqls(store) if "UPDATE workers SET invited_at = now()" in s]
    assert len(touch) == 1                                             # 해석 1
    assert _params_for(store, "UPDATE workers SET invited_at")[0] == {"id": 7}


def test_worker_lookup_locks_row(monkeypatch):
    """동시 재발급 경합 — id 조회도 행 잠금(emp_no 경로 동형)."""
    store = _store(rows=PENDING)
    monkeypatch.setattr(invites.tenancy, "connect", fake_connect(store))
    client.post("/api/v1/admin/workers/7/send-invite", json=KAKAO)
    assert "FOR UPDATE" in [s for s in _sqls(store) if "SELECT id, emp_no, activated_at" in s][0]


# ── admin_events 1행 ──────────────────────────────────────

def test_admin_events_row_recorded(monkeypatch):
    store = _store(rows=PENDING)
    monkeypatch.setattr(invites.tenancy, "connect", fake_connect(store))

    client.post("/api/v1/admin/workers/7/send-invite", json=KAKAO)

    rows = _params_for(store, "INSERT INTO admin_events")
    assert len(rows) == 1
    ev = rows[0]
    assert ev["actor"] == ADMIN_ACTOR_UNAUTHENTICATED
    assert ev["target_type"] == "worker" and ev["target_id"] == 7
    assert ev["action"] == "worker_invited" and ev["detail"] == "A-001"


# ── 워커 없음 404 · 활성 409 ──────────────────────────────

def test_missing_worker_returns_404(monkeypatch):
    store = _store(rows=MISSING)
    monkeypatch.setattr(invites.tenancy, "connect", fake_connect(store))

    r = client.post("/api/v1/admin/workers/999/send-invite", json=KAKAO)

    assert r.status_code == 404, r.text
    sqls = _sqls(store)
    assert not any("INSERT INTO invites" in s for s in sqls)
    assert not any("INSERT INTO admin_events" in s for s in sqls)
    assert store["commits"] == 0                                   # 롤백 — 부분 기록 없음


def test_active_worker_returns_409(monkeypatch):
    """활성 워커 재발급 금지 — 기존 초대 발급 규칙(409) 유지."""
    store = _store(rows=ACTIVE)
    monkeypatch.setattr(invites.tenancy, "connect", fake_connect(store))

    r = client.post("/api/v1/admin/workers/7/send-invite", json=KAKAO)

    assert r.status_code == 409, r.text
    assert not any("INSERT INTO invites" in s for s in _sqls(store))
    assert store["commits"] == 0


# ── channel 검증 — kakao_link 만 유효 ─────────────────────

@pytest.mark.parametrize("payload", [
    {"channel": "sms"},              # 로드맵 — 이번 범위 아님
    {"channel": "email"},
    {"channel": ""},
    {},                              # channel 미지정
])
def test_invalid_channel_returns_422(monkeypatch, payload):
    def _boom(*a, **k):
        pytest.fail("검증 실패인데 저장소를 호출했다")

    monkeypatch.setattr(invites.tenancy, "connect", _boom)
    r = client.post("/api/v1/admin/workers/7/send-invite", json=payload)
    assert r.status_code == 422, r.text


# ── M-08b ④ 가드 — invite_worker 동형 ─────────────────────

def test_identity_field_in_body_returns_400(monkeypatch):
    def _boom(*a, **k):
        pytest.fail("가드가 400 을 내야 하는데 저장소를 호출했다")

    monkeypatch.setattr(invites.tenancy, "connect", _boom)
    r = client.post("/api/v1/admin/workers/7/send-invite",
                    json={**KAKAO, "worker_id": 7})

    assert r.status_code == 400, r.text
    assert r.json()["detail"]["fields"] == ["worker_id"]
