"""LLM 단일 진입점 — M-03(qwen3:8b 주력/4b 폴백), M-17(외부 = 용어사전 주입 번역 전용). [새봄]

외부 timeout/오류 → 로컬 자동 폴백, LLMResult.tier_used 기록. 직접 httpx 호출 금지.
Mock 경계(§7): Ollama 교체 전까지 FakeLLM(고정 응답)으로 그래프 선행.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class LLMResult:
    text: str
    tier_used: Literal["local", "external"]
    model: str
    latency_ms: int
    error: str | None = None


def complete(prompt: str, tier: Literal["local", "external"], timeout_s: float = 20) -> LLMResult:
    raise NotImplementedError("[새봄] services.llm_adapter.complete")


def embed(texts: list[str]) -> list[list[float]]:
    # bge-m3 / 1024 고정 (M-02 비가역)
    raise NotImplementedError("[새봄] services.llm_adapter.embed")
