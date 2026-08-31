"""M-34 c — verify_backtranslation 단위 (되번역 local + bge-m3 코사인 τ 게이트). [새봄]"""

import pytest

from app.agents import verify as verify_mod
from app.services import llm_adapter


def _result(text="장갑을 끼지 마세요.", error=None):
    return llm_adapter.LLMResult(text=text, tier_used="local", model="qwen3:8b", latency_ms=12, error=error)


def _patch(monkeypatch, *, text="장갑을 끼지 마세요.", error=None, vectors=None, seen=None):
    def _complete(prompt, tier, timeout_s=None):
        if seen is not None:
            seen.append({"prompt": prompt, "tier": tier, "timeout_s": timeout_s})
        return _result(text, error)

    monkeypatch.setattr(verify_mod, "complete", _complete)
    monkeypatch.setattr(verify_mod, "embed", lambda texts: vectors or [[1.0, 0.0], [1.0, 0.0]])


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("GATE_TAU", raising=False)


def test_cosine_is_pure_python_and_handles_edges():
    assert verify_mod.cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert verify_mod.cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert verify_mod.cosine([], [1.0]) == 0.0
    assert verify_mod.cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert verify_mod.cosine([1.0, 1.0], [1.0]) == 0.0


def test_score_above_tau_passes(monkeypatch):
    _patch(monkeypatch, vectors=[[1.0, 0.0], [1.0, 0.0]])
    v = verify_mod.verify_backtranslation("장갑을 끼면 안 됩니다.", "Không được đeo găng tay.")
    assert v.score == pytest.approx(1.0)
    assert v.passed is True
    assert v.back_text == "장갑을 끼지 마세요."
    assert v.timed_out is False and v.error is None


def test_score_below_tau_fails(monkeypatch):
    # cos = 0.6 < 0.80
    _patch(monkeypatch, vectors=[[0.6, 0.8], [1.0, 0.0]])
    v = verify_mod.verify_backtranslation("장갑을 끼면 안 됩니다.", "Không được đeo găng tay.")
    assert v.score == pytest.approx(0.6)
    assert v.passed is False
    assert v.error is None


def test_score_is_real_value_not_placeholder(monkeypatch):
    _patch(monkeypatch, vectors=[[1.0, 1.0], [1.0, 0.0]])
    v = verify_mod.verify_backtranslation("원문", "bản dịch")
    assert v.score == pytest.approx(1 / (2 ** 0.5))       # 0.7071…
    assert v.passed is False                              # < 0.80


def test_gate_tau_env_is_honoured(monkeypatch):
    monkeypatch.setenv("GATE_TAU", "0.50")
    _patch(monkeypatch, vectors=[[0.6, 0.8], [1.0, 0.0]])
    v = verify_mod.verify_backtranslation("원문", "bản dịch")
    assert verify_mod.gate_tau() == pytest.approx(0.50)
    assert v.score == pytest.approx(0.6)
    assert v.passed is True                               # 0.6 >= 0.50


def test_gate_tau_env_non_numeric_falls_back(monkeypatch):
    monkeypatch.setenv("GATE_TAU", "높음")
    assert verify_mod.gate_tau() == pytest.approx(verify_mod.DEFAULT_GATE_TAU)


@pytest.mark.parametrize("error", ["local_failed[qwen3:8b:timeout]", "local_failed[qwen3:4b:deadline_exceeded]"])
def test_timeout_is_fail_open(monkeypatch, error):
    _patch(monkeypatch, error=error, text="")
    v = verify_mod.verify_backtranslation("원문", "bản dịch")
    assert v.score is None
    assert v.passed is True
    assert v.timed_out is True
    assert v.error == error


def test_non_timeout_error_is_fail_open_too(monkeypatch):
    _patch(monkeypatch, error="local_failed[qwen3:8b:connect]", text="")
    v = verify_mod.verify_backtranslation("원문", "bản dịch")
    assert v.score is None and v.passed is True
    assert v.timed_out is False
    assert v.error == "local_failed[qwen3:8b:connect]"


def test_embed_failure_is_fail_open(monkeypatch):
    _patch(monkeypatch)

    def _boom(texts):
        raise RuntimeError("embed down")

    monkeypatch.setattr(verify_mod, "embed", _boom)
    v = verify_mod.verify_backtranslation("원문", "bản dịch")
    assert v.score is None and v.passed is True and v.timed_out is False
    assert v.error == "embed_failed[RuntimeError]"


def test_empty_input_skips_llm(monkeypatch):
    seen = []
    _patch(monkeypatch, seen=seen)
    for src, out in (("", "bản dịch"), ("원문", "   ")):
        v = verify_mod.verify_backtranslation(src, out)
        assert v.score is None and v.passed is True and v.error == "empty_input"
    assert seen == []                                     # LLM 호출 0


def test_non_positive_budget_skips_llm(monkeypatch):
    seen = []
    _patch(monkeypatch, seen=seen)
    v = verify_mod.verify_backtranslation("원문", "bản dịch", timeout_s=0)
    assert v.score is None and v.passed is True
    assert v.timed_out is True and v.error == "no_budget"
    assert seen == []


def test_empty_backtranslation_is_fail_open(monkeypatch):
    _patch(monkeypatch, text="   ")
    v = verify_mod.verify_backtranslation("원문", "bản dịch")
    assert v.score is None and v.passed is True
    assert v.error == "empty_backtranslation"


def test_prompt_and_tier_and_timeout_are_passed_through(monkeypatch):
    seen = []
    _patch(monkeypatch, seen=seen)
    verify_mod.verify_backtranslation("원문", "Không được đeo găng tay.", timeout_s=7.5)
    assert len(seen) == 1
    assert seen[0]["tier"] == "local"                     # M-17 로컬 고정
    assert seen[0]["timeout_s"] == 7.5
    assert "Không được đeo găng tay." in seen[0]["prompt"]
    assert seen[0]["prompt"].startswith("다음 문장을 한국어로 번역하세요.")


def test_signature_keeps_src_out_positional():
    import inspect

    params = list(inspect.signature(verify_mod.verify_backtranslation).parameters)
    assert params[:2] == ["src", "out"]                   # §4 동결 시그니처
