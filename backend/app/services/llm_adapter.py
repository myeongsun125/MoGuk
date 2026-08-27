"""LLM 단일 진입점 — M-03(qwen3:8b 주력/4b 폴백), M-17·M-17a(외부 = gpt-4o-mini), M-30(timeout 체계). [새봄]

계약(변경 금지):
- skeleton-v3 §4 동결 시그니처 — `complete(prompt, tier, timeout_s=None)`.
  timeout_s=None → 티어별 설정값(M-30). 명시 전달 시 그 값이 해당 티어의 시도별 timeout 이 되며,
  어느 경우든 LLM_DEADLINE_S 상한이 항상 적용된다.
- tier="external": openai gpt-4o-mini. timeout/오류 전부(상태코드 구분 없음) → 로컬 자동 폴백.
- tier="local": qwen3:8b 주력 → 실패 시 qwen3:4b 폴백. 외부는 절대 타지 않는다(M-17 티어 정책).
- LLMResult.tier_used 에 실제 사용 티어 기록. 폴백 시 원인·원티어→폴백티어를 WARNING 로그로 남긴다.
- 외부 HTTP 호출은 이 모듈에만 존재한다 — 다른 모듈의 직접 httpx 호출 금지.
- ollama 호출은 think:false + options.num_predict 를 항상 전달하고, 응답의 `<think>` 블록을 제거한다
  (M-30 ③). external 경로에는 적용하지 않는다.

M-30 예산 규칙:
- complete() 진입 시점부터 LLM_DEADLINE_S 를 계측한다.
- 각 시도 직전 timeout = min(티어 timeout, 잔여). 잔여 ≤ 0 이면 그 시도를 생략하고 사유를 남긴다.

env 키 (M-30 확정 / 구 키 EXTERNAL_LLM_TIMEOUT_S·LOCAL_FALLBACK_TIMEOUT_S 는 폐지 — 하위호환 읽기 없음, R4):
- LLM_TIMEOUT_LOCAL_S=25.0    로컬 시도별 timeout (local 직접 호출 + external 폴백 후 로컬 통합)
- LLM_TIMEOUT_EXTERNAL_S=8.0  외부 시도별 timeout (M-17a)
- LLM_DEADLINE_S=27.0         요청당 총 예산
- LLM_NUM_PREDICT=200         ollama options.num_predict (int, 0 이하·비숫자는 기본값 폴백 + WARNING)
- LLM_PROBE_TIMEOUT_S=2.0     /health 프로브
- 기존: OLLAMA_URL, OLLAMA_MODEL, OLLAMA_FALLBACK_MODEL, OLLAMA_KEEP_ALIVE,
  EXTERNAL_LLM_API_KEY(빈 값 = 외부 비활성 → 즉시 로컬 폴백),
  EXTERNAL_LLM_PROVIDER=openai, EXTERNAL_LLM_MODEL=gpt-4o-mini,
  EXTERNAL_LLM_BASE_URL=https://api.openai.com/v1
※ .env.example·compose 등재는 BG 소유 — 이 모듈은 미등재 상태에서도 기본값으로 동작한다.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Callable, Literal

import httpx

log = logging.getLogger(__name__)

Tier = Literal["local", "external"]

# M-30 확정값 (env 미설정 시 기본값)
DEFAULT_LOCAL_TIMEOUT_S = 25.0
DEFAULT_EXTERNAL_TIMEOUT_S = 8.0
DEFAULT_DEADLINE_S = 27.0
DEFAULT_NUM_PREDICT = 200
DEFAULT_PROBE_TIMEOUT_S = 2.0
SUPPORTED_EXTERNAL_PROVIDERS = ("openai",)

# M-02 비가역: bge-m3 / 1024 고정. M-02a: 런타임 = ollama /api/embed 단일.
DEFAULT_EMBED_MODEL = "bge-m3"
EMBED_DIM = 1024

# 예산 계측용 — 테스트가 이 이름을 monkeypatch 한다.
_now: Callable[[], float] = time.perf_counter


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


def _env_int_positive(name: str, default: int) -> int:
    """0 이하·비숫자는 기본값으로 폴백하고 WARNING (M-30 ②)."""
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        log.warning("llm_adapter: env %s=%r 가 정수가 아님 — 기본값 %s 사용", name, raw, default)
        return default
    if value <= 0:
        log.warning("llm_adapter: env %s=%r 가 0 이하 — 기본값 %s 사용", name, raw, default)
        return default
    return value


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


def local_timeout_s() -> float:
    """M-30: 로컬 시도별 timeout. external 폴백 후 로컬에도 동일 적용."""
    return _env_float("LLM_TIMEOUT_LOCAL_S", DEFAULT_LOCAL_TIMEOUT_S)


def external_timeout_s() -> float:
    """M-30·M-17a: 외부 시도별 timeout."""
    return _env_float("LLM_TIMEOUT_EXTERNAL_S", DEFAULT_EXTERNAL_TIMEOUT_S)


def deadline_s() -> float:
    """M-30: 요청당 총 예산. complete() 진입부터 계측."""
    return _env_float("LLM_DEADLINE_S", DEFAULT_DEADLINE_S)


def num_predict() -> int:
    return _env_int_positive("LLM_NUM_PREDICT", DEFAULT_NUM_PREDICT)


def embed_model() -> str:
    """M-02a: 임베딩 런타임은 ollama 단일. 모델은 bge-m3 고정(M-02)."""
    return _env("EMBED_MODEL", DEFAULT_EMBED_MODEL)


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
            "think": False,  # M-30 ③
            "options": {"num_predict": num_predict()},
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


# ── <think> 후처리 (M-30 ③, 로컬 경로 전용) ──

_THINK_OPEN = re.compile(r"<think\s*>", re.IGNORECASE)
_THINK_BLOCK = re.compile(r"<think\s*>.*?</think\s*>", re.IGNORECASE | re.DOTALL)
_THINK_UNCLOSED = re.compile(r"<think\s*>.*", re.IGNORECASE | re.DOTALL)


def _strip_think(text: str, model: str) -> str:
    """폐합 블록 제거 → 미폐합이면 여는 태그 이후 전부 제거 → strip. think:false 인데 검출되면 WARNING."""
    if not text:
        return text
    if not _THINK_OPEN.search(text):
        return text.strip()
    log.warning(
        "llm_adapter: think=false 인데 <think> 블록이 응답에 포함됨 — 제거함 (model=%s)", model
    )
    out = _THINK_BLOCK.sub("", text)
    out = _THINK_UNCLOSED.sub("", out)
    return out.strip()


# ── 티어 실행 ──

def _run_local(
    prompt: str,
    base_timeout_s: float,
    origin: Tier,
    remaining: Callable[[], float],
) -> tuple[str | None, str, str]:
    """(text|None, 사용 모델, 실패 사유). M-03: 8b 주력 → 실패 시 4b 폴백. 시도마다 DEADLINE 잔여 확인."""
    primary, fallback = local_model(), local_fallback_model()
    candidates = [primary] if primary == fallback else [primary, fallback]
    failures: list[str] = []
    for model in candidates:
        left = remaining()
        if left <= 0:
            failures.append(f"{model}:deadline_exceeded")
            log.warning(
                "llm_adapter: DEADLINE 잔여 소진 — local(%s) 시도 생략 · 원티어=%s", model, origin
            )
            continue
        try:
            text = _call_ollama(model, prompt, min(base_timeout_s, left))
            return _strip_think(text, model), model, ""
        except Exception as exc:  # noqa: BLE001 — 어떤 실패든 다음 모델로 내려간다
            reason = _reason(exc)
            failures.append(f"{model}:{reason}")
            if model == primary and len(candidates) > 1:
                log.warning(
                    "llm_adapter 폴백: local(%s) → local(%s) · 원인=%s · 원티어=%s",
                    primary, fallback, reason, origin,
                )
    return None, candidates[-1], ",".join(failures)


def complete(
    prompt: str, tier: Literal["local", "external"], timeout_s: float | None = None
) -> LLMResult:
    """단일 진입점. external 은 timeout/오류 전부 로컬로 자동 폴백한다(M-17a). 예산 = M-30."""
    t0 = _now()
    deadline = deadline_s()

    def elapsed() -> int:
        return int((_now() - t0) * 1000)

    def remaining() -> float:
        return deadline - (_now() - t0)

    external_reason = ""
    if tier == "external":
        model = external_model()
        api_key = os.getenv("EXTERNAL_LLM_API_KEY") or ""
        provider = external_provider()
        ext_timeout = external_timeout_s() if timeout_s is None else timeout_s
        left = remaining()
        if not api_key:
            external_reason = "no_api_key"
        elif provider not in SUPPORTED_EXTERNAL_PROVIDERS:
            external_reason = f"unsupported_provider:{provider}"
        elif left <= 0:
            external_reason = "deadline_exceeded"
        else:
            try:
                text = _call_external(model, prompt, min(ext_timeout, left), api_key)
                return LLMResult(text=text, tier_used="external", model=model, latency_ms=elapsed())
            except Exception as exc:  # noqa: BLE001 — 상태코드 구분 없이 전부 로컬 폴백(M-17a)
                external_reason = _reason(exc)
        log.warning(
            "llm_adapter 폴백: external(%s) → local(%s) · 원인=%s",
            model, local_model(), external_reason,
        )
        # 폴백 후 로컬은 항상 LLM_TIMEOUT_LOCAL_S (M-30 ②: local 직접·폴백 통합)
        text, used_model, local_reason = _run_local(
            prompt, local_timeout_s(), "external", remaining
        )
    else:
        local_base = local_timeout_s() if timeout_s is None else timeout_s
        text, used_model, local_reason = _run_local(prompt, local_base, "local", remaining)

    if text is not None:
        return LLMResult(text=text, tier_used="local", model=used_model, latency_ms=elapsed())

    error = f"local_failed[{local_reason}]"
    if external_reason:
        error = f"external_failed[{external_reason}] -> {error}"
    log.error("llm_adapter: 전 티어 실패 · %s", error)
    return LLMResult(text="", tier_used="local", model=used_model, latency_ms=elapsed(), error=error)


def _call_ollama_embed(model: str, texts: list[str], timeout_s: float) -> list[list[float]]:
    r = httpx.post(
        f"{ollama_url()}/api/embed",
        json={"model": model, "input": texts, "keep_alive": _env("OLLAMA_KEEP_ALIVE", "10m")},
        timeout=timeout_s,
    )
    r.raise_for_status()
    return r.json()["embeddings"]


def embed(texts: list[str]) -> list[list[float]]:
    """bge-m3 / 1024 고정(M-02 비가역). 런타임 = ollama /api/embed 단일(M-02a).

    인제스천(Dagster)과 질의(어댑터)가 같은 런타임을 써야 벡터가 일치한다 — 다른 런타임 혼용 금지.
    차원이 1024가 아니면 적재·질의 정합이 깨지므로 즉시 예외를 올린다.
    """
    if not texts:
        return []
    model = embed_model()
    vectors = _call_ollama_embed(model, texts, local_timeout_s())
    if len(vectors) != len(texts):
        raise ValueError(
            f"embed: 입력 {len(texts)}건 대비 벡터 {len(vectors)}건 반환 (model={model})"
        )
    for i, vec in enumerate(vectors):
        if len(vec) != EMBED_DIM:
            raise ValueError(
                f"embed: 차원 불일치 — {len(vec)} != {EMBED_DIM} (M-02 고정, model={model}, idx={i})"
            )
    return vectors


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
