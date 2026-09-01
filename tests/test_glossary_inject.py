"""용어집 주입 하네스 — 되번역(기본 on)·답변(기본 off) (총괄 확정 0901). [새봄]

DoD: 되번역 주입 프롬프트가 실험 사본(measure_gate_scores_gloss.py gloss_prompt,
sha256 872c94b9…)의 산출과 문자열 동일. 기대 문자열 3건(S01·S02·S03)은 사본
gloss_prompt() 를 로컬에서 직접 실행(입력 = sentences_30.json answer_vi +
data/seed/glossary/glossary_50.json)해 산출한 값을 리터럴로 고정한 것 —
레포 밖 파일에 의존하지 않는다.

네트워크·LLM 실호출 없음 — 로더는 monkeypatch.
"""

import json
from pathlib import Path

import pytest

from app.agents import graph as graph_mod
from app.agents import verify
from app.agents.retrieve import Chunk
from app.services import glossary_terms

ROOT = Path(__file__).resolve().parents[1]

# 실험 사본 산출 리터럴 (2026-09-01, 사본 직접 실행분 — 보고서에 산출 과정 기록)
EXPECTED = {
    "S01": {
        "out": "Tuyệt đối không chạm tay vào các bộ phận đang quay hoặc dịch chuyển như mâm cặp, trục vít, phôi và dụng cụ.",
        "prompt": "다음 문장을 한국어로 번역하세요. 번역문만 출력하고 다른 말은 덧붙이지 마세요.\n다음 용어는 반드시 지정 한국어 표기로 번역: mâm cặp→척\n\n{text}",
        "matched": [("mâm cặp", "척")],
    },
    "S02": {
        "out": "Không đeo găng tay khi làm việc trên máy tiện.",
        "prompt": "다음 문장을 한국어로 번역하세요. 번역문만 출력하고 다른 말은 덧붙이지 마세요.\n다음 용어는 반드시 지정 한국어 표기로 번역: máy tiện→선반\n\n{text}",
        "matched": [("máy tiện", "선반")],
    },
    "S03": {
        "out": "Trong khi làm việc phải luôn đeo kính bảo hộ.",
        "prompt": "다음 문장을 한국어로 번역하세요. 번역문만 출력하고 다른 말은 덧붙이지 마세요.\n다음 용어는 반드시 지정 한국어 표기로 번역: kính bảo hộ→보안경\n\n{text}",
        "matched": [("kính bảo hộ", "보안경")],
    },
}


def _repo_terms():
    """data/seed/glossary/glossary_50.json → 로더 반환 형식 (term_ko, term_vi, term_in)."""
    items = json.loads((ROOT / "data/seed/glossary/glossary_50.json").read_text(encoding="utf-8"))
    return tuple((g.get("term_ko"), g.get("term_vi"), g.get("term_in")) for g in items)


