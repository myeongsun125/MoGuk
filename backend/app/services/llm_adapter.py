"""LLM 단일 진입점 — M-03(qwen3:8b 주력/4b 폴백), M-17·M-17a(외부 = gpt-4o-mini, 8s, external→local 폴백). [새봄]

계약(변경 금지):
- 시그니처는 skeleton-v3 §4 동결 — `complete(prompt, tier, timeout_s=20)`. 기본값 20 유지.
  M-17a 의 8s 는 **external 호출부가 external_timeout_s() 를 명시 전달**해 만족시킨다.
- tier="external": openai gpt-4o-mini. timeout/오류 전부(상태코드 구분 없음) → 로컬 자동 폴백.
- tier="local": qwen3:8b 주력 → 실패 시 qwen3:4b 폴백. 외부는 절대 타지 않는다(M-17 티어 정책).
- LLMResult.tier_used 에 실제 사용 티어 기록. 폴백 시 원인·원티어→폴백티어를 WARNING 로그로 남긴다.
- 외부 HTTP 호출은 이 모듈에만 존재한다 — 다른 모듈의 직접 httpx 호출 금지.

env 키:
- 기존(compose·.env.example 등재): OLLAMA_URL, OLLAMA_MODEL, OLLAMA_FALLBACK_MODEL,
  OLLAMA_KEEP_ALIVE, EXTERNAL_LLM_API_KEY(빈 값 = 외부 비활성 → 즉시 로컬 폴백)
- 미등재(.env.example 추가는 BG V2-2 소유 — 이 트랙에서 파일 수정 금지, 코드 기본값으로 동작):
  EXTERNAL_LLM_PROVIDER=openai · EXTERNAL_LLM_MODEL=gpt-4o-mini ·
  EXTERNAL_LLM_BASE_URL=https://api.openai.com/v1 · EXTERNAL_LLM_TIMEOUT_S=8 ·
  LOCAL_FALLBACK_TIMEOUT_S=20 (external 실패 후 로컬 재시도용) · LLM_PROBE_TIMEOUT_S=2 (/health)
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Literal

import httpx

log = logging.getLogger(__name__)

Tier = Literal["local", "external"]

# M-17a 확정값. 호출부가 external 을 쓸 때 timeout_s 로 명시 전달한다.
DEFAULT_EXTERNAL_TIMEOUT_S = 8.0
DEFAULT_LOCAL_FALLBACK_TIMEOUT_S = 20.0
DEFAULT_PROBE_TIMEOUT_S = 2.0
SUPPORTED_EXTERNAL_PROVIDERS = ("openai",)


@dataclass(frozen=True)
class LLMResult:
    text: str
    tier_used: Literal["local", "external"]
    model: str
    latency_ms: int
    error: str | None = None


# ── 설정 접근자 (호출 시점에 읽는다 — 재기동 없이 env 교체·테스트 monkeypatch 가능) ──

def _env(name: str, default: str) -> str:
    return os.getenv(name) or default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        log.warning("llm_adapter: env %s=%r 가 숫자가 아님 — 기본값 %s 사용", name, raw, default)
        return default


def ollama_url() -> str:
    return _env("OLLAMA_URL", "http://ollama:11434").rstrip("/")


def local_model() -> str:
    return _env("OLLAMA_MODEL", "qwen3:8b")


def local_fallback_model() -> str:
    return _env("OLLAMA_FALLBACK_MODEL", "qwen3:4b")


def external_provider() -> str:
    return _env("EXTERNAL_LLM_PROVIDER", "openai").lower()


def external_model() -> str:
    return _env("EXTERNAL_LLM_MODEL", "gpt-4o-mini")


def external_base_url() -> str:
    return _env("EXTERNAL_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def external_timeout_s() -> float:
    """M-17a: 외부 호출 타임아웃 8s. 호출부가 complete(..., timeout_s=external_timeout_s()) 로 전달."""
    return _env_float("EXTERNAL_LLM_TIMEOUT_S", DEFAULT_EXTERNAL_TIMEOUT_S)


def _local_fallback_timeout_s() -> float:
    return _env_float("LOCAL_FALLBACK_TIMEOUT_S", DEFAULT_LOCAL_FALLBACK_TIMEOUT_S)


def _probe_timeout_s() -> float:
    return _env_float("LLM_PROBE_TIMEOUT_S", DEFAULT_PROBE_TIMEOUT_S)


# ── 원시 호출 (테스트는 이 두 함수를 monkeypatch 한다) ──

def _call_ollama(model: str, prompt: str, timeout_s: float) -> str:
    r = httpx.post(
        f"{ollama_url()}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": _env("OLLAMA_KEEP_ALIVE", "10m"),
        },
        timeout=timeout_s,
    )
    r.raise_for_status()
    return r.json()["response"]


def _call_external(model: str, prompt: str, timeout_s: float, api_key: str) -> str:
    r = httpx.post(
        f"{external_base_url()}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}]},
        timeout=timeout_s,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _reason(exc: BaseException) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_{exc.response.status_code}"
    return type(exc).__name__


# ── 티어 실행 ──

def _run_local(prompt: str, timeout_s: float, origin: Tier) -> tuple[str | None, str, str]:
    """(text|None, 사용 모델, 실패 사유). M-03: 8b 주력 → 실패 시 4b 폴백."""
    primary, fallback = local_model(), local_fallback_model()
    candidates = [primary] if primary == fallback else [primary, fallback]
    failures: list[str] = []
    for model in candidates:
        try:
            return _call_ollama(model, prompt, timeout_s), model, ""
        except Exception as exc:  # noqa: BLE001 — 어떤 실패든 다음 모델로 내려간다
            reason = _reason(exc)
            failures.append(f"{model}:{reason}")
            if model == primary and len(candidates) > 1:
                log.warning(
                    "llm_adapter 폴백: local(%s) → local(%s) · 원인=%s · 원티어=%s",
                    primary, fallback, reason, origin,
                )
    return None, candidates[-1], ",".join(failures)


def complete(prompt: str, tier: Literal["local", "external"], timeout_s: float = 20) -> LLMResult:
    """단일 진입점. external 은 timeout/오류 전부 로컬로 자동 폴백한다(M-17a)."""
    t0 = time.perf_counter()

    def elapsed() -> int:
        return int((time.perf_counter() - t0) * 1000)

    external_reason = ""
    if tier == "external":
        configured = external_timeout_s()
        if timeout_s > configured:
            log.warning(
                "llm_adapter: external timeout_s=%s 가 M-17a 설정값 %ss 보다 큽니다 "
                "— 호출부가 timeout_s=external_timeout_s() 를 명시 전달해야 합니다",
                timeout_s, configured,
            )
        api_key = os.getenv("EXTERNAL_LLM_API_KEY") or ""
        provider = external_provider()
        model = external_model()
        if not api_key:
            external_reason = "no_api_key"
        elif provider not in SUPPORTED_EXTERNAL_PROVIDERS:
            external_reason = f"unsupported_provider:{provider}"
        else:
            try:
                text = _call_external(model, prompt, timeout_s, api_key)
                return LLMResult(text=text, tier_used="external", model=model, latency_ms=elapsed())
            except Exception as exc:  # noqa: BLE001 — 상태코드 구분 없이 전부 로컬 폴백(M-17a)
                external_reason = _reason(exc)
        log.warning(
            "llm_adapter 폴백: external(%s) → local(%s) · 원인=%s",
            model, local_model(), external_reason,
        )
        text, used_model, local_reason = _run_local(
            prompt, _local_fallback_timeout_s(), origin="external"
        )
    else:
        text, used_model, local_reason = _run_local(prompt, timeout_s, origin="local")

    if text is not None:
        return LLMResult(text=text, tier_used="local", model=used_model, latency_ms=elapsed())

    error = f"local_failed[{local_reason}]"
    if external_reason:
        error = f"external_failed[{external_reason}] -> {error}"
    log.error("llm_adapter: 전 티어 실패 · %s", error)
    return LLMResult(text="", tier_used="local", model=used_model, latency_ms=elapsed(), error=error)


def embed(texts: list[str]) -> list[list[float]]:
    # bge-m3 / 1024 고정 (M-02 비가역). V2-2(RAG) 의존 — 구현 백엔드 미결이라 이번 구간 미교체.
    raise NotImplementedError("[새봄] services.llm_adapter.embed")


# ── /health 용 프로브 (services/system_service.check_llm 이 호출) ──

def _normalize(name: str) -> str:
    return name if ":" in name else f"{name}:latest"


def probe() -> dict:
    """ollama 모델 탑재 여부. 예외를 밖으로 던지지 않는다 — /health 는 원인 유형만 노출."""
    primary, fallback = local_model(), local_fallback_model()
    external = "configured" if os.getenv("EXTERNAL_LLM_API_KEY") else "absent"
    try:
        r = httpx.get(f"{ollama_url()}/api/tags", timeout=_probe_timeout_s())
        r.raise_for_status()
        loaded = {_normalize(str(m.get("name", ""))) for m in r.json().get("models", [])}
    except Exception as exc:  # noqa: BLE001
        return {"status": "fail", "error": _reason(exc), "model": primary, "external": external}

    has_primary = _normalize(primary) in loaded
    has_fallback = _normalize(fallback) in loaded
    return {
        "status": "ok" if has_primary else "degraded",
        "model": primary,
        "fallback_model": fallback,
        "loaded": {primary: has_primary, fallback: has_fallback},
        "external": external,
    }
