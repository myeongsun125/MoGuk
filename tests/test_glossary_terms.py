"""용어집 로더 — status 집합 필터·60s 캐시 (총괄 확정 0901). [새봄]

네트워크·LLM 실호출 없음 — fake cursor·env 주입.
"""

import pytest

from app.services import glossary_terms as gt

ROWS = [("척", "mâm cặp", "cekam"), ("선반", "máy tiện", "mesin bubut")]


class Cursor:
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.store["calls"].append((sql, params))

    def fetchall(self):
        return self.store["rows"]


class Conn:
    def __init__(self, store):
        self.store = store

    def cursor(self):
        return Cursor(self.store)

    def commit(self):
        pass


def fake_connect(store):
    from contextlib import contextmanager

    @contextmanager
    def _connect(slug=None):
        store["connects"] += 1
        yield Conn(store)

    return _connect


def _store(rows=None):
    return {"calls": [], "rows": rows if rows is not None else list(ROWS), "connects": 0}


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/test")
    monkeypatch.delenv(gt.STATUS_ENV, raising=False)
    gt.invalidate()
    yield
    gt.invalidate()


def test_fetch_returns_tuples_in_id_order(monkeypatch):
    store = _store()
    monkeypatch.setattr(gt.tenancy, "connect", fake_connect(store))

    out = gt.fetch_terms()

    assert out == (("척", "mâm cặp", "cekam"), ("선반", "máy tiện", "mesin bubut"))
    sql, params = store["calls"][0]
    assert "ORDER BY id" in sql and "status = ANY" in sql
    assert params == {"statuses": ["approved", "draft"]}   # 기본 집합


@pytest.mark.parametrize(
    "raw,expected",
    [("approved", ["approved"]),
     ("approved, draft", ["approved", "draft"]),
     ("  ,, ", ["approved", "draft"]),      # 공백뿐 → 기본 집합
     ("draft", ["draft"])],
)
def test_status_env_controls_filter(monkeypatch, raw, expected):
    store = _store()
    monkeypatch.setattr(gt.tenancy, "connect", fake_connect(store))
    monkeypatch.setenv(gt.STATUS_ENV, raw)

    gt.fetch_terms()

    assert store["calls"][0][1] == {"statuses": expected}


def test_cache_expires_after_ttl(monkeypatch):
    store = _store()
    monkeypatch.setattr(gt.tenancy, "connect", fake_connect(store))
    clock = {"t": 1000.0}
    monkeypatch.setattr(gt.time, "monotonic", lambda: clock["t"])

    gt.fetch_terms()
    gt.fetch_terms()                        # TTL 안 — 재조회 없음
    assert store["connects"] == 1

    clock["t"] += gt.CACHE_TTL_S + 0.1      # 만료
    gt.fetch_terms()
    assert store["connects"] == 2


def test_status_change_busts_cache(monkeypatch):
    store = _store()
    monkeypatch.setattr(gt.tenancy, "connect", fake_connect(store))

    gt.fetch_terms()
    monkeypatch.setenv(gt.STATUS_ENV, "approved")
    gt.fetch_terms()                        # 키가 달라 캐시 미적중

    assert store["connects"] == 2


def test_invalidate_forces_reload(monkeypatch):
    store = _store()
    monkeypatch.setattr(gt.tenancy, "connect", fake_connect(store))
    gt.fetch_terms()
    gt.invalidate()
    gt.fetch_terms()
    assert store["connects"] == 2


def test_db_error_propagates(monkeypatch):
    def _boom(slug=None):
        raise RuntimeError("db down")

    monkeypatch.setattr(gt.tenancy, "connect", _boom)
    with pytest.raises(RuntimeError):
        gt.fetch_terms()
