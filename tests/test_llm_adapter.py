"""llm_adapter 단위 테스트 — 네트워크 없음(_call_ollama/_call_external/httpx monkeypatch). [새봄]

검증 대상 계약:
- skeleton-v3 §4 동결 시그니처 `complete(prompt, tier, timeout_s=None)` (M-30 ①)
- M-30 ②: LLM_TIMEOUT_LOCAL_S=25 / LLM_TIMEOUT_EXTERNAL_S=8 / LLM_DEADLINE_S=27 / LLM_NUM_PREDICT=200,
  구 키(EXTERNAL_LLM_TIMEOUT_S·LOCAL_FALLBACK_TIMEOUT_S) 하위호환 읽기 없음(R4)
- M-30 ③: ollama 페이로드 think:false + options.num_predict, 응답 <think> 블록 제거(로컬 전용)
- M-17a: external timeout/오류 전부(상태코드 구분 없음) → local 자동 폴백
- M-03: local qwen3:8b 주력 → 실패 시 qwen3:4b 폴백
- M-17 티어 정책: tier="local" 은 외부를 절대 호출하지 않는다
- M-03a 폴백 env(OLLAMA_MODEL=qwen3:4b, LLM_NUM_PREDICT=100) 정상 동작
"""

import inspect

import httpx
import pytest

from app.services import llm_adapter
from app.services.llm_adapter import complete

M30_KEYS = (
    "LLM_TIMEOUT_LOCAL_S",
    "LLM_TIMEOUT_EXTERNAL_S",
    "LLM_DEADLINE_S",
    "LLM_NUM_PREDICT",
    "LLM_PROBE_TIMEOUT_S",
    "EXTERNAL_LLM_PROVIDER",
    "EXTERNAL_LLM_MODEL",
    # 폐지된 구 키 — 테스트 간 누수 방지
    "EXTERNAL_LLM_TIMEOUT_S",
    "LOCAL_FALLBACK_TIMEOUT_S",
)


@pytest.fixture(autouse=True)
def _base_env(monkeypatch):
    """기준 env — 실제 네트워크로 새지 않도록 로컬 주소를 명시하고 M-30 키는 비운다."""
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    monkeypatch.setenv("OLLAMA_FALLBACK_MODEL", "qwen3:4b")
    monkeypatch.setenv("EXTERNAL_LLM_API_KEY", "sk-test-dummy")
    for key in M30_KEYS:
        monkeypatch.delenv(key, raising=False)


