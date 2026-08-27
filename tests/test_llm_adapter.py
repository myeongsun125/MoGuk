"""llm_adapter 단위 테스트 — 네트워크 없음(_call_ollama/_call_external monkeypatch). [새봄]

검증 대상 계약:
- skeleton-v3 §4 동결 시그니처(timeout_s 기본값 20)
- M-17a: external = gpt-4o-mini, 8s, timeout/오류 전부 → local 자동 폴백(상태코드 구분 없음)
- M-03: local = qwen3:8b 주력 → 실패 시 qwen3:4b 폴백
- M-17 티어 정책: tier="local" 은 외부를 절대 호출하지 않는다
- LLMResult.tier_used = 실제 사용 티어
"""

import inspect

import httpx
import pytest

from app.services import llm_adapter
from app.services.llm_adapter import complete


@pytest.fixture(autouse=True)
def _base_env(monkeypatch):
    """모든 테스트의 기준 env — 실제 네트워크로 새지 않도록 로컬 주소를 명시."""
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    monkeypatch.setenv("OLLAMA_FALLBACK_MODEL", "qwen3:4b")
    monkeypatch.setenv("EXTERNAL_LLM_API_KEY", "sk-test-dummy")
    monkeypatch.delenv("EXTERNAL_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("EXTERNAL_LLM_MODEL", raising=False)
    monkeypatch.delenv("EXTERNAL_LLM_TIMEOUT_S", raising=False)


def _timeout_exc() -> Exception:
    return httpx.ReadTimeout("timed out")


def _status_exc(code: int) -> Exception:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return httpx.HTTPStatusError(
        f"{code}", request=request, response=httpx.Response(code, request=request)
    )


def _ollama_ok(text="로컬 응답"):
    def _fn(model, prompt, timeout_s):
        return f"{text}({model})"

    return _fn


def _ollama_fail_primary_then_ok(calls: list):
    def _fn(model, prompt, timeout_s):
        calls.append(model)
        if model == "qwen3:8b":
            raise _status_exc(500)
        return f"4b 응답({model})"

    return _fn


def _ollama_all_fail(model, prompt, timeout_s):
    raise _timeout_exc()


def _external_forbidden(*args, **kwargs):
    raise AssertionError("tier='local' 인데 외부 호출이 발생했다 — M-17 티어 정책 위반")


# ── 시그니처 동결 ───────────────────────────────────────────

def test_adapter_signature_is_frozen():
    """skeleton-v3 §4: complete(prompt, tier, timeout_s=20). 기본값 20 유지."""
    sig = inspect.signature(complete)
    assert list(sig.parameters) == ["prompt", "tier", "timeout_s"]
    assert sig.parameters["timeout_s"].default == 20


def test_adapter_external_timeout_setting_is_8s():
    """M-17a 8s 는 설정값으로 보유하고 호출부가 명시 전달한다."""
    assert llm_adapter.external_timeout_s() == 8.0
    assert llm_adapter.external_model() == "gpt-4o-mini"
    assert llm_adapter.external_provider() == "openai"


# ── external 경로 ───────────────────────────────────────────

def test_adapter_external_success_records_external_tier(monkeypatch):
    seen = {}

    def _ext(model, prompt, timeout_s, api_key):
        seen.update(model=model, timeout_s=timeout_s)
        return "external 응답"

    monkeypatch.setattr(llm_adapter, "_call_external", _ext)
    monkeypatch.setattr(llm_adapter, "_call_ollama", _external_forbidden)

    r = complete("안전화 규정?", "external", timeout_s=llm_adapter.external_timeout_s())

    assert r.tier_used == "external"
    assert r.model == "gpt-4o-mini"
    assert r.text == "external 응답"
    assert r.error is None
    assert seen["timeout_s"] == 8.0


def test_adapter_external_timeout_falls_back_to_local(monkeypatch, caplog):
    monkeypatch.setattr(llm_adapter, "_call_external", lambda *a, **k: (_ for _ in ()).throw(_timeout_exc()))
    monkeypatch.setattr(llm_adapter, "_call_ollama", _ollama_ok())

    with caplog.at_level("WARNING"):
        r = complete("안전화 규정?", "external", timeout_s=8)

    assert r.tier_used == "local"
    assert r.model == "qwen3:8b"
    assert r.error is None
    assert "external(gpt-4o-mini) → local(qwen3:8b)" in caplog.text
    assert "원인=timeout" in caplog.text


@pytest.mark.parametrize("code", [400, 401, 429, 500, 503])
def test_adapter_external_any_error_falls_back_to_local(monkeypatch, code):
    """M-17a 문언 그대로 — 4xx/5xx 구분 없이 전부 로컬 폴백."""
    monkeypatch.setattr(
        llm_adapter, "_call_external", lambda *a, **k: (_ for _ in ()).throw(_status_exc(code))
    )
    monkeypatch.setattr(llm_adapter, "_call_ollama", _ollama_ok())

    r = complete("안전화 규정?", "external", timeout_s=8)

    assert r.tier_used == "local"
    assert r.error is None


def test_adapter_no_api_key_falls_back_to_local(monkeypatch, caplog):
    """WORKORDER SB V2-1 확인 방법: 외부 키 제거 상태 호출 → local 폴백."""
    monkeypatch.setenv("EXTERNAL_LLM_API_KEY", "")
    monkeypatch.setattr(llm_adapter, "_call_external", _external_forbidden)
    monkeypatch.setattr(llm_adapter, "_call_ollama", _ollama_ok())

    with caplog.at_level("WARNING"):
        r = complete("안전화 규정?", "external", timeout_s=8)

    assert r.tier_used == "local"
    assert "원인=no_api_key" in caplog.text


def test_adapter_unsupported_provider_falls_back_to_local(monkeypatch):
    """M-17a 벤더 = OpenAI 고정. 다른 provider 지정 시 외부를 타지 않는다."""
    monkeypatch.setenv("EXTERNAL_LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(llm_adapter, "_call_external", _external_forbidden)
    monkeypatch.setattr(llm_adapter, "_call_ollama", _ollama_ok())

    r = complete("안전화 규정?", "external", timeout_s=8)

    assert r.tier_used == "local"


# ── local 경로 (M-03) ───────────────────────────────────────

def test_adapter_local_primary_success(monkeypatch):
    monkeypatch.setattr(llm_adapter, "_call_ollama", _ollama_ok())
    monkeypatch.setattr(llm_adapter, "_call_external", _external_forbidden)

    r = complete("사업장 지식 질문", "local")

    assert r.tier_used == "local"
    assert r.model == "qwen3:8b"
    assert r.error is None


def test_adapter_local_8b_failure_falls_back_to_4b(monkeypatch, caplog):
    calls: list[str] = []
    monkeypatch.setattr(llm_adapter, "_call_ollama", _ollama_fail_primary_then_ok(calls))
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

    r = complete("PII 포함 질문", "local")  # 전멸해도 외부로 새지 않아야 한다

    assert r.tier_used == "local"
    assert r.error is not None


# ── 전멸 ────────────────────────────────────────────────────

def test_adapter_all_tiers_down_returns_error(monkeypatch):
    monkeypatch.setattr(
        llm_adapter, "_call_external", lambda *a, **k: (_ for _ in ()).throw(_status_exc(503))
    )
    monkeypatch.setattr(llm_adapter, "_call_ollama", _ollama_all_fail)

    r = complete("안전화 규정?", "external", timeout_s=8)

    assert r.text == ""
    assert r.error is not None
    assert "external_failed[http_503]" in r.error
    assert "qwen3:8b:timeout" in r.error and "qwen3:4b:timeout" in r.error
    assert r.tier_used == "local"


# ── /health 프로브 ──────────────────────────────────────────

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
    monkeypatch.setattr(
        llm_adapter.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("refused"))
    )
    p = llm_adapter.probe()
    assert p["status"] == "fail"
    assert p["error"] == "ConnectError"


def test_adapter_embed_still_unimplemented():
    """embed 는 V2-2(RAG) 의존 — 이번 구간 미교체임을 고정."""
    with pytest.raises(NotImplementedError):
        llm_adapter.embed(["텍스트"])
