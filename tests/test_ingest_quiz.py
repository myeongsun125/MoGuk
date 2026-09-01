"""ingest_seed --sources quiz — 시드 퀴즈 적재 (M-38). [새봄]

검증 대상 계약:
- quiz_sets: origin='seed', status='draft' / quiz_items: 파일에 적힌 순서 그대로
- body = 항목 dict 원형(실물 키 q_ko·q_vi·q_in·choices·choices_vi·choices_in·answer_idx·
  explain_ko + draft·source·src·quote)
- 멱등: 재실행 시 중복 적재 없음 — 세트 행 보존(quiz_attempts FK)·문항만 교체,
  approved 세트 무접촉(glossary '승인 행 무접촉' 동형)
- documents·chunks·glossary 무접촉 경로 (임베딩 호출 없음)

모듈 로드는 파일 경로 직접 — pyyaml 없는 CI 에서도 임포트돼야 한다(quiz 경로는 yaml 비사용).
"""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location("ingest_seed", ROOT / "scripts" / "ingest_seed.py")
ing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ing)


class FakeCursor:
    """needle 기반 fake — (SELECT 결과 주입, 실행 SQL·파라미터 수집)."""

    def __init__(self, rows):
        self.rows = rows              # [(needle, fetchone 값)]
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        self._last = sql

    def fetchone(self):
        for needle, value in self.rows:
            if needle in self._last:
                return value
        return (1,)

    def sqls(self):
        return [c[0] for c in self.calls]

    def params_for(self, needle):
        return [c[1] for c in self.calls if needle in c[0]]


# ── load_quiz_plan — 파일 실물 로드 ───────────────────────

def test_load_quiz_plan_reads_two_files_in_order():
    sets = ing.load_quiz_plan()

    assert [s["module"] for s in sets] == ["learning", "safety"]
    assert all(len(s["items"]) == 5 for s in sets)
    assert [s["source"] for s in sets] == ing.QUIZ_FILES

    # 파일 순서 보존 — 실물 1번 문항과 동일
    raw = json.loads((ROOT / ing.QUIZ_FILES[0]).read_text(encoding="utf-8"))
    assert sets[0]["items"][0] == raw["items"][0]
    assert sets[0]["items"] == raw["items"]              # 전체 순서 그대로
    assert sets[0]["title"] == raw["_meta"]["title"]

    # 실물 키 충족 (q_in·choices_in 은 #85 반영분)
    for it in sets[0]["items"]:
        for key in ("q_ko", "q_vi", "q_in", "choices", "choices_vi", "choices_in",
                    "answer_idx", "explain_ko"):
            assert key in it, key


# ── ingest_quiz — 신규 적재 ───────────────────────────────

def _one_set():
    return [{"module": "learning", "title": "T", "source": "s.json",
             "items": [{"q_ko": "q1", "answer_idx": 0}, {"q_ko": "q2", "answer_idx": 1}]}]


def test_ingest_quiz_inserts_new_set_as_seed_draft():
    cur = FakeCursor(rows=[("SELECT id, status FROM quiz_sets", None),
                           ("INSERT INTO quiz_sets", (5,))])

    ing.ingest_quiz(cur, _one_set())

    ins = [s for s in cur.sqls() if "INSERT INTO quiz_sets" in s][0]
    assert "'seed'" in ins and "'draft'" in ins          # 계약 고정값
    items = cur.params_for("INSERT INTO quiz_items")
    assert len(items) == 2
    assert items[0][0] == 5 and items[1][0] == 5
    # 파일 순서 그대로 — 첫 INSERT 가 첫 문항
    assert json.loads(items[0][1])["q_ko"] == "q1"
    assert json.loads(items[1][1])["q_ko"] == "q2"


def test_ingest_quiz_body_is_item_verbatim():
    item = {"q_ko": "q", "q_vi": "v", "q_in": "i", "choices": ["a"], "choices_vi": ["b"],
            "choices_in": ["c"], "answer_idx": 0, "explain_ko": "e",
            "draft": True, "source": "PRESS-1", "src": ["M-1"], "quote": "원문"}
    cur = FakeCursor(rows=[("SELECT id, status FROM quiz_sets", None),
                           ("INSERT INTO quiz_sets", (5,))])

    ing.ingest_quiz(cur, [{"module": "m", "title": "t", "source": "s", "items": [item]}])

    stored = json.loads(cur.params_for("INSERT INTO quiz_items")[0][1])
    assert stored == item                                # 원형 그대로 — 키 추가·삭제 없음


# ── 멱등 — 기존 draft 세트 교체·approved 무접촉 ───────────

def test_ingest_quiz_rerun_replaces_items_keeping_set_row():
    cur = FakeCursor(rows=[("SELECT id, status FROM quiz_sets", (7, "draft"))])

    ing.ingest_quiz(cur, _one_set())

    sqls = cur.sqls()
    assert not any("INSERT INTO quiz_sets" in s for s in sqls)     # 세트 행 보존(FK)
    assert not any("DELETE FROM quiz_sets" in s for s in sqls)
    assert cur.params_for("DELETE FROM quiz_items") == [(7,)]      # 문항만 교체
    assert len(cur.params_for("INSERT INTO quiz_items")) == 2


def test_ingest_quiz_skips_approved_set():
    cur = FakeCursor(rows=[("SELECT id, status FROM quiz_sets", (7, "approved"))])

    ing.ingest_quiz(cur, _one_set())

    sqls = cur.sqls()
    assert not any("DELETE" in s for s in sqls)
    assert not any("INSERT INTO quiz_items" in s for s in sqls)    # 승인 세트 무접촉


def test_ingest_quiz_touches_only_quiz_tables():
    cur = FakeCursor(rows=[("SELECT id, status FROM quiz_sets", None),
                           ("INSERT INTO quiz_sets", (5,))])

    ing.ingest_quiz(cur, _one_set())

    for sql in cur.sqls():
        assert "quiz_sets" in sql or "quiz_items" in sql, sql      # documents·glossary 무접촉
