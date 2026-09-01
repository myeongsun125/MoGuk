"""GET /admin/dashboard — KPI 4종 + 오늘 시간대별 추이 (총괄 확정 0830). [새봄]

검증 대상 계약:
- A open_reports        = risk_reports WHERE status='submitted'
- B reports_by_status   = submitted/acknowledged/resolved 각 건수(% 없음)
- C unanswered_open     = unanswered_queue WHERE status='open'
- D citation_rate       분모 = 답변 방출(gated 제외) / 분자 = sources 존재
                        gated 는 분모에 넣지 않는다(그쪽은 C 담당, M-05a 정합)
- 추이                  오늘(Asia/Seoul) 시간대별, 00시~현재 zero-fill. 7일 집계 아님
- M-28c                 edge role 은 릴레이 경유, 읽기 전용(쓰기·이벤트 0)
- 3중 대조              §3 등재 문안 ↔ PR 계약 표 ↔ 구현 상수
"""

import asyncio
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app, build_app
from app.services import dashboard as dash
from app.services import relay
from app.workers import relay_poller

client = TestClient(app, client=("127.0.0.1", 50000))


# ── 가짜 DB — 쿼리별로 응답을 골라준다 ─────────────────────

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

    def _pick(self, key):
        return self.store[key]

    def fetchall(self):
        if "GROUP BY status" in self._last:
            return self.store.get("status_rows", [])
        if "JOIN quiz_sets" in self._last:                       # M-38 per_module
            return self.store.get("per_module_rows", [])
        if "FROM v_comprehension" in self._last:                 # M-38 per_worker
            return self.store.get("per_worker_rows", [])
        return self.store.get("trend_rows", [])

    def fetchone(self):
        if "unanswered_queue" in self._last:
            return (self.store.get("unanswered", 0),)
        if "FILTER (WHERE grounded" in self._last:
            return self.store.get("citation", (0, 0))
        if "now() AT TIME ZONE" in self._last:
            return (self.store.get("now_local", "2026-08-30 17:00:00"),)
        if "quiz_attempts" in self._last:                        # M-38 completion
            return self.store.get("completion", (0, 0))
        if "avg(score)" in self._last:                           # M-38 avg_comprehension
            return (self.store.get("avg_comprehension"),)
        return (0,)


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
    base = {"calls": [], "commits": 0}
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


# ── A·B: 상태 집계 ────────────────────────────────────────

def test_open_reports_and_status_breakdown(monkeypatch):
    store = _store(status_rows=[("submitted", 3), ("acknowledged", 1), ("resolved", 2)],
                   unanswered=0, citation=(0, 0), trend_rows=[], now_local="2026-08-30 03:00:00")
    monkeypatch.setattr(dash.tenancy, "connect", fake_connect(store))

    out = dash.get_dashboard()

    assert out["reports_by_status"] == {"submitted": 3, "acknowledged": 1, "resolved": 2}
    assert out["open_reports"] == 3                      # A = submitted 건수
    assert out["open_reports"] == out["reports_by_status"]["submitted"]
    assert all(isinstance(v, int) for v in out["reports_by_status"].values())   # % 아님


def test_status_breakdown_fills_missing_states_with_zero(monkeypatch):
    store = _store(status_rows=[("submitted", 2)], unanswered=0, citation=(0, 0),
                   trend_rows=[], now_local="2026-08-30 03:00:00")
    monkeypatch.setattr(dash.tenancy, "connect", fake_connect(store))

    out = dash.get_dashboard()

    assert out["reports_by_status"] == {"submitted": 2, "acknowledged": 0, "resolved": 0}
    assert set(out["reports_by_status"]) == set(dash.STATUS_KEYS)


def test_status_query_has_no_where_filter(monkeypatch):
    """B 는 전체 GROUP BY — 특정 상태만 세면 3칸 합이 전체와 어긋난다."""
    store = _store(status_rows=[], unanswered=0, citation=(0, 0), trend_rows=[],
                   now_local="2026-08-30 03:00:00")
    monkeypatch.setattr(dash.tenancy, "connect", fake_connect(store))
    dash.get_dashboard()

    sql = [s for s in _sqls(store) if "GROUP BY status" in s][0]
    assert "WHERE" not in sql.upper(), sql