class _Clock:
    """DEADLINE 계측용 가짜 시계 — 테스트가 t 를 직접 전진시킨다."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _timeout_exc() -> Exception:
    return httpx.ReadTimeout("timed out")


def _status_exc(code: int) -> Exception:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return httpx.HTTPStatusError(
        f"{code}", request=request, response=httpx.Response(code, request=request)
    )


def _raise(exc):
    def _fn(*a, **k):
        raise exc

    return _fn


def _ollama_ok(text="로컬 응답"):
    def _fn(model, prompt, timeout_s):
        return f"{text}({model})"

    return _fn


def _ollama_all_fail(model, prompt, timeout_s):
    raise _timeout_exc()


def _external_forbidden(*args, **kwargs):
    raise AssertionError("tier='local' 인데 외부 호출이 발생했다 — M-17 티어 정책 위반")


def _record_local_timeouts(monkeypatch, outcomes=None):
    """local 시도별로 전달된 timeout 을 수집. outcomes=None 이면 항상 성공."""
    seen: list[float] = []

    def _fn(model, prompt, timeout_s):
        seen.append(timeout_s)
        if outcomes is not None:
            result = outcomes[len(seen) - 1]
            if isinstance(result, Exception):
                raise result
            return result
        return f"ok({model})"

    monkeypatch.setattr(llm_adapter, "_call_ollama", _fn)
    return seen


# ── 시그니처 동결 (M-30 ①) ─────────────────────────────────

def test_adapter_signature_is_frozen():
    """skeleton-v3 §4: complete(prompt, tier, timeout_s=None)."""
    sig = inspect.signature(complete)
    assert list(sig.parameters) == ["prompt", "tier", "timeout_s"]
    assert sig.parameters["timeout_s"].default is None


def test_adapter_m30_defaults():
    """M-30 ② 확정값이 env 미설정 상태의 기본값이어야 한다."""
    assert llm_adapter.local_timeout_s() == 25.0
    assert llm_adapter.external_timeout_s() == 8.0
    assert llm_adapter.deadline_s() == 27.0
    assert llm_adapter.num_predict() == 200
    assert llm_adapter.external_model() == "gpt-4o-mini"
    assert llm_adapter.external_provider() == "openai"


def test_adapter_legacy_timeout_keys_are_ignored(monkeypatch):
    """R4: 구 키 EXTERNAL_LLM_TIMEOUT_S·LOCAL_FALLBACK_TIMEOUT_S 는 읽지 않는다."""
    monkeypatch.setenv("EXTERNAL_LLM_TIMEOUT_S", "99")
    monkeypatch.setenv("LOCAL_FALLBACK_TIMEOUT_S", "99")

    assert llm_adapter.external_timeout_s() == 8.0
    assert llm_adapter.local_timeout_s() == 25.0


def test_adapter_num_predict_rejects_invalid(monkeypatch, caplog):
    """0 이하·비숫자는 기본값 폴백 + WARNING (M-30 ②)."""
    monkeypatch.setenv("LLM_NUM_PREDICT", "0")
    with caplog.at_level("WARNING"):
        assert llm_adapter.num_predict() == 200
    assert "0 이하" in caplog.text

    caplog.clear()
    monkeypatch.setenv("LLM_NUM_PREDICT", "abc")
    with caplog.at_level("WARNING"):
        assert llm_adapter.num_predict() == 200
    assert "정수가 아님" in caplog.text

    monkeypatch.setenv("LLM_NUM_PREDICT", "100")
    assert llm_adapter.num_predict() == 100


# ── 티어별 설정값 적용 (M-30 ①②) ───────────────────────────

def test_adapter_external_uses_tier_setting_when_none(monkeypatch):
    seen = {}

    def _ext(model, prompt, timeout_s, api_key):
        seen.update(model=model, timeout_s=timeout_s)
        return "external 응답"

    monkeypatch.setattr(llm_adapter, "_call_external", _ext)
    monkeypatch.setattr(llm_adapter, "_call_ollama", _external_forbidden)

    r = complete("안전화 규정?", "external")  # timeout_s 생략 → 티어 설정값

    assert r.tier_used == "external"
    assert r.model == "gpt-4o-mini"
    assert r.error is None
    assert seen["timeout_s"] == 8.0


def test_adapter_external_tier_setting_from_env(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT_EXTERNAL_S", "3.5")
    seen = {}
    monkeypatch.setattr(
        llm_adapter,
        "_call_external",
        lambda model, prompt, timeout_s, api_key: (seen.update(timeout_s=timeout_s), "ok")[1],
    )
    monkeypatch.setattr(llm_adapter, "_call_ollama", _external_forbidden)

    complete("q", "external")

    assert seen["timeout_s"] == 3.5


def test_adapter_explicit_timeout_overrides_tier_setting(monkeypatch):
    """명시 전달 시 그 값이 시도별 timeout (DEADLINE 상한은 별도 적용)."""
    seen = {}
    monkeypatch.setattr(
        llm_adapter,
        "_call_external",
        lambda model, prompt, timeout_s, api_key: (seen.update(timeout_s=timeout_s), "ok")[1],
    )
    monkeypatch.setattr(llm_adapter, "_call_ollama", _external_forbidden)

    complete("q", "external", timeout_s=2.0)

    assert seen["timeout_s"] == 2.0


def test_adapter_local_uses_tier_setting_when_none(monkeypatch):
    seen = _record_local_timeouts(monkeypatch)
    monkeypatch.setattr(llm_adapter, "_call_external", _external_forbidden)

    r = complete("사업장 지식 질문", "local")

    assert r.tier_used == "local"
    assert r.model == "qwen3:8b"
    assert seen == [25.0]


def test_adapter_local_tier_setting_from_env(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT_LOCAL_S", "10")
    seen = _record_local_timeouts(monkeypatch)
    monkeypatch.setattr(llm_adapter, "_call_external", _external_forbidden)

    complete("q", "local")

    assert seen == [10.0]


def test_adapter_local_explicit_timeout_overrides(monkeypatch):
    seen = _record_local_timeouts(monkeypatch)
    monkeypatch.setattr(llm_adapter, "_call_external", _external_forbidden)

    complete("q", "local", timeout_s=4.0)

    assert seen == [4.0]


def test_adapter_external_fallback_local_uses_local_tier_setting(monkeypatch):
    """M-30 ②: external 폴백 후 로컬도 LLM_TIMEOUT_LOCAL_S (LOCAL_FALLBACK_TIMEOUT_S 폐지)."""
    monkeypatch.setenv("LLM_TIMEOUT_LOCAL_S", "12")
    monkeypatch.setattr(llm_adapter, "_call_external", _raise(_timeout_exc()))
    seen = _record_local_timeouts(monkeypatch)

    r = complete("q", "external")

    assert r.tier_used == "local"
    assert seen == [12.0]


# ── DEADLINE (M-30 예산 규칙) ──────────────────────────────

def test_adapter_deadline_shrinks_attempt_timeout(monkeypatch):
    """각 시도 직전 timeout = min(티어 timeout, 잔여)."""
    clock = _Clock()
    monkeypatch.setattr(llm_adapter, "_now", clock)
    monkeypatch.setattr(llm_adapter, "_call_external", _external_forbidden)

    seen: list[float] = []

    def _fn(model, prompt, timeout_s):
        seen.append(timeout_s)
        if model == "qwen3:8b":
            clock.t = 20.0  # 20초 소진
            raise _timeout_exc()
        return "4b 응답"

    monkeypatch.setattr(llm_adapter, "_call_ollama", _fn)

    r = complete("q", "local")  # deadline 27, local 25

    assert seen == [25.0, 7.0]  # 1차 min(25,27)=25 / 2차 min(25, 27-20)=7
    assert r.tier_used == "local"
    assert r.model == "qwen3:4b"
    assert r.error is None


def test_adapter_deadline_skips_attempt_when_exhausted(monkeypatch, caplog):
    """잔여 ≤ 0 이면 시도를 생략하고 사유를 남긴다."""
    clock = _Clock()
    monkeypatch.setattr(llm_adapter, "_now", clock)
    monkeypatch.setattr(llm_adapter, "_call_external", _external_forbidden)

    calls: list[str] = []

    def _fn(model, prompt, timeout_s):
        calls.append(model)
        clock.t = 30.0  # deadline 27 초과
        raise _timeout_exc()

    monkeypatch.setattr(llm_adapter, "_call_ollama", _fn)

    with caplog.at_level("WARNING"):
        r = complete("q", "local")

    assert calls == ["qwen3:8b"]  # 4b 는 시도 자체가 생략
    assert r.error is not None
    assert "qwen3:8b:timeout" in r.error
    assert "qwen3:4b:deadline_exceeded" in r.error
    assert "DEADLINE 잔여 소진" in caplog.text


def test_adapter_deadline_zero_skips_all_attempts(monkeypatch):
    """LLM_DEADLINE_S=0 이면 external·local 시도 전부 생략."""
    monkeypatch.setenv("LLM_DEADLINE_S", "0")
    monkeypatch.setattr(llm_adapter, "_call_external", _external_forbidden)
    monkeypatch.setattr(llm_adapter, "_call_ollama", _external_forbidden)

    r = complete("q", "external")

    assert r.text == ""
    assert r.error is not None
    assert "external_failed[deadline_exceeded]" in r.error
    assert "qwen3:8b:deadline_exceeded" in r.error
    assert "qwen3:4b:deadline_exceeded" in r.error


# ── external 폴백 경로 (M-17a) ─────────────────────────────

def test_adapter_external_timeout_falls_back_to_local(monkeypatch, caplog):
    monkeypatch.setattr(llm_adapter, "_call_external", _raise(_timeout_exc()))
    monkeypatch.setattr(llm_adapter, "_call_ollama", _ollama_ok())

    with caplog.at_level("WARNING"):
        r = complete("안전화 규정?", "external")

    assert r.tier_used == "local"
    assert r.model == "qwen3:8b"
    assert r.error is None
    assert "external(gpt-4o-mini) → local(qwen3:8b)" in caplog.text
    assert "원인=timeout" in caplog.text


@pytest.mark.parametrize("code", [400, 401, 429, 500, 503])
def test_adapter_external_any_error_falls_back_to_local(monkeypatch, code):
    """M-17a 문언 그대로 — 4xx/5xx 구분 없이 전부 로컬 폴백."""
    monkeypatch.setattr(llm_adapter, "_call_external", _raise(_status_exc(code)))
    monkeypatch.setattr(llm_adapter, "_call_ollama", _ollama_ok())

    r = complete("안전화 규정?", "external")

    assert r.tier_used == "local"
    assert r.error is None


def test_adapter_no_api_key_falls_back_to_local(monkeypatch, caplog):
    """WORKORDER SB V2-1 확인 방법: 외부 키 제거 상태 호출 → local 폴백."""
    monkeypatch.setenv("EXTERNAL_LLM_API_KEY", "")
    monkeypatch.setattr(llm_adapter, "_call_external", _external_forbidden)
    monkeypatch.setattr(llm_adapter, "_call_ollama", _ollama_ok())

    with caplog.at_level("WARNING"):
        r = complete("안전화 규정?", "external")

    assert r.tier_used == "local"
    assert "원인=no_api_key" in caplog.text


def test_adapter_unsupported_provider_falls_back_to_local(monkeypatch):
    """M-17a 벤더 = OpenAI 고정. 다른 provider 지정 시 외부를 타지 않는다."""
    monkeypatch.setenv("EXTERNAL_LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(llm_adapter, "_call_external", _external_forbidden)
    monkeypatch.setattr(llm_adapter, "_call_ollama", _ollama_ok())

    r = complete("안전화 규정?", "external")

    assert r.tier_used == "local"


# ── local 경로 (M-03) ──────────────────────────────────────

def test_adapter_local_8b_failure_falls_back_to_4b(monkeypatch, caplog):
    calls: list[str] = []

    def _fn(model, prompt, timeout_s):
        calls.append(model)
        if model == "qwen3:8b":
            raise _status_exc(500)
        return f"4b 응답({model})"

    monkeypatch.setattr(llm_adapter, "_call_ollama", _fn)
    monkeypatch.setattr(llm_adapter, "_call_external", _external_forbidden)

    with caplog.at_level("WARNING"):
        r = complete("사업장 지식 질문", "local")

    assert calls == ["qwen3:8b", "qwen3:4b"]
    assert r.tier_used == "local"
    assert r.model == "qwen3:4b"
    assert r.error is None
    assert "local(qwen3:8b) → local(qwen3:4b)" in caplog.text


def test_adapter_local_tier_never_calls_external(monkeypatch):
    """M-17 티어 정책: 사업장 지식·상담·위험보고·PII = 로컬 고정."""
    monkeypatch.setattr(llm_adapter, "_call_ollama", _ollama_all_fail)
    monkeypatch.setattr(llm_adapter, "_call_external", _external_forbidden)

    r = complete("PII 포함 질문", "local")

    assert r.tier_used == "local"
    assert r.error is not None


def test_adapter_all_tiers_down_returns_error(monkeypatch):
    monkeypatch.setattr(llm_adapter, "_call_external", _raise(_status_exc(503)))
    monkeypatch.setattr(llm_adapter, "_call_ollama", _ollama_all_fail)

    r = complete("안전화 규정?", "external")

    assert r.text == ""
    assert r.error is not None
    assert "external_failed[http_503]" in r.error
    assert "qwen3:8b:timeout" in r.error and "qwen3:4b:timeout" in r.error
    assert r.tier_used == "local"


# ── ollama 페이로드 (M-30 ③) ───────────────────────────────

def _ollama_http_response(text: str) -> httpx.Response:
    request = httpx.Request("POST", "http://127.0.0.1:1/api/generate")
    return httpx.Response(200, json={"response": text}, request=request)


def test_adapter_ollama_payload_has_think_false_and_num_predict(monkeypatch):
    seen = {}

    def _post(url, json=None, timeout=None, **kwargs):
        seen.update(url=url, json=json, timeout=timeout)
        return _ollama_http_response("응답")

    monkeypatch.setattr(llm_adapter.httpx, "post", _post)

    out = llm_adapter._call_ollama("qwen3:8b", "질문", 25.0)

    assert out == "응답"
    assert seen["url"] == "http://127.0.0.1:1/api/generate"
    assert seen["timeout"] == 25.0
    assert seen["json"]["think"] is False
    assert seen["json"]["options"] == {"num_predict": 200}
    assert seen["json"]["stream"] is False
    assert seen["json"]["model"] == "qwen3:8b"


def test_adapter_ollama_payload_num_predict_from_env(monkeypatch):
    monkeypatch.setenv("LLM_NUM_PREDICT", "100")
    seen = {}
    monkeypatch.setattr(
        llm_adapter.httpx,
        "post",
        lambda url, json=None, timeout=None, **k: (
            seen.update(json=json),
            _ollama_http_response("ok"),
        )[1],
    )

    llm_adapter._call_ollama("qwen3:4b", "q", 25.0)

    assert seen["json"]["options"] == {"num_predict": 100}


def test_adapter_external_payload_has_no_think(monkeypatch):
    """M-30 ③ 은 로컬 전용 — external 페이로드는 무변경."""
    seen = {}

    def _post(url, headers=None, json=None, timeout=None, **kwargs):
        seen.update(json=json)
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
            request=request,
        )

    monkeypatch.setattr(llm_adapter.httpx, "post", _post)

    llm_adapter._call_external("gpt-4o-mini", "q", 8.0, "sk-x")

    assert "think" not in seen["json"]
    assert "options" not in seen["json"]


# ── <think> 제거 (M-30 ③) ─────────────────────────────────

def test_strip_think_removes_closed_block(caplog):
    with caplog.at_level("WARNING"):
        out = llm_adapter._strip_think("<think>추론 과정</think>\n실제 답변", "qwen3:8b")
    assert out == "실제 답변"
    assert "<think> 블록이 응답에 포함됨" in caplog.text


def test_strip_think_removes_unclosed_block():
    out = llm_adapter._strip_think("답변 앞부분\n<think>잘린 추론…", "qwen3:8b")
    assert out == "답변 앞부분"


def test_strip_think_is_case_insensitive():
    out = llm_adapter._strip_think("<THINK>추론</Think>  답변  ", "qwen3:8b")
    assert out == "답변"


def test_strip_think_keeps_plain_text(caplog):
    with caplog.at_level("WARNING"):
        out = llm_adapter._strip_think("  근거 기반 답변  ", "qwen3:8b")
    assert out == "근거 기반 답변"
    assert "블록이 응답에 포함됨" not in caplog.text


def test_adapter_complete_strips_think_on_local_path(monkeypatch):
    monkeypatch.setattr(
        llm_adapter,
        "_call_ollama",
        lambda model, prompt, timeout_s: "<think>내부 추론</think>안전화를 착용하세요.",
    )
    monkeypatch.setattr(llm_adapter, "_call_external", _external_forbidden)

    r = complete("q", "local")

    assert r.text == "안전화를 착용하세요."


# ── M-03a 폴백 env ────────────────────────────────────────

def test_adapter_m03a_fallback_env(monkeypatch):
    """M-03a: OLLAMA_MODEL=qwen3:4b + LLM_NUM_PREDICT=100 로도 정상 동작(코드 무변경)."""
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:4b")
    monkeypatch.setenv("LLM_NUM_PREDICT", "100")
    monkeypatch.setattr(llm_adapter, "_call_external", _external_forbidden)

    calls: list[str] = []

    def _fn(model, prompt, timeout_s):
        calls.append(model)
        return "4b 응답"

    monkeypatch.setattr(llm_adapter, "_call_ollama", _fn)

    r = complete("프레스 작업 전 점검", "local")

    assert calls == ["qwen3:4b"]  # 주력==폴백 → 중복 시도 없음
    assert r.tier_used == "local"
    assert r.model == "qwen3:4b"
    assert r.error is None
    assert llm_adapter.num_predict() == 100


# ── /health 프로브 ────────────────────────────────────────

def _tags_response(models: list[dict]) -> httpx.Response:
    request = httpx.Request("GET", "http://127.0.0.1:1/api/tags")
    return httpx.Response(200, json={"models": models}, request=request)


def test_adapter_probe_ok_when_primary_model_loaded(monkeypatch):
    monkeypatch.setattr(
        llm_adapter.httpx,
        "get",
        lambda *a, **k: _tags_response([{"name": "qwen3:8b"}, {"name": "qwen3:4b"}]),
    )
    p = llm_adapter.probe()
    assert p["status"] == "ok"
    assert p["loaded"] == {"qwen3:8b": True, "qwen3:4b": True}
    assert p["external"] == "configured"


def test_adapter_probe_degraded_when_model_missing(monkeypatch):
    monkeypatch.setattr(llm_adapter.httpx, "get", lambda *a, **k: _tags_response([]))
    p = llm_adapter.probe()
    assert p["status"] == "degraded"
    assert p["loaded"] == {"qwen3:8b": False, "qwen3:4b": False}


def test_adapter_probe_fail_when_ollama_unreachable(monkeypatch):
    monkeypatch.setattr(llm_adapter.httpx, "get", _raise(httpx.ConnectError("refused")))
    p = llm_adapter.probe()
    assert p["status"] == "fail"
    assert p["error"] == "ConnectError"


def test_adapter_embed_is_implemented():
    """embed 는 V2-2(M-02a)에서 구현됨 — 상세 계약은 tests/test_rag_ask.py."""
    assert not isinstance(llm_adapter.embed, type(None))
    assert llm_adapter.embed([]) == []
    assert llm_adapter.embed_model() == "bge-m3"
    assert llm_adapter.EMBED_DIM == 1024
