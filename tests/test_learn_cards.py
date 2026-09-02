"""GET /learn/cards — 학습 카드 phrase·term (M-42, 총괄 계약 확정 0902). [새봄]

검증 대상 계약:
- 응답 {module, quiz_set_id, cards[{id, kind, text, text_ko, high_risk, note_ko?, src?}]}
- safety = phrases_10 사본(backend/app/data) 기반 phrase 카드 — id 파일 순번 1부터(총괄 확정),
  프로세스 캐시(재호출 시 파일 재독 없음), high_risk 시드 값 그대로
- lang 해석 퀴즈 동형: vi/in 지정 우선 → Bearer 근로자 lang → ko 폴백
- module 미지정·집합 밖 422, quiz_set_id = module 최신 세트·없으면 null(총괄 확정)

fake cursor(needle) — DB 실호출 없음. phrases 는 레포 실물 사본을 그대로 읽는다.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import auth as auth_service
from app.services import learn_cards

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
        yield FakeConn(store)

    return _connect


def _store(**kw):
    base = {"calls": [], "rows": [], "commits": 0}
    base.update(kw)
    return base


@pytest.fixture(autouse=True)
def _base_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/test")
    monkeypatch.setenv("API_ROLE", "core")
    learn_cards.invalidate_cache()
    yield
    learn_cards.invalidate_cache()


def _patch(monkeypatch, rows=None):
    store = _store(rows=rows or [("FROM quiz_sets", (5,))])
    monkeypatch.setattr(learn_cards.tenancy, "connect", fake_connect(store))
    return store


def _bearer(monkeypatch, wid=9):
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-m42")
    token = auth_service.issue_token_pair(wid, "axis_demo")["jwt"]
    return {"Authorization": f"Bearer {token}"}


# ── safety = phrase 카드 ──────────────────────────────────

def test_safety_phrase_cards_vi(monkeypatch):
    _patch(monkeypatch)

    r = client.get("/api/v1/learn/cards?module=safety&lang=vi")

    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"module", "quiz_set_id", "cards"}
    assert body["module"] == "safety"
    c0 = body["cards"][0]
    assert c0["kind"] == "phrase"
    assert c0["text"] == "Dừng lại!"                   # 시드 실물 text_vi
    assert c0["text_ko"] == "멈춰 주세요!"
    assert c0["high_risk"] is True
    assert c0["note_ko"].startswith("비상 시")
    assert c0["src"] == "NCS-LATHE p.57"
    assert all(c["kind"] == "phrase" for c in body["cards"])


def test_phrase_ids_are_file_order_1_to_10(monkeypatch):
    """총괄 확정 — id = 파일 순번, 1부터."""
    _patch(monkeypatch)

    ids = [c["id"] for c in client.get(
        "/api/v1/learn/cards?module=safety&lang=vi").json()["cards"]]

    assert ids == list(range(1, 11))


def test_phrase_high_risk_matches_seed(monkeypatch):
    """시드 실물 분포(1번 true·6번 false)와 일치."""
    _patch(monkeypatch)

    cards = client.get("/api/v1/learn/cards?module=safety").json()["cards"]

    assert cards[0]["high_risk"] is True               # 시드 1번 항목
    assert cards[5]["high_risk"] is False              # 시드 6번 항목
    assert [c["high_risk"] for c in cards].count(False) == 3   # 시드 전수 분포


def test_phrase_src_omitted_when_absent(monkeypatch):
    """src 없는 시드 항목(3건)은 카드에서 키 생략 — note_ko 는 전건 존재."""
    _patch(monkeypatch)

    cards = client.get("/api/v1/learn/cards?module=safety").json()["cards"]

    assert sum(1 for c in cards if "src" in c) == 7
    assert all("note_ko" in c for c in cards)


# ── lang 해석 (퀴즈 동형) ─────────────────────────────────

def test_lang_in_explicit(monkeypatch):
    _patch(monkeypatch)
    c0 = client.get("/api/v1/learn/cards?module=safety&lang=in").json()["cards"][0]
    assert c0["text"] == "Berhenti!"                   # 시드 실물 text_in


def test_lang_from_bearer_worker(monkeypatch):
    store = _patch(monkeypatch, rows=[("FROM workers", ("in",)), ("FROM quiz_sets", (5,))])
    headers = _bearer(monkeypatch)

    c0 = client.get("/api/v1/learn/cards?module=safety", headers=headers).json()["cards"][0]

    assert c0["text"] == "Berhenti!"
    assert [c[1] for c in store["calls"] if "FROM workers" in c[0]] == [{"id": 9}]


def test_lang_invalid_falls_back_to_ko(monkeypatch):
    _patch(monkeypatch)
    c0 = client.get("/api/v1/learn/cards?module=safety&lang=en").json()["cards"][0]
    assert c0["text"] == c0["text_ko"] == "멈춰 주세요!"


def test_lang_unauthenticated_default_ko(monkeypatch):
    _patch(monkeypatch)
    c0 = client.get("/api/v1/learn/cards?module=safety").json()["cards"][0]
    assert c0["text"] == "멈춰 주세요!"


# ── module 검증 422 ───────────────────────────────────────

@pytest.mark.parametrize("query", ["", "?module=xx", "?module=SAFETY"])
def test_invalid_module_422_no_db(monkeypatch, query):
    def _boom(*a, **k):
        pytest.fail("검증 실패인데 저장소를 호출했다")

    monkeypatch.setattr(learn_cards.tenancy, "connect", _boom)

    assert client.get(f"/api/v1/learn/cards{query}").status_code == 422


# ── quiz_set_id 매핑 ──────────────────────────────────────

def test_quiz_set_id_latest_for_module(monkeypatch):
    store = _patch(monkeypatch, rows=[("FROM quiz_sets", (7,))])

    body = client.get("/api/v1/learn/cards?module=safety").json()

    assert body["quiz_set_id"] == 7
    assert [c[1] for c in store["calls"] if "FROM quiz_sets" in c[0]] == [{"module": "safety"}]
    sql = [c[0] for c in store["calls"] if "FROM quiz_sets" in c[0]][0]
    assert "ORDER BY id DESC LIMIT 1" in sql           # 최신 세트


def test_quiz_set_id_null_when_no_set(monkeypatch):
    """총괄 확정 — 해당 module 세트가 없으면 null."""
    _patch(monkeypatch, rows=[("FROM quiz_sets", None)])

    assert client.get("/api/v1/learn/cards?module=safety").json()["quiz_set_id"] is None


# ── 프로세스 캐시 ─────────────────────────────────────────

def test_phrases_file_read_once(monkeypatch):
    _patch(monkeypatch)
    calls = {"n": 0}
    real = learn_cards._read_phrases_file

    def counting():
        calls["n"] += 1
        return real()

    monkeypatch.setattr(learn_cards, "_read_phrases_file", counting)

    client.get("/api/v1/learn/cards?module=safety")
    client.get("/api/v1/learn/cards?module=safety&lang=vi")

    assert calls["n"] == 1                             # 두 번째 호출은 캐시