# ── C: 무근거 질의 대기 ───────────────────────────────────

def test_unanswered_open_counts_only_open(monkeypatch):
    store = _store(status_rows=[], unanswered=9, citation=(0, 0), trend_rows=[],
                   now_local="2026-08-30 03:00:00")
    monkeypatch.setattr(dash.tenancy, "connect", fake_connect(store))

    out = dash.get_dashboard()

    assert out["unanswered_open"] == 9
    sql = [s for s in _sqls(store) if "unanswered_queue" in s][0]
    assert "status = 'open'" in sql, sql


# ── D: 근거 인용률 ────────────────────────────────────────

def test_citation_rate_denominator_excludes_gated(monkeypatch):
    """분모 = 답변 방출(§3:234) — grounded 이면서 gated 아닌 행만 센다."""
    store = _store(status_rows=[], unanswered=7, citation=(12, 12), trend_rows=[],
                   now_local="2026-08-30 03:00:00")
    monkeypatch.setattr(dash.tenancy, "connect", fake_connect(store))

    out = dash.get_dashboard()

    assert out["citation_rate"] == {"answered": 12, "with_sources": 12, "rate": 1.0}
    sql = [s for s in _sqls(store) if "FILTER (WHERE grounded" in s][0]
    assert "jsonb_array_length(sources) > 0" in sql               # 분자 = 출처 존재
    assert "unanswered" not in sql                                # C 경로 혼입 금지
    # 분모가 전체 질의(count(*) 단독)면 gated 가 섞인다 — 그 형태가 아님을 단정
    assert re.search(r"count\(\*\)\s+FROM questions", sql) is None, sql


def test_citation_sql_excludes_threshold_blocked_rows():
    """threshold 차단 행(grounded=true·trace.verify.gated=true)은 분모·분자 모두 제외.

    grounded 판별만으로는 τ 차단 행이 분모에 남는다(0831 워밍업 3건 실측).
    분모·분자 FILTER 두 곳 모두에 gated 제외 조건이 있어야 하고, 키 부재 행은
    NULL → IS DISTINCT FROM 으로 미차단 계산(하위 호환)이어야 한다.
    """
    sql = dash._SQL_CITATION
    assert sql.count("trace -> 'verify' -> 'gated'") == 2         # 분모·분자 양쪽
    assert sql.count("IS DISTINCT FROM 'true'::jsonb") == 2       # NULL 안전(키 부재 = 미차단)
    denom, numer = sql.split("count(*) FILTER")[1:]
    assert "IS DISTINCT FROM" in denom and "grounded" in denom
    assert "IS DISTINCT FROM" in numer and "jsonb_array_length(sources) > 0" in numer


def test_citation_rate_below_one_is_reported_as_is(monkeypatch, caplog):
    """100% 미만이어도 수치를 만지지 않는다 — 결함 신호로 로그만 남긴다."""
    store = _store(status_rows=[], unanswered=0, citation=(10, 7), trend_rows=[],
                   now_local="2026-08-30 03:00:00")
    monkeypatch.setattr(dash.tenancy, "connect", fake_connect(store))

    with caplog.at_level("WARNING"):
        out = dash.get_dashboard()

    assert out["citation_rate"] == {"answered": 10, "with_sources": 7, "rate": 0.7}
    assert any("근거 인용률" in r.message for r in caplog.records)


def test_citation_rate_is_none_when_no_answered_query(monkeypatch):
    """분모 0 — 0으로 나누지 않고 null 로 내보낸다(0.0 으로 위장 금지)."""
    store = _store(status_rows=[], unanswered=0, citation=(0, 0), trend_rows=[],
                   now_local="2026-08-30 03:00:00")
    monkeypatch.setattr(dash.tenancy, "connect", fake_connect(store))

    out = dash.get_dashboard()

    assert out["citation_rate"] == {"answered": 0, "with_sources": 0, "rate": None}


# ── 추이: 오늘 시간대별 ───────────────────────────────────

