"""승인큐 목록 API — GET /admin/glossary · /admin/unanswered (총괄 확정 0830). [새봄]

이번 범위 = 목록 조회만. 전이(approve/reject)는 감사 이벤트 수용처 판정(0-c) 후 별도.

검증 대상 계약:
- 001 정본 필드 전사 (glossary·unanswered_queue ⋈ questions)
- 기본 필터: glossary=draft / unanswered=open. ?status= 빈 값 = 전체
- 읽기 전용 — SELECT 만, 커밋·쓰기 0
- M-28c 패턴: edge role 은 릴레이 경유(빈 body), 쿼리스트링 복원
- 3중 대조: §3 등재 문안 ↔ 계약 표 ↔ 구현 상수
"""

import asyncio
import re
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app, build_app
from app.services import approval, relay
from app.workers import relay_poller

client = TestClient(app, client=("127.0.0.1", 50000))

AT = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
AT_ISO = AT.isoformat()


class FakeCursor:
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.store["calls"].append((sql, params))

    def fetchall(self):
        return self.store.get("rows", [])


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


@pytest.fixture(autouse=True)
def _base_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/test")
    monkeypatch.setenv("API_ROLE", "core")
    monkeypatch.delenv("TENANT_SLUG", raising=False)
    relay.queue.reset()
    yield
    relay.queue.reset()


GLOSSARY_ROW = (7, "척", "mâm cặp", "cekam", "선반 고정 장치", "draft", None, None, None)
UNANSWERED_ROW = (3, 41, "open", "프레스 점검 주기는?", "vi", AT, None, None)


# ── 001 정본 필드 전사 ────────────────────────────────────

def test_glossary_row_uses_001_field_names(monkeypatch):
    store = _store(rows=[GLOSSARY_ROW])
    monkeypatch.setattr(approval.tenancy, "connect", fake_connect(store))

    out = approval.list_glossary()

    assert len(out) == 1
    assert tuple(out[0]) == approval.GLOSSARY_KEYS
    assert out[0] == {
        "id": 7, "term_ko": "척", "term_vi": "mâm cặp", "term_in": "cekam",
        "note": "선반 고정 장치", "status": "draft",
        "source_question_id": None, "approved_by": None, "approved_at": None,
    }
    # 001 에 없는 컬럼을 지어내지 않는다
    assert "created_at" not in out[0] and "lang" not in out[0]


def test_unanswered_row_joins_questions(monkeypatch):
    store = _store(rows=[UNANSWERED_ROW])
    monkeypatch.setattr(approval.tenancy, "connect", fake_connect(store))

    out = approval.list_unanswered()

    assert tuple(out[0]) == approval.UNANSWERED_KEYS
    assert out[0]["question"] == "프레스 점검 주기는?" and out[0]["lang"] == "vi"
    assert out[0]["question_created_at"] == AT_ISO
    sql = _sqls(store)[0]
    assert "FROM unanswered_queue u" in sql and "JOIN questions q ON q.id = u.question_id" in sql


def test_status_check_sets_match_001():
    assert approval.GLOSSARY_STATUS == ("draft", "approved", "rejected")
    assert approval.UNANSWERED_STATUS == ("open", "answered")
    assert approval.GLOSSARY_DEFAULT_STATUS == "draft"
    assert approval.UNANSWERED_DEFAULT_STATUS == "open"


# ── 필터 ──────────────────────────────────────────────────

@pytest.mark.parametrize(
    "fn,default", [(approval.list_glossary, "draft"), (approval.list_unanswered, "open")]
)
def test_default_filter_is_applied(monkeypatch, fn, default):
    store = _store()
    monkeypatch.setattr(approval.tenancy, "connect", fake_connect(store))
    fn()
    assert store["calls"][0][1] == {"status": default}


@pytest.mark.parametrize("blank", [None, ""])
def test_blank_status_means_all(monkeypatch, blank):
    """?status= 빈 값 → NULL 로 넘겨 전체 조회 (빈 문자열로 0건이 되는 함정 방지)."""
    store = _store()
    monkeypatch.setattr(approval.tenancy, "connect", fake_connect(store))
    approval.list_glossary(blank)
    assert store["calls"][0][1] == {"status": None}
    assert "%(status)s::text IS NULL OR" in _sqls(store)[0]


def test_explicit_status_passes_through(monkeypatch):
    store = _store()
    monkeypatch.setattr(approval.tenancy, "connect", fake_connect(store))
    approval.list_glossary("approved")
    assert store["calls"][0][1] == {"status": "approved"}


# ── 읽기 전용 ─────────────────────────────────────────────

@pytest.mark.parametrize("fn", [approval.list_glossary, approval.list_unanswered])
def test_list_is_read_only(monkeypatch, fn):
    store = _store()
    monkeypatch.setattr(approval.tenancy, "connect", fake_connect(store))
    fn()
    for sql in _sqls(store):
        assert sql.strip().split()[0].upper() == "SELECT", sql
    assert store["commits"] == 0


def test_transitions_not_implemented_yet():
    """전이는 감사 이벤트 수용처 판정(0-c) 후 — 이벤트 없이 상태만 바꾸는 구현을 두지 않는다."""
    assert not hasattr(approval, "approve_glossary")
    assert not hasattr(approval, "reject_glossary")


