"""승인큐 목록 API — GET /admin/glossary · /admin/unanswered (총괄 확정 0830). [새봄]

범위 = 목록 조회 + 전이(approve/reject, M-08d) + 감사 로그 조회(GET /admin/events).

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
from app.services import admin_events, approval, relay
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


def test_transitions_always_record_an_event():
    """이벤트 없이 상태만 바꾸는 경로는 두지 않는다 — 전이 구현은 record 호출을 반드시 거친다."""
    import inspect

    src = inspect.getsource(approval._transition)
    assert "admin_events.record(" in src
    for fn in (approval.approve_glossary, approval.reject_glossary):
        assert "_transition(" in inspect.getsource(fn)


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


# ── M-08d (a) admin_events — append-only ──────────────────

def test_admin_events_has_no_update_or_delete_path():
    """append-only — 모듈·마이그레이션 어디에도 admin_events 대상 UPDATE/DELETE 가 없다."""
    import re
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    out = subprocess.run(
        ["git", "grep", "-nE", r"(UPDATE|DELETE)[[:space:]]+(FROM[[:space:]]+)?admin_events",
         "--", "backend", "db"],
        cwd=root, capture_output=True, text=True, encoding="utf-8",
    ).stdout.strip()
    assert out == "", out
    # 모듈이 들고 있는 SQL 상수에 INSERT/SELECT 외 동사가 없어야 한다
    for name in dir(admin_events):
        val = getattr(admin_events, name)
        if not name.startswith("_") or name.startswith("__"):   # 던더(__cached__ 등) 제외
            continue
        if isinstance(val, str) and "admin_events" in val:
            head = val.strip().split()[0].upper()
            assert head in ("INSERT", "SELECT"), (name, head)


def test_admin_events_record_inserts_one_row():
    calls = []

    class Cur:
        def execute(self, sql, params=None):
            calls.append((sql, params))

    admin_events.record(
        Cur(), actor="admin:x", target_type="glossary", target_id=7,
        action="glossary_approved", from_state="draft", to_state="approved", detail="사유",
    )
    assert len(calls) == 1
    sql, params = calls[0]
    assert sql.strip().startswith("INSERT INTO admin_events")
    assert params == {
        "actor": "admin:x", "target_type": "glossary", "target_id": 7,
        "action": "glossary_approved", "from_state": "draft",
        "to_state": "approved", "detail": "사유",
    }


def test_001_defines_admin_events_and_keeps_existing_tables():
    """001 에 admin_events 1문 추가 — 기존 CREATE TABLE 정의 무접촉."""
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    ddl = (root / "db/migrations/001_tenant_template.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS admin_events (" in ddl
    for col in ("actor text", "target_type text NOT NULL", "target_id int NOT NULL",
                "action text NOT NULL", "from_state text", "to_state text", "detail text",
                "created_at timestamptz NOT NULL DEFAULT now()"):
        assert col in ddl, col

    base = subprocess.run(["git", "show", "origin/main:db/migrations/001_tenant_template.sql"],
                          cwd=root, capture_output=True).stdout.decode("utf-8")
    if base:                       # origin/main 을 못 읽는 환경이면 생략
        old = [l for l in base.split("\n") if l.startswith("CREATE TABLE")]
        new = [l for l in ddl.split("\n") if l.startswith("CREATE TABLE")]
        assert old == new, "기존 CREATE TABLE 정의가 변경됨"


# ── M-08d (b) 전이 ────────────────────────────────────────

def _t_store(status="draft"):
    return _store(rows=[("SELECT status FROM glossary", (status,))])


class StatusCursor(FakeCursor):
    def fetchone(self):
        for needle, value in self.store.get("rows", []):
            if needle in self.store["calls"][-1][0]:
                return value
        return None


def _patch_transition(monkeypatch, store):
    monkeypatch.setattr(approval.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(FakeConn, "cursor", lambda self: StatusCursor(self.store))


def test_approve_updates_snapshot_and_records_event(monkeypatch):
    store = _t_store("draft")
    _patch_transition(monkeypatch, store)

    out = approval.approve_glossary(7)

    assert out == {"id": 7, "status": "approved"}
    sqls = [c[0] for c in store["calls"]]
    up = [s for s in sqls if s.strip().upper().startswith("UPDATE")][0]
    assert "approved_at = now()" in up
    assert "approved_by" not in up                  # M-15b 판정 1 — integer FK 는 NULL 유지
    ev = [c[1] for c in store["calls"] if "INSERT INTO admin_events" in c[0]][0]
    assert ev["actor"] == "admin:unauthenticated"
    assert ev["target_type"] == "glossary" and ev["target_id"] == 7
    assert (ev["from_state"], ev["to_state"]) == ("draft", "approved")
    assert ev["action"] == "glossary_approved" and ev["detail"] is None
    assert store["commits"] == 1


def test_reject_preserves_note_in_event_detail_not_glossary_note(monkeypatch):
    store = _t_store("draft")
    _patch_transition(monkeypatch, store)

    out = approval.reject_glossary(7, "표기 오류 — 재검토 필요")

    assert out == {"id": 7, "status": "rejected"}
    up = [c[0] for c in store["calls"] if c[0].strip().upper().startswith("UPDATE")][0]
    assert "note" not in up                        # 용어 설명(note) 덮어쓰기 금지
    assert "approved_at" not in up                 # 반려는 승인 시각을 채우지 않는다
    ev = [c[1] for c in store["calls"] if "INSERT INTO admin_events" in c[0]][0]
    assert ev["detail"] == "표기 오류 — 재검토 필요"
    assert ev["action"] == "glossary_rejected" and ev["to_state"] == "rejected"


@pytest.mark.parametrize("current", ["approved", "rejected"])
@pytest.mark.parametrize("fn", [approval.approve_glossary, approval.reject_glossary])
def test_transition_only_from_draft(monkeypatch, current, fn):
    store = _t_store(current)
    _patch_transition(monkeypatch, store)

    with pytest.raises(approval.TransitionError):
        fn(7)
    assert not any(c[0].strip().upper().startswith("UPDATE") for c in store["calls"])
    assert not any("INSERT INTO admin_events" in c[0] for c in store["calls"])


def test_transition_missing_term(monkeypatch):
    store = _store(rows=[("SELECT status FROM glossary", None)])
    _patch_transition(monkeypatch, store)
    with pytest.raises(approval.TermNotFound):
        approval.approve_glossary(999)


def test_transition_endpoints(monkeypatch):
    store = _t_store("draft")
    _patch_transition(monkeypatch, store)
    r1 = client.post("/api/v1/admin/glossary/7/approve")
    assert r1.status_code == 200 and r1.json() == {"id": 7, "status": "approved"}

    store2 = _t_store("draft")
    _patch_transition(monkeypatch, store2)
    r2 = client.post("/api/v1/admin/glossary/7/reject", json={"note": "n"})
    assert r2.status_code == 200 and r2.json() == {"id": 7, "status": "rejected"}


def test_transition_endpoint_422_and_404(monkeypatch):
    _patch_transition(monkeypatch, _t_store("approved"))
    assert client.post("/api/v1/admin/glossary/7/approve").status_code == 422

    store = _store(rows=[("SELECT status FROM glossary", None)])
    _patch_transition(monkeypatch, store)
    assert client.post("/api/v1/admin/glossary/9/approve").status_code == 404


@pytest.mark.parametrize("field", ["actor", "admin_id", "status", "id"])
def test_identity_fields_rejected_on_transition(monkeypatch, field):
    def _boom(*a, **k):
        pytest.fail("거부돼야 하는데 저장소 호출됨")

    monkeypatch.setattr(approval.tenancy, "connect", _boom)
    for path in ("/api/v1/admin/glossary/7/approve", "/api/v1/admin/glossary/7/reject"):
        r = client.post(path, json={field: 1})
        assert r.status_code == 400, (path, r.status_code)
        assert field in r.json()["detail"]["fields"]


def test_no_new_actor_literal_after_m08d():
    """M-15b — admin_events 도입 후에도 actor 리터럴 주입 지점은 1곳뿐."""
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    out = subprocess.run(["git", "grep", "-n", "admin:unauthenticated", "--", "backend"],
                         cwd=root, capture_output=True, text=True, encoding="utf-8"
                         ).stdout.strip().splitlines()
    assert len(out) == 1, out
    assert out[0].startswith("backend/app/services/risk_reports.py:")


# ── M-08d (c) GET /admin/events ───────────────────────────

EVENT_ROW = (12, "admin:unauthenticated", "glossary", 7,
             "glossary_approved", "draft", "approved", None, AT)


def test_list_events_shape_and_keys(monkeypatch):
    store = _store(rows2=[EVENT_ROW])
    monkeypatch.setattr(admin_events.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(FakeCursor, "fetchall", lambda self: self.store.get("rows2", []))

    out = admin_events.list_events()

    assert len(out) == 1 and tuple(out[0]) == admin_events.EVENT_KEYS
    assert out[0]["created_at"] == AT_ISO
    assert out[0]["actor"] == "admin:unauthenticated"


def test_list_events_filters_and_defaults(monkeypatch):
    store = _store(rows2=[])
    monkeypatch.setattr(admin_events.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(FakeCursor, "fetchall", lambda self: self.store.get("rows2", []))

    admin_events.list_events()
    p = store["calls"][0][1]
    assert p == {"date": None, "target_type": None, "tz": "Asia/Seoul",
                 "report_type": admin_events.REPORT_TARGET_TYPE,   # M-36 report 행 사영 상수
                 "limit": admin_events.LIMIT_DEFAULT, "offset": 0}

    admin_events.list_events("2026-08-30", "glossary", 10, 5)
    p2 = store["calls"][1][1]
    assert p2["date"] == "2026-08-30" and p2["target_type"] == "glossary"
    assert p2["limit"] == 10 and p2["offset"] == 5


@pytest.mark.parametrize(
    "given,expected",
    [(None, 50), (0, 50), (-3, 50), (1, 1), (200, 200), (201, 200), (10_000, 200)],
)
def test_limit_clamped(given, expected):
    assert admin_events.clamp_limit(given) == expected


def test_offset_never_negative(monkeypatch):
    store = _store(rows2=[])
    monkeypatch.setattr(admin_events.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(FakeCursor, "fetchall", lambda self: self.store.get("rows2", []))
    admin_events.list_events(offset=-5)
    assert store["calls"][0][1]["offset"] == 0


def test_list_events_sql_shape(monkeypatch):
    store = _store(rows2=[])
    monkeypatch.setattr(admin_events.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(FakeCursor, "fetchall", lambda self: self.store.get("rows2", []))
    admin_events.list_events()

    sql = store["calls"][0][0]
    assert "ORDER BY created_at DESC" in sql               # 최신 우선 (M-36 — id 정렬 폐지)
    assert "ORDER BY id DESC" not in sql
    assert "LIMIT %(limit)s OFFSET %(offset)s" in sql
    assert "(created_at AT TIME ZONE %(tz)s)::date = %(date)s::date" in sql
    assert "%(date)s::text IS NULL OR" in sql              # 필터 미지정 = 전체
    assert sql.strip().split()[0].upper() == "SELECT"


# ── M-36 병합 조회 ────────────────────────────────────────

# 병합 결과에서 report 행이 갖는 모습 — id=risk_report_events.id, target_type='report',
# target_id=report_id, action 은 원값, detail 은 note(ack/resolve) 또는 null.
REPORT_EVENT_ROW = (34, "admin:unauthenticated", "report", 9,
                    "report_resolved", "acknowledged", "resolved", "현장 조치 완료", AT)
REPORT_EVENT_ROW_NULL_DETAIL = (35, "worker:3", "report", 9,
                                "reporter_confirmed", None, None, None, AT)


def _events_store(monkeypatch, rows):
    store = _store(rows2=rows)
    monkeypatch.setattr(admin_events.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(FakeCursor, "fetchall", lambda self: self.store.get("rows2", []))
    return store


def _outer_where(sql: str) -> str:
    """UNION 바깥(= 병합 결과에 걸리는) 절만 잘라낸다."""
    return sql[sql.index(") events"):]


def test_merged_report_rows_map_to_nine_keys(monkeypatch):
    """(a) report 행도 admin_events 행과 같은 9종 필드·순서로 나온다."""
    _events_store(monkeypatch, [REPORT_EVENT_ROW, REPORT_EVENT_ROW_NULL_DETAIL])

    out = admin_events.list_events()

    assert [tuple(r) for r in out] == [admin_events.EVENT_KEYS] * 2   # 키 이름·순서 무변경
    first, second = out
    assert first["id"] == 34                                  # 원본 테이블 id
    assert first["target_type"] == admin_events.REPORT_TARGET_TYPE == "report"
    assert first["target_id"] == 9                            # = report_id
    assert first["action"] == "report_resolved"               # 원값 (M-36 ②)
    assert first["detail"] == "현장 조치 완료"                  # = note
    assert first["actor"] == "admin:unauthenticated"
    assert (first["from_state"], first["to_state"]) == ("acknowledged", "resolved")
    assert first["created_at"] == AT_ISO
    assert second["detail"] is None                           # note 미지정 → null


def test_merge_sql_unions_both_tables_with_report_projection(monkeypatch):
    """(a) 병합 소스 2개와 report 사영이 SQL 에 있고, 저장 이중화는 없다."""
    store = _events_store(monkeypatch, [])
    admin_events.list_events()

    sql, params = store["calls"][0]
    assert "FROM admin_events" in sql and "FROM risk_report_events" in sql
    assert "UNION ALL" in sql
    assert "::text AS target_type" in sql                      # report 행 target_type 사영
    assert "report_id AS target_id" in sql                     # target_id = report_id
    assert params["report_type"] == admin_events.REPORT_TARGET_TYPE
    # 저장 이중화 없음 — 조회 경로에 INSERT/UPDATE 가 없다
    assert all(q.strip().split()[0].upper() == "SELECT" for q, _ in store["calls"])
    assert "risk_report_events" not in admin_events._INSERT   # 기록 규약 무접촉(M-08d)


def test_merge_orders_globally_by_created_at_desc(monkeypatch):
    """(b) 정렬은 병합 결과 전역에 3키(created_at, target_type, id) desc 로 걸린다."""
    store = _events_store(monkeypatch, [REPORT_EVENT_ROW, EVENT_ROW])
    out = admin_events.list_events()

    sql = store["calls"][0][0]
    outer = _outer_where(sql)
    assert "ORDER BY created_at DESC, target_type DESC, id DESC" in outer   # UNION 바깥 = 전역
    assert "ORDER BY" not in sql[:sql.index(") events")]       # 브랜치 내부 정렬 없음
    # 커서가 준 순서를 그대로 낸다(파이썬에서 다시 정렬하지 않는다)
    assert [r["id"] for r in out] == [34, 12]


def test_merge_tiebreak_is_deterministic_on_equal_created_at(monkeypatch):
    """동률 — 같은 created_at 이면 target_type DESC(report 선행), 같은 축 안에서는 id DESC.

    정렬은 DB 가 수행하므로 여기서는 ORDER BY 키 순서·방향을 SQL 로 단정하고,
    그 키로 정렬한 결과가 어떤 순서가 되는지를 같은 규칙으로 확인한다.
    """
    same_time_rows = [
        REPORT_EVENT_ROW,                                      # id 34, target_type 'report'
        REPORT_EVENT_ROW_NULL_DETAIL,                          # id 35, target_type 'report'
        EVENT_ROW,                                             # id 12, target_type 'glossary'
    ]
    assert {r[8] for r in same_time_rows} == {AT}              # 세 행 created_at 동률

    store = _events_store(monkeypatch, same_time_rows)
    admin_events.list_events()
    outer = _outer_where(store["calls"][0][0])
    keys = outer[outer.index("ORDER BY"):].splitlines()[0]
    assert keys == "ORDER BY created_at DESC, target_type DESC, id DESC"

    # 같은 3키로 정렬하면: report(35) → report(34) → glossary(12)
    ordered = sorted(same_time_rows, key=lambda r: (r[8], r[2], r[0]), reverse=True)
    assert [r[0] for r in ordered] == [35, 34, 12]
    assert [r[2] for r in ordered] == ["report", "report", "glossary"]   # report 선행


def test_merge_target_type_filter_selects_source(monkeypatch):
    """(c) 'report' → report 행만 / 다른 값 → admin_events 만 / 미지정 → 병합."""
    store = _events_store(monkeypatch, [])

    admin_events.list_events(target_type="report")
    admin_events.list_events(target_type="glossary")
    admin_events.list_events()

    p_report, p_glossary, p_none = (c[1] for c in store["calls"])
    assert p_report["target_type"] == "report"
    assert p_glossary["target_type"] == "glossary"
    assert p_none["target_type"] is None                       # 미지정 = 필터 없음 = 병합

    # 필터는 UNION 바깥에 걸린다 — report 행의 target_type 은 상수 사영이므로
    # 'report' 는 risk_report_events 만, 그 외 값은 admin_events 만 남는다.
    outer = _outer_where(store["calls"][0][0])
    assert "%(target_type)s::text IS NULL OR target_type = %(target_type)s" in outer


def test_merge_applies_date_limit_offset_to_merged_result(monkeypatch):
    """(d) date·limit·offset 이 병합 결과에 적용된다(브랜치별 적용 아님)."""
    store = _events_store(monkeypatch, [])
    admin_events.list_events("2026-08-30", None, 10, 5)

    sql, params = store["calls"][0]
    outer = _outer_where(sql)
    assert "(created_at AT TIME ZONE %(tz)s)::date = %(date)s::date" in outer
    assert "LIMIT %(limit)s OFFSET %(offset)s" in outer
    inner = sql[:sql.index(") events")]
    for token in ("LIMIT", "OFFSET", "AT TIME ZONE"):
        assert token not in inner, token                        # 브랜치 안에는 없다
    assert params["date"] == "2026-08-30" and params["limit"] == 10 and params["offset"] == 5

    admin_events.list_events(limit=10_000, offset=-5)
    p2 = store["calls"][1][1]
    assert p2["limit"] == admin_events.LIMIT_MAX and p2["offset"] == 0   # 병합 후에도 상한 유지


def test_merge_keeps_admin_events_rows_unchanged(monkeypatch):
    """(e) 기존 admin_events 행의 응답 모습은 병합 전과 같다 — 무회귀."""
    _events_store(monkeypatch, [EVENT_ROW])
    out = admin_events.list_events()

    assert len(out) == 1 and tuple(out[0]) == admin_events.EVENT_KEYS
    assert out[0]["id"] == 12 and out[0]["target_type"] == "glossary"
    assert out[0]["target_id"] == 7 and out[0]["action"] == "glossary_approved"
    assert out[0]["detail"] is None and out[0]["created_at"] == AT_ISO


def test_list_events_is_read_only(monkeypatch):
    store = _store(rows2=[])
    monkeypatch.setattr(admin_events.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(FakeCursor, "fetchall", lambda self: self.store.get("rows2", []))
    admin_events.list_events()
    for sql, _ in store["calls"]:
        assert sql.strip().split()[0].upper() == "SELECT", sql
    assert store["commits"] == 0


def test_events_endpoint_core(monkeypatch):
    store = _store(rows2=[EVENT_ROW])
    monkeypatch.setattr(admin_events.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(FakeCursor, "fetchall", lambda self: self.store.get("rows2", []))

    r = client.get("/api/v1/admin/events?target_type=glossary&limit=5")

    assert r.status_code == 200
    assert tuple(r.json()[0]) == admin_events.EVENT_KEYS
    assert store["calls"][0][1]["target_type"] == "glossary"
    assert store["calls"][0][1]["limit"] == 5


@pytest.mark.asyncio
async def test_edge_events_and_transitions_go_through_relay(monkeypatch):
    """M-28c 패턴 — 감사 로그 조회·전이 모두 릴레이 경유."""
    monkeypatch.setenv("API_ROLE", "edge")
    monkeypatch.setenv("RELAY_HOLD_S", "3")
    monkeypatch.setenv("RELAY_EDGE_WAIT_S", "5")
    app_edge = build_app("edge")

    cases = [
        ("GET", "/api/v1/admin/events?target_type=glossary",
         "/api/v1/admin/events?target_type=glossary&limit=50&offset=0", []),
        ("POST", "/api/v1/admin/glossary/7/approve",
         "/api/v1/admin/glossary/7/approve", {"id": 7, "status": "approved"}),
    ]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_edge), base_url="http://edge"
    ) as c:
        for method, url, relay_path, payload in cases:
            task = asyncio.create_task(c.get(url) if method == "GET" else c.post(url, json={}))
            pend = await c.get("/internal/relay/pending")
            items = pend.json()["items"]
            assert len(items) == 1, items
            assert items[0]["method"] == method and items[0]["path"] == relay_path
            await c.post(f"/internal/relay/{items[0]['request_id']}/respond",
                         json={"status_code": 200, "body": payload})
            r = await task
            assert r.status_code == 200 and r.json() == payload


def test_poller_dispatches_events_and_transitions(monkeypatch):
    seen = {}

    def _list(date=None, target_type=None, limit=50, offset=0):
        seen.update(date=date, target_type=target_type, limit=limit, offset=offset)
        return []

    monkeypatch.setattr("app.services.admin_events.list_events", _list)
    status, body = relay_poller.dispatch(
        "GET", "/api/v1/admin/events?date=2026-08-30&target_type=glossary&limit=7&offset=2", {}
    )
    assert (status, body) == (200, [])
    assert seen == {"date": "2026-08-30", "target_type": "glossary", "limit": 7, "offset": 2}

    monkeypatch.setattr("app.services.approval.approve_glossary",
                        lambda tid: {"id": tid, "status": "approved"})
    monkeypatch.setattr("app.services.approval.reject_glossary",
                        lambda tid, note=None: {"id": tid, "status": "rejected", "note": note})
    assert relay_poller.dispatch("POST", "/api/v1/admin/glossary/3/approve", {}) == (
        200, {"id": 3, "status": "approved"})
    assert relay_poller.dispatch("POST", "/api/v1/admin/glossary/3/reject", {"note": "n"}) == (
        200, {"id": 3, "status": "rejected", "note": "n"})


# ── 3중 대조: §3 ↔ 구현 ───────────────────────────────────

def test_skeleton_events_contract_matches_implementation():
    line = _skeleton_line("GET  /admin/events")
    assert tuple(_listed_keys(line)) == admin_events.EVENT_KEYS
    assert f"기본 {admin_events.LIMIT_DEFAULT}" in line
    assert f"최대 {admin_events.LIMIT_MAX}" in line
    assert admin_events.EVENTS_TZ in line
    assert "created_at desc, target_type desc, id desc" in line   # M-36 3키 정렬(총괄 0901)


def test_skeleton_transition_contract_documents_m08d_decisions():
    line = _skeleton_line("POST /admin/glossary/{id}/approve")
    for token in ("'approved'", "'rejected'", "422", "404",
                  "admin_events", "M-15b", "admin_events.detail"):
        assert token in line, token