def test_trend_is_today_hourly_zero_filled(monkeypatch):
    store = _store(status_rows=[], unanswered=0, citation=(0, 0),
                   trend_rows=[("2026-08-30 09", 2), ("2026-08-30 11", 5)],
                   now_local="2026-08-30 11:42:10")
    monkeypatch.setattr(dash.tenancy, "connect", fake_connect(store))

    out = dash.get_dashboard()
    trend = out["reports_today_hourly"]

    assert len(trend) == 12                                   # 00시~11시 포함
    assert trend[0] == {"hour": "2026-08-30T00:00:00", "count": 0}
    assert trend[9] == {"hour": "2026-08-30T09:00:00", "count": 2}
    assert trend[10] == {"hour": "2026-08-30T10:00:00", "count": 0}
    assert trend[11] == {"hour": "2026-08-30T11:00:00", "count": 5}
    assert all(set(b) == set(dash.TREND_KEYS) for b in trend)
    assert [b["hour"] for b in trend] == sorted(b["hour"] for b in trend)


def test_trend_query_is_today_only_and_not_weekly(monkeypatch):
    """7일 집계 금지 — 오늘 날짜 한정, 버킷은 hour."""
    store = _store(status_rows=[], unanswered=0, citation=(0, 0), trend_rows=[],
                   now_local="2026-08-30 05:00:00")
    monkeypatch.setattr(dash.tenancy, "connect", fake_connect(store))
    dash.get_dashboard()

    sql = [s for s in _sqls(store) if "date_trunc" in s][0]
    assert "date_trunc('hour'" in sql
    assert "(now() AT TIME ZONE %(tz)s)::date" in sql          # 오늘만
    for banned in ("interval '7", "7 days", "week"):
        assert banned not in sql.lower(), sql


def test_trend_timezone_is_applied_to_both_bucket_and_today(monkeypatch):
    """버킷 경계와 '오늘' 판정에 같은 시간대를 쓴다 — 경계 어긋남 방지."""
    store = _store(status_rows=[], unanswered=0, citation=(0, 0), trend_rows=[],
                   now_local="2026-08-30 05:00:00")
    monkeypatch.setattr(dash.tenancy, "connect", fake_connect(store))
    dash.get_dashboard()

    sql, params = [c for c in store["calls"] if "date_trunc" in c[0]][0]
    assert params == {"tz": dash.DASHBOARD_TZ} == {"tz": "Asia/Seoul"}
    assert sql.count("AT TIME ZONE %(tz)s") == 3               # 버킷·WHERE 좌변·now()


def test_generated_at_and_timezone_exposed(monkeypatch):
    store = _store(status_rows=[], unanswered=0, citation=(0, 0), trend_rows=[],
                   now_local="2026-08-30 17:05:00")
    monkeypatch.setattr(dash.tenancy, "connect", fake_connect(store))

    out = dash.get_dashboard()

    assert out["generated_at"] == "2026-08-30T17:05:00"
    assert out["timezone"] == "Asia/Seoul"


# ── 읽기 전용 ─────────────────────────────────────────────

def test_dashboard_is_read_only(monkeypatch):
    store = _store(status_rows=[], unanswered=0, citation=(0, 0), trend_rows=[],
                   now_local="2026-08-30 03:00:00")
    monkeypatch.setattr(dash.tenancy, "connect", fake_connect(store))
    dash.get_dashboard()

    for sql in _sqls(store):
        head = sql.strip().split()[0].upper()
        assert head == "SELECT", sql
    assert store["commits"] == 0
    assert not any("risk_report_events" in s for s in _sqls(store))   # 이벤트 기록 없음


# ── 엔드포인트 · M-28c edge 분기 ──────────────────────────

def test_dashboard_endpoint_core(monkeypatch):
    store = _store(status_rows=[("submitted", 1)], unanswered=2, citation=(4, 4),
                   trend_rows=[("2026-08-30 01", 1)], now_local="2026-08-30 01:30:00")
    monkeypatch.setattr(dash.tenancy, "connect", fake_connect(store))

    r = client.get("/api/v1/admin/dashboard")

    assert r.status_code == 200
    body = r.json()
    assert tuple(body) == dash.RESPONSE_KEYS
    assert body["open_reports"] == 1 and body["unanswered_open"] == 2
    assert body["citation_rate"]["rate"] == 1.0
    assert body["reports_today_hourly"][-1] == {"hour": "2026-08-30T01:00:00", "count": 1}


