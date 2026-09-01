"""GET /learn/quiz/{set_id} · POST submit — 문항 조회·채점 (M-38 §3:221·222). [새봄]

검증 대상 계약:
- 응답 {set_id, module, title, status, items[{id, q, choices[], term_hints[{term_ko, term_lang}]}]}
- lang 해석: 지정 vi/in 우선(그 외 값 ko), 미지정 → Bearer 근로자 lang, 미인증 → ko.
  항목 축 부재(q_in 없음 등)는 문항 단위 ko 폴백
- ★answer_idx 미노출(재귀 전수 검사) — explain_ko 등 계약 외 키도 미노출
- term_hints: q_ko NFC+casefold 부분 문자열 매칭, term_lang = 해석 언어 용어
  (ko 해석이면 term_ko 그대로, 대상어 NULL 이면 term_ko 폴백)
- status 그대로 반환(draft 포함) — 서버는 화면 문구를 만들지 않는다

fake cursor(needle) — 네트워크·DB 실호출 없음. 용어집 로더는 monkeypatch.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import auth as auth_service
from app.services import quiz

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

    def fetchall(self):
        for needle, value in self.store.get("many", []):
            if needle in self._last:
                return value
        return []


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
    base = {"calls": [], "rows": [], "many": [], "commits": 0}
    base.update(kw)
    return base


# ── 픽스처 — 세트 1·문항 2(2번 문항은 in 축 부재 → ko 폴백 검증용) ──

ITEM1 = {
    "q_ko": "척 조임 깊이 기준은?", "q_vi": "Q1-vi", "q_in": "Q1-in",
    "choices": ["가", "나", "다", "라"], "choices_vi": ["a-vi", "b-vi", "c-vi", "d-vi"],
    "choices_in": ["a-in", "b-in", "c-in", "d-in"],
    "answer_idx": 2, "explain_ko": "해설1", "draft": True, "src": ["M-1"],
}
ITEM2 = {
    "q_ko": "보안경과 프레스 점검 시점은?", "q_vi": "Q2-vi",
    "choices": ["ㄱ", "ㄴ"], "choices_vi": ["g-vi", "n-vi"],
    "answer_idx": 0, "explain_ko": "해설2", "draft": True, "src": ["M-2"],
}
SET_ROW = (3, "learning", "선반·프레스 장비 이해", "draft")
TERMS = (
    ("척", "mâm cặp", "cekam"),
    ("보안경", "kính bảo hộ", "kacamata pelindung"),
    ("프레스", "máy dập", None),          # term_in NULL → ko 폴백 검증
)


@pytest.fixture(autouse=True)
def _base_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/test")
    monkeypatch.setenv("API_ROLE", "core")
    monkeypatch.setattr(quiz.glossary_terms, "fetch_terms", lambda: TERMS)


def _quiz_store(**kw):
    return _store(
        rows=[("FROM quiz_sets", SET_ROW)] + kw.pop("rows", []),
        many=[("FROM quiz_items", [(101, ITEM1), (102, ITEM2)])],
        **kw,
    )


def _no_answer_idx(node):
    """응답 어디에도 answer_idx 키가 없어야 한다 — 재귀 전수."""
    if isinstance(node, dict):
        assert "answer_idx" not in node, node
        for v in node.values():
            _no_answer_idx(v)
    elif isinstance(node, list):
        for v in node:
            _no_answer_idx(v)


# ── lang 해석 ─────────────────────────────────────────────

def test_get_quiz_vi(monkeypatch):
    store = _quiz_store()
    monkeypatch.setattr(quiz.tenancy, "connect", fake_connect(store))

    r = client.get("/api/v1/learn/quiz/3?lang=vi")

    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"set_id", "module", "title", "status", "items"}
    assert (body["set_id"], body["module"], body["status"]) == (3, "learning", "draft")
    assert body["items"][0]["q"] == "Q1-vi"
    assert body["items"][0]["choices"] == ["a-vi", "b-vi", "c-vi", "d-vi"]
    assert body["items"][1]["q"] == "Q2-vi"


def test_get_quiz_in_with_item_level_ko_fallback(monkeypatch):
    """2번 문항은 q_in·choices_in 부재 — 그 문항만 ko 폴백."""
    store = _quiz_store()
    monkeypatch.setattr(quiz.tenancy, "connect", fake_connect(store))

    body = client.get("/api/v1/learn/quiz/3?lang=in").json()

    assert body["items"][0]["q"] == "Q1-in"
    assert body["items"][0]["choices"] == ["a-in", "b-in", "c-in", "d-in"]
    assert body["items"][1]["q"] == "보안경과 프레스 점검 시점은?"     # ko 폴백
    assert body["items"][1]["choices"] == ["ㄱ", "ㄴ"]


def test_get_quiz_invalid_lang_falls_back_to_ko(monkeypatch):
    store = _quiz_store()
    monkeypatch.setattr(quiz.tenancy, "connect", fake_connect(store))

    body = client.get("/api/v1/learn/quiz/3?lang=en").json()

    assert body["items"][0]["q"] == "척 조임 깊이 기준은?"
    assert body["items"][0]["choices"] == ["가", "나", "다", "라"]


def test_get_quiz_lang_from_bearer_worker(monkeypatch):
    """lang 미지정 → Bearer 근로자 workers.lang(in) 사용."""
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-m38")
    store = _quiz_store(rows=[("FROM workers", ("in",))])
    monkeypatch.setattr(quiz.tenancy, "connect", fake_connect(store))
    token = auth_service.issue_token_pair(9, "axis_demo")["jwt"]

    body = client.get("/api/v1/learn/quiz/3",
                      headers={"Authorization": f"Bearer {token}"}).json()

    assert body["items"][0]["q"] == "Q1-in"
    assert [c[1] for c in store["calls"] if "FROM workers" in c[0]] == [{"id": 9}]


def test_get_quiz_explicit_lang_overrides_bearer(monkeypatch):
    """지정 lang 우선 — 근로자 lang(in)보다 쿼리 vi 가 이긴다."""
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-m38")
    store = _quiz_store(rows=[("FROM workers", ("in",))])
    monkeypatch.setattr(quiz.tenancy, "connect", fake_connect(store))
    token = auth_service.issue_token_pair(9, "axis_demo")["jwt"]

    body = client.get("/api/v1/learn/quiz/3?lang=vi",
                      headers={"Authorization": f"Bearer {token}"}).json()

    assert body["items"][0]["q"] == "Q1-vi"
    assert not any("FROM workers" in c[0] for c in store["calls"])   # 조회 자체가 없다


def test_get_quiz_unauthenticated_without_lang_is_ko(monkeypatch):
    store = _quiz_store()
    monkeypatch.setattr(quiz.tenancy, "connect", fake_connect(store))

    body = client.get("/api/v1/learn/quiz/3").json()

    assert body["items"][0]["q"] == "척 조임 깊이 기준은?"


# ── ★answer_idx 미노출·계약 외 키 미노출 ──────────────────

@pytest.mark.parametrize("query", ["?lang=vi", "?lang=in", "?lang=en", ""])
def test_answer_idx_never_leaks(monkeypatch, query):
    store = _quiz_store()
    monkeypatch.setattr(quiz.tenancy, "connect", fake_connect(store))

    body = client.get(f"/api/v1/learn/quiz/3{query}").json()

    _no_answer_idx(body)
    for it in body["items"]:
        assert set(it) == {"id", "q", "choices", "term_hints"}     # 계약 키 화이트리스트
        assert "explain_ko" not in it and "src" not in it


# ── term_hints ────────────────────────────────────────────

def test_term_hints_matches_q_ko_and_uses_lang_term(monkeypatch):
    store = _quiz_store()
    monkeypatch.setattr(quiz.tenancy, "connect", fake_connect(store))

    body = client.get("/api/v1/learn/quiz/3?lang=vi").json()

    assert body["items"][0]["term_hints"] == [{"term_ko": "척", "term_lang": "mâm cặp"}]
    assert body["items"][1]["term_hints"] == [
        {"term_ko": "보안경", "term_lang": "kính bảo hộ"},
        {"term_ko": "프레스", "term_lang": "máy dập"},
    ]


def test_term_hints_null_target_falls_back_to_ko(monkeypatch):
    """in 해석에서 term_in 이 NULL(프레스) — term_lang 은 term_ko 폴백."""
    store = _quiz_store()
    monkeypatch.setattr(quiz.tenancy, "connect", fake_connect(store))

    hints = client.get("/api/v1/learn/quiz/3?lang=in").json()["items"][1]["term_hints"]

    assert {"term_ko": "프레스", "term_lang": "프레스"} in hints
    assert {"term_ko": "보안경", "term_lang": "kacamata pelindung"} in hints


def test_term_hints_ko_resolution_uses_term_ko(monkeypatch):
    """ko 해석(무효 lang) — term_lang = term_ko 그대로."""
    store = _quiz_store()
    monkeypatch.setattr(quiz.tenancy, "connect", fake_connect(store))

    hints = client.get("/api/v1/learn/quiz/3?lang=xx").json()["items"][0]["term_hints"]

    assert hints == [{"term_ko": "척", "term_lang": "척"}]


def test_term_hints_glossary_failure_is_fail_open(monkeypatch):
    """용어집 조회 실패 — 문항 조회는 살고 힌트만 빈다(주입 하네스 동형)."""
    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(quiz.glossary_terms, "fetch_terms", _boom)
    store = _quiz_store()
    monkeypatch.setattr(quiz.tenancy, "connect", fake_connect(store))

    r = client.get("/api/v1/learn/quiz/3?lang=vi")

    assert r.status_code == 200
    assert all(it["term_hints"] == [] for it in r.json()["items"])


# ── 404 · 읽기 전용 ───────────────────────────────────────

def test_get_quiz_missing_set_404(monkeypatch):
    store = _store(rows=[("FROM quiz_sets", None)])
    monkeypatch.setattr(quiz.tenancy, "connect", fake_connect(store))

    assert client.get("/api/v1/learn/quiz/999?lang=vi").status_code == 404


def test_get_quiz_is_read_only(monkeypatch):
    store = _quiz_store()
    monkeypatch.setattr(quiz.tenancy, "connect", fake_connect(store))

    client.get("/api/v1/learn/quiz/3?lang=vi")

    for sql, _ in store["calls"]:
        assert sql.strip().split()[0].upper() == "SELECT", sql
    assert store["commits"] == 0


# ══ POST /learn/quiz/{set_id}/submit (§3:222) ══════════════

import json as _json


def _submit_store(threshold=(90,), rows=None):
    return _store(
        rows=[("FROM quiz_sets", SET_ROW), ("FROM tenant_settings", threshold)] + (rows or []),
        many=[("FROM quiz_items", [(101, ITEM1), (102, ITEM2)])],
    )


def _attempt_params(store):
    return [c[1] for c in store["calls"] if "INSERT INTO quiz_attempts" in c[0]]


def test_submit_perfect_score_green(monkeypatch):
    store = _submit_store()
    monkeypatch.setattr(quiz.tenancy, "connect", fake_connect(store))

    r = client.post("/api/v1/learn/quiz/3/submit", json={"answers": [2, 0]})

    assert r.status_code == 200, r.text
    assert r.json() == {"score": 100, "passed": True, "label": "green"}
    p = _attempt_params(store)[0]
    assert (p["quiz_set_id"], p["score"], p["passed"], p["worker_id"]) == (3, 100, True, None)
    detail = _json.loads(p["detail"])
    assert detail == {"answers": [2, 0], "correct": [True, True]}   # 정오 기록
    assert store["commits"] == 1


def test_submit_half_score_red_not_passed(monkeypatch):
    store = _submit_store()
    monkeypatch.setattr(quiz.tenancy, "connect", fake_connect(store))

    r = client.post("/api/v1/learn/quiz/3/submit", json={"answers": [2, 1]})

    assert r.json() == {"score": 50, "passed": False, "label": "red"}
    assert _json.loads(_attempt_params(store)[0]["detail"])["correct"] == [True, False]


def test_submit_threshold_from_tenant_settings_not_hardcoded(monkeypatch):
    """threshold_pass=50 행 — score 50 이 passed=True 가 된다(상수 90 이면 불가능).

    label 은 계약 고정 경계라 여전히 red — passed 와 label 의 독립도 함께 고정.
    """
    store = _submit_store(threshold=(50,))
    monkeypatch.setattr(quiz.tenancy, "connect", fake_connect(store))

    r = client.post("/api/v1/learn/quiz/3/submit", json={"answers": [2, 1]})

    assert r.json() == {"score": 50, "passed": True, "label": "red"}
    assert any("tenant_settings" in c[0] for c in store["calls"])
    assert [c[1] for c in store["calls"] if "tenant_settings" in c[0]] == [{"key": "threshold_pass"}]


def test_submit_threshold_row_missing_falls_back_90(monkeypatch):
    store = _submit_store(threshold=None)
    monkeypatch.setattr(quiz.tenancy, "connect", fake_connect(store))

    r = client.post("/api/v1/learn/quiz/3/submit", json={"answers": [2, 1]})

    assert r.json()["passed"] is False                 # 50 < 폴백 90
    r2_store = _submit_store(threshold=None)
    monkeypatch.setattr(quiz.tenancy, "connect", fake_connect(r2_store))
    assert client.post("/api/v1/learn/quiz/3/submit",
                       json={"answers": [2, 0]}).json()["passed"] is True   # 100 ≥ 90


def test_submit_records_bearer_worker_id(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-m38")
    store = _submit_store()
    monkeypatch.setattr(quiz.tenancy, "connect", fake_connect(store))
    token = auth_service.issue_token_pair(9, "axis_demo")["jwt"]

    client.post("/api/v1/learn/quiz/3/submit", json={"answers": [2, 0]},
                headers={"Authorization": f"Bearer {token}"})

    assert _attempt_params(store)[0]["worker_id"] == 9


@pytest.mark.parametrize("answers", [
    [2],                 # 길이 부족
    [2, 0, 1],           # 길이 초과
    [2, 5],              # 2번 문항(2지) 범위 밖
    [-1, 0],             # 음수
    [True, 0],           # bool — StrictInt 가 pydantic 코어스(true→1)를 차단
])
def test_submit_invalid_answers_422_no_insert(monkeypatch, answers):
    store = _submit_store()
    monkeypatch.setattr(quiz.tenancy, "connect", fake_connect(store))

    r = client.post("/api/v1/learn/quiz/3/submit", json={"answers": answers})

    assert r.status_code == 422, r.text
    assert _attempt_params(store) == []                # 거절 시 기록 없음
    assert store["commits"] == 0


def test_submit_bool_rejected_at_service_layer(monkeypatch):
    """릴레이 경로처럼 pydantic 을 거치지 않는 직접 호출 — bool 은 서비스가 거절한다."""
    store = _submit_store()
    monkeypatch.setattr(quiz.tenancy, "connect", fake_connect(store))

    with pytest.raises(quiz.InvalidAnswers):
        quiz.submit_quiz(3, [True, 0])

    assert _attempt_params(store) == []


def test_submit_non_list_answers_422(monkeypatch):
    def _boom(*a, **k):
        pytest.fail("검증 실패인데 저장소를 호출했다")

    monkeypatch.setattr(quiz.tenancy, "connect", _boom)
    assert client.post("/api/v1/learn/quiz/3/submit",
                       json={"answers": "oops"}).status_code == 422        # pydantic


def test_submit_missing_set_404(monkeypatch):
    store = _store(rows=[("FROM quiz_sets", None)])
    monkeypatch.setattr(quiz.tenancy, "connect", fake_connect(store))

    assert client.post("/api/v1/learn/quiz/999/submit",
                       json={"answers": [0]}).status_code == 404


@pytest.mark.parametrize("score, label", [
    (0, "red"), (79, "red"), (80, "yellow"), (89, "yellow"), (90, "green"), (100, "green"),
])
def test_label_boundaries_contract_fixed(score, label):
    """red<80 / yellow<90 / green — v_comprehension(001:69) 경계와 동일."""
    assert quiz.label_for(score) == label