@pytest.fixture(autouse=True)
def _base(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/test")
    monkeypatch.delenv(verify.INJECT_BACKTRANS_ENV, raising=False)
    monkeypatch.delenv(graph_mod.ANSWER_INJECT_ENV, raising=False)
    monkeypatch.setattr(glossary_terms, "fetch_terms", _repo_terms)
    yield


# ── 되번역 주입 — 실험 사본 문자열 동일 (DoD) ────────────

@pytest.mark.parametrize("sid", ["S01", "S02", "S03"])
def test_backtrans_prompt_equals_experiment_copy(sid):
    exp = EXPECTED[sid]
    prompt, matched = verify.build_backtrans_prompt(exp["out"], lang="vi")
    assert prompt == exp["prompt"]                    # 사본 gloss_prompt 산출과 문자열 동일
    assert matched == exp["matched"]


def test_backtrans_no_match_returns_original():
    prompt, matched = verify.build_backtrans_prompt("용어집 항목이 없는 문장", lang="vi")
    assert prompt == verify.BACKTRANS_PROMPT and matched == []


def test_backtrans_flag_off_is_byte_identical(monkeypatch):
    monkeypatch.setenv(verify.INJECT_BACKTRANS_ENV, "off")
    prompt, matched = verify.build_backtrans_prompt(EXPECTED["S01"]["out"], lang="vi")
    assert prompt == verify.BACKTRANS_PROMPT and matched == []


def test_backtrans_in_lang_uses_term_in():
    prompt, matched = verify.build_backtrans_prompt("gunakan mesin bubut dengan aman", lang="in")
    assert matched == [("mesin bubut", "선반")]
    assert "mesin bubut→선반" in prompt.split("\n")[1]


def test_backtrans_loader_failure_falls_back(monkeypatch):
    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(glossary_terms, "fetch_terms", _boom)
    prompt, matched = verify.build_backtrans_prompt(EXPECTED["S01"]["out"], lang="vi")
    assert prompt == verify.BACKTRANS_PROMPT and matched == []


def test_backtrans_format_still_fills_text():
    prompt, _ = verify.build_backtrans_prompt(EXPECTED["S02"]["out"], lang="vi")
    filled = prompt.format(text=EXPECTED["S02"]["out"])
    assert EXPECTED["S02"]["out"] in filled and "{text}" not in filled


# ── 답변 주입 (기본 off) ──────────────────────────────────

CHUNKS = [Chunk(id=1, document_id=1,
                content="작업 중에는 반드시 보안경을 착용하십시오. 선반 주변을 정리하십시오.",
                title="안전수칙", category="safety")]


def test_answer_inject_default_off():
    line, matched = graph_mod._answer_gloss_line(CHUNKS, "vi")
    assert line is None and matched == []


def test_answer_prompt_byte_identical_when_off():
    base = graph_mod.build_prompt("질문", "vi", CHUNKS)
    assert base == graph_mod.build_prompt("질문", "vi", CHUNKS)
    line, _ = graph_mod._answer_gloss_line(CHUNKS, "vi")
    assert line is None                                # off → 삽입 자체가 없다


def test_answer_inject_on_matches_ko_terms(monkeypatch):
    monkeypatch.setenv(graph_mod.ANSWER_INJECT_ENV, "on")
    line, matched = graph_mod._answer_gloss_line(CHUNKS, "vi")
    assert matched == [("선반", "máy tiện"), ("보안경", "kính bảo hộ")]   # 용어집 순서(선반=1번째 항목)
    assert line == graph_mod.ANSWER_GLOSS_HEAD + "선반→máy tiện, 보안경→kính bảo hộ"


def test_answer_inject_in_lang_maps_term_in(monkeypatch):
    monkeypatch.setenv(graph_mod.ANSWER_INJECT_ENV, "on")
    _, matched = graph_mod._answer_gloss_line(CHUNKS, "in")
    assert matched == [("선반", "mesin bubut"), ("보안경", "kacamata pelindung")]


def test_answer_inject_skips_ko_lang(monkeypatch):
    monkeypatch.setenv(graph_mod.ANSWER_INJECT_ENV, "on")
    line, matched = graph_mod._answer_gloss_line(CHUNKS, "ko")
    assert line is None and matched == []


# ── trace 키 ──────────────────────────────────────────────

def _bt(inj):
    return verify.Verify(score=0.9, passed=True, score_src=0.9, score_aux=0.8,
                         back_text="척을 사용하십시오.", back_ms=10, inj_terms=inj)


def test_trace_records_injection():
    t = graph_mod._backtrans_trace(
        _bt((("mâm cặp", "척"),)), high_risk=True, src_kind="question",
        chunks_joined="근거", src_text="근거",
        ans_injected=[("보안경", "kính bảo hộ")],
    )
    assert (t["inj_n"], t["inj_terms"]) == (1, ["mâm cặp→척"])
    assert (t["ans_inj_n"], t["ans_inj_terms"]) == (1, ["보안경→kính bảo hộ"])
    # 기존 키 무변경 (§3 응답 4키 밖)
    assert t["score_question"] == 0.9 and t["src_kind"] == "question"


def test_trace_injection_none_when_no_backtranslation():
    t = graph_mod._backtrans_trace(None, high_risk=False, src_kind="question")
    assert t["inj_n"] is None and t["inj_terms"] is None
    assert t["ans_inj_n"] == 0 and t["ans_inj_terms"] == []