@pytest.mark.asyncio
async def test_dashboard_edge_goes_through_relay(monkeypatch):
    """M-28c 패턴 — edge 는 DB 자격이 없으므로 릴레이 경유(빈 body)."""
    monkeypatch.setenv("API_ROLE", "edge")
    monkeypatch.setenv("RELAY_HOLD_S", "3")
    monkeypatch.setenv("RELAY_EDGE_WAIT_S", "5")
    payload = {"open_reports": 0}
    app_edge = build_app("edge")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_edge), base_url="http://edge"
    ) as c:
        task = asyncio.create_task(c.get("/api/v1/admin/dashboard"))
        pend = await c.get("/internal/relay/pending")
        items = pend.json()["items"]
        assert len(items) == 1
        assert items[0]["method"] == "GET"
        assert items[0]["path"] == "/api/v1/admin/dashboard"
        assert items[0]["body"] == {}
        await c.post(f"/internal/relay/{items[0]['request_id']}/respond",
                     json={"status_code": 200, "body": payload})
        r = await task

    assert r.status_code == 200 and r.json() == payload


def test_poller_dispatches_dashboard_get(monkeypatch):
    monkeypatch.setattr("app.services.dashboard.get_dashboard", lambda: {"open_reports": 7})
    status, body = relay_poller.dispatch("GET", "/api/v1/admin/dashboard", {})
    assert (status, body) == (200, {"open_reports": 7})


# ── 3중 대조: §3 등재 문안 ↔ 구현 상수 ─────────────────────

def _skeleton_dashboard_line() -> str:
    import io
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    text = io.open(root / "docs/skeleton-v3.md", encoding="utf-8").read()
    lines = [l for l in text.split("\n") if l.startswith("GET  /admin/dashboard")]
    assert len(lines) == 1, lines
    return lines[0]


def _top_level_keys(line: str) -> list[str]:
    body = re.search(r"→ \{(.*)\}   #", line).group(1)
    out, depth, cur = [], 0, ""
    for ch in body:
        if ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    out.append(cur.strip())
    return [k.split(":")[0].split("[")[0].strip() for k in out]


def test_skeleton_contract_matches_implementation_keys():
    """§3:235 중괄호 = 기존 7키(무변경 확인). 학습 KPI 4키(M-38)는 말미 추가분 —
    per_worker·per_module 는 §3 주석부에 등재, completion_rate·avg_comprehension 은
    총괄 지시(0902) 선반영으로 §3 등재는 MS 몫(보고 상신)."""
    line = _skeleton_dashboard_line()
    assert tuple(_top_level_keys(line)) == dash.RESPONSE_KEYS[:7]
    assert dash.RESPONSE_KEYS[7:] == (
        "per_worker", "per_module", "completion_rate", "avg_comprehension"
    )


def test_skeleton_contract_documents_nested_keys_and_tz():
    line = _skeleton_dashboard_line()
    for k in dash.CITATION_KEYS + dash.TREND_KEYS + dash.STATUS_KEYS:
        assert k in line, k
    assert dash.DASHBOARD_TZ in line
    assert "gated 제외" in line          # D 분모 정의 명시
    # M-38 — 학습 KPI 문면(§3:235 주석부)과 구현 키 정합
    assert "per_worker" in line and "per_module" in line and "v_comprehension" in line
    for k in dash.PER_WORKER_KEYS + dash.PER_MODULE_KEYS:
        assert k in line, k


# ── M-38 학습 KPI — per_worker·per_module·completion_rate·avg_comprehension ──

import datetime as _dt
from decimal import Decimal

_AT = _dt.datetime(2026, 9, 2, 1, 0, tzinfo=_dt.timezone.utc)