def test_no_new_admin_actor_literal():
    """M-15b — actor 리터럴 신규 도입 0. 주입 지점은 risk_reports.py 상수 1곳뿐."""
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    out = subprocess.run(
        ["git", "grep", "-n", "admin:unauthenticated", "--", "backend"],
        cwd=root, capture_output=True, text=True, encoding="utf-8",
    ).stdout.strip().splitlines()
    assert len(out) == 1, out
    assert out[0].startswith("backend/app/services/risk_reports.py:")


# ── 엔드포인트 · M-28c edge 분기 ──────────────────────────

def test_glossary_endpoint_core(monkeypatch):
    store = _store(rows=[GLOSSARY_ROW])
    monkeypatch.setattr(approval.tenancy, "connect", fake_connect(store))

    r = client.get("/api/v1/admin/glossary")

    assert r.status_code == 200
    assert tuple(r.json()[0]) == approval.GLOSSARY_KEYS
    assert store["calls"][0][1] == {"status": "draft"}


def test_unanswered_endpoint_core_with_status(monkeypatch):
    store = _store(rows=[UNANSWERED_ROW])
    monkeypatch.setattr(approval.tenancy, "connect", fake_connect(store))

    r = client.get("/api/v1/admin/unanswered?status=answered")

    assert r.status_code == 200
    assert store["calls"][0][1] == {"status": "answered"}


@pytest.mark.parametrize(
    "url,relay_path",
    [
        ("/api/v1/admin/glossary", "/api/v1/admin/glossary?status=draft"),
        ("/api/v1/admin/glossary?status=approved", "/api/v1/admin/glossary?status=approved"),
        ("/api/v1/admin/unanswered", "/api/v1/admin/unanswered?status=open"),
    ],
)
@pytest.mark.asyncio
async def test_edge_lists_go_through_relay(monkeypatch, url, relay_path):
    """M-28c 패턴 — edge 는 DB 자격이 없으므로 릴레이 경유, 쿼리스트링 온전 전달."""
    monkeypatch.setenv("API_ROLE", "edge")
    monkeypatch.setenv("RELAY_HOLD_S", "3")
    monkeypatch.setenv("RELAY_EDGE_WAIT_S", "5")
    app_edge = build_app("edge")
    payload = [{"id": 1}]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_edge), base_url="http://edge"
    ) as c:
        task = asyncio.create_task(c.get(url))
        pend = await c.get("/internal/relay/pending")
        items = pend.json()["items"]
        assert len(items) == 1
        assert items[0]["method"] == "GET" and items[0]["path"] == relay_path
        assert items[0]["body"] == {}
        await c.post(f"/internal/relay/{items[0]['request_id']}/respond",
                     json={"status_code": 200, "body": payload})
        r = await task

    assert r.status_code == 200 and r.json() == payload


@pytest.mark.parametrize(
    "path,fn_name,expected_status",
    [
        ("/api/v1/admin/glossary", "list_glossary", None),
        ("/api/v1/admin/glossary?status=draft", "list_glossary", "draft"),
        ("/api/v1/admin/unanswered?status=open", "list_unanswered", "open"),
    ],
)
def test_poller_dispatches_lists(monkeypatch, path, fn_name, expected_status):
    seen = {}

    def _fn(status=None):
        seen["status"] = status
        return []

    monkeypatch.setattr("app.services.approval." + fn_name, _fn)
    status, body = relay_poller.dispatch("GET", path, {})
    assert (status, body) == (200, [])
    assert seen["status"] == expected_status


def test_poller_unregistered_admin_get_still_404():
    status, _ = relay_poller.dispatch("GET", "/api/v1/admin/nope", {})
    assert status == 404


# ── 3중 대조: §3 등재 문안 ↔ 구현 상수 ─────────────────────

def _skeleton_line(prefix: str) -> str:
    import io
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    text = io.open(root / "docs/skeleton-v3.md", encoding="utf-8").read()
    lines = [l for l in text.split("\n") if l.startswith(prefix)]
    assert len(lines) == 1, lines
    return lines[0]


def _listed_keys(line: str) -> list[str]:
    return [k.strip() for k in re.search(r"\[\{(.*?)\}\]", line).group(1).split(",")]


def test_skeleton_glossary_matches_implementation():
    line = _skeleton_line("GET  /admin/glossary")
    assert tuple(_listed_keys(line)) == approval.GLOSSARY_KEYS
    for v in approval.GLOSSARY_STATUS:
        assert f"'{v}'" in line
    assert "기본 필터 draft" in line
    assert "created_at 컬럼 없음" in line          # 001 에 없는 필드를 계약에 넣지 않음을 명시


def test_skeleton_unanswered_matches_implementation():
    line = _skeleton_line("GET  /admin/unanswered")
    assert tuple(_listed_keys(line)) == approval.UNANSWERED_KEYS
    for v in approval.UNANSWERED_STATUS:
        assert f"'{v}'" in line
    assert "기본 필터 open" in line
    assert "M-05a 2종" in line and "시스템 오류 미적재" in line