def _kpi_store(**kw):
    base = dict(status_rows=[], unanswered=0, citation=(0, 0), trend_rows=[],
                now_local="2026-09-02 03:00:00")
    base.update(kw)
    return _store(**base)


def test_per_worker_rows_shape_and_view_label_passthrough(monkeypatch):
    """v_comprehension 행 그대로 — 라벨은 뷰 계산값을 재계산 없이 투과."""
    store = _kpi_store(per_worker_rows=[
        (2, 3, Decimal("100"), "green", _AT),
        (3, 3, Decimal("66.7"), "red", _AT),
    ])
    monkeypatch.setattr(dash.tenancy, "connect", fake_connect(store))

    out = dash.get_dashboard()

    assert out["per_worker"] == [
        {"worker_id": 2, "quiz_set_id": 3, "score": 100, "label": "green",
         "created_at": "2026-09-02T01:00:00+00:00"},
        {"worker_id": 3, "quiz_set_id": 3, "score": 66.7, "label": "red",
         "created_at": "2026-09-02T01:00:00+00:00"},
    ]
    assert all(tuple(r) == dash.PER_WORKER_KEYS for r in out["per_worker"])
    # 라벨 경계는 뷰(001:69) 소유 — 대시보드 SQL 이 재계산하지 않는다
    assert "CASE WHEN" not in dash._SQL_PER_WORKER


def test_per_module_aggregates_with_rounding(monkeypatch):
    store = _kpi_store(per_module_rows=[
        ("learning", 2, Decimal("83.35")), ("safety", 1, Decimal("100")),
    ])
    monkeypatch.setattr(dash.tenancy, "connect", fake_connect(store))

    out = dash.get_dashboard()

    assert out["per_module"] == [
        {"module": "learning", "n": 2, "avg_score": 83.3},   # round(…, 1)
        {"module": "safety", "n": 1, "avg_score": 100.0},
    ]
    assert "JOIN quiz_sets" in dash._SQL_PER_MODULE and "v_comprehension" in dash._SQL_PER_MODULE


def test_completion_rate_counts_and_ratio(monkeypatch):
    store = _kpi_store(completion=(3, 8))
    monkeypatch.setattr(dash.tenancy, "connect", fake_connect(store))

    out = dash.get_dashboard()

    assert out["completion_rate"] == {
        "workers_attempted": 3, "workers_activated": 8, "rate": 0.375,
    }
    sql = [s for s in _sqls(store) if "quiz_attempts" in s][0]
    assert "DISTINCT worker_id" in sql                     # 시도 근로자 수(시도 횟수 아님)
    assert "activated_at IS NOT NULL" in sql               # 분모 = 활성 근로자


def test_completion_rate_zero_activated_is_null(monkeypatch):
    store = _kpi_store(completion=(0, 0))
    monkeypatch.setattr(dash.tenancy, "connect", fake_connect(store))

    out = dash.get_dashboard()

    assert out["completion_rate"] == {
        "workers_attempted": 0, "workers_activated": 0, "rate": None,
    }


def test_avg_comprehension_value_and_null(monkeypatch):
    store = _kpi_store(avg_comprehension=Decimal("82.54"))
    monkeypatch.setattr(dash.tenancy, "connect", fake_connect(store))
    assert dash.get_dashboard()["avg_comprehension"] == 82.5

    empty = _kpi_store()                                   # 데이터 없음 → null
    monkeypatch.setattr(dash.tenancy, "connect", fake_connect(empty))
    assert dash.get_dashboard()["avg_comprehension"] is None


def test_learn_kpi_keys_are_appended_not_renamed(monkeypatch):
    """기존 7키 순서 그대로 + 신설 4키는 말미 — 제거·개명 없음(총괄 지시)."""
    store = _kpi_store()
    monkeypatch.setattr(dash.tenancy, "connect", fake_connect(store))

    out = dash.get_dashboard()

    assert tuple(out) == dash.RESPONSE_KEYS
    assert dash.RESPONSE_KEYS[:7] == (
        "open_reports", "reports_by_status", "unanswered_open", "citation_rate",
        "reports_today_hourly", "generated_at", "timezone",
    )
