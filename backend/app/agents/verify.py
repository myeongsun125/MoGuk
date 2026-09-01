"""백트랜슬레이션 검증 + 고위험 판정 (M-10). τ = env GATE_TAU (M-34 c). [새봄]"""

from __future__ import annotations

import logging
import math
import os
import time
import unicodedata
from dataclasses import dataclass

from app.agents.classify import Cls
from app.agents.retrieve import Chunk
from app.services import glossary_terms
from app.services.llm_adapter import complete, embed

log = logging.getLogger(__name__)

# M-34 c: τ 는 상수가 아니라 env. tenant_settings·001 무접촉(테넌트별 조정은 범위 밖).
DEFAULT_GATE_TAU = 0.80

# 되번역 프롬프트 — 최소 지시문. 출력 언어는 항상 ko(원문 대조축이 ko 이므로).
BACKTRANS_PROMPT = """다음 문장을 한국어로 번역하세요. 번역문만 출력하고 다른 말은 덧붙이지 마세요.

{text}"""

# ── 용어집 주입 (총괄 확정 0901) — 실험 사본 gloss_prompt(:79-88)와 문자열 동일 규격 ──
# env GLOSSARY_INJECT_BACKTRANS 기본 on. off 면 기존 프롬프트 바이트 동일.
INJECT_BACKTRANS_ENV = "GLOSSARY_INJECT_BACKTRANS"
GLOSS_HEAD = "다음 용어는 반드시 지정 한국어 표기로 번역: "
_TEXT_TAIL = "\n\n{text}"
assert BACKTRANS_PROMPT.endswith(_TEXT_TAIL), "원 프롬프트 말미가 '\\n\\n{text}' 가 아님 — 삽입 위치 재확인 필요"


def _flag_off(name: str) -> bool:
    """기본 on 플래그 — 명시적 off 값만 끈다."""
    return (os.getenv(name) or "").strip().lower() in ("0", "false", "off", "no")


def _norm(s: str) -> str:
    return unicodedata.normalize("NFC", s or "").casefold()


def build_backtrans_prompt(out: str, lang: str | None = None) -> tuple[str, list[tuple[str, str]]]:
    """out 에 포함된 용어집 항목만 나열한 되번역 프롬프트. 0개·off·조회 실패면 원 프롬프트.

    조립 규격 = 실험 사본과 동일: 헤드 + "src→ko" 나열(", " 구분, 용어집 순서),
    삽입 위치 = 지시문 바로 다음 행, 매칭 = NFC·casefold 부분 문자열.
    항목의 src 축은 질의 lang 이 in 이면 term_in, 그 외 term_vi.
    """
    if _flag_off(INJECT_BACKTRANS_ENV):
        return BACKTRANS_PROMPT, []
    try:
        terms = glossary_terms.fetch_terms()
    except Exception as exc:  # noqa: BLE001 — 주입은 보강이므로 조회 실패는 원 프롬프트로 폴백
        log.warning("verify: 용어집 조회 실패 — 주입 없이 되번역 진행 (%s)", exc)
        return BACKTRANS_PROMPT, []
    hay = _norm(out)
    matched = []
    for term_ko, term_vi, term_in in terms:
        src = term_in if lang == "in" else term_vi
        if not (src and term_ko):
            continue
        if _norm(src) in hay:
            matched.append((src, term_ko))
    if not matched:
        return BACKTRANS_PROMPT, []
    line = GLOSS_HEAD + ", ".join(f"{src}→{ko}" for src, ko in matched)
    line = line.replace("{", "{{").replace("}", "}}")   # str.format 보호(용어에 중괄호는 없지만 방어)
    body = BACKTRANS_PROMPT[: -len(_TEXT_TAIL)]
    return body + "\n" + line + _TEXT_TAIL, matched


@dataclass(frozen=True)
class Verify:
    score: float | None          # 게이트 판정에 쓴 점수(gate_on 이 고른 쪽)
    passed: bool
    # 실측 기록용(§3 응답 미노출 — graph 가 trace.verify 로만 싣는다)
    score_src: float | None = None    # src 대비 코사인
    score_aux: float | None = None    # aux_src 대비 코사인(미지정이면 None)
    back_text: str = ""
    back_ms: int = 0
    timed_out: bool = False
    error: str | None = None
    inj_terms: tuple = ()        # 용어집 주입 실측 (src, ko) — trace 기록용, 게이트 무관


def _env_float(name: str, default: float) -> float:
    """llm_adapter._env_float 동형 — 비숫자는 기본값 폴백 + WARNING."""
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        log.warning("verify: env %s=%r 가 숫자가 아님 — 기본값 %s 사용", name, raw, default)
        return default


def gate_tau() -> float:
    return _env_float("GATE_TAU", DEFAULT_GATE_TAU)


def cosine(a: list[float], b: list[float]) -> float:
    """순수 파이썬 코사인 — 의존성 추가 0(numpy 불요). 영벡터·길이 불일치는 0.0."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _is_timeout(error: str) -> bool:
    # llm_adapter 는 'local_failed[<model>:timeout]' · '...:deadline_exceeded' 형태로 싣는다.
    return "timeout" in error or "deadline_exceeded" in error


def _fail_open(
    error: str, *, timed_out: bool = False, back_ms: int = 0, back_text: str = ""
) -> Verify:
    """M-34 c: 검증 자체가 실패하면 답변을 막지 않는다(게이트는 오탐보다 미탐을 택한다)."""
    return Verify(
        score=None, passed=True, back_text=back_text, back_ms=back_ms,
        timed_out=timed_out, error=error,
    )


def verify_backtranslation(
    src: str,
    out: str,
    *,
    aux_src: str | None = None,
    gate_on: str = "src",
    timeout_s: float | None = None,
    lang: str | None = None,
) -> Verify:
    """out(vi/in)을 ko 로 되번역해 src 와 bge-m3 코사인 비교. score < τ 면 passed=False.

    src 가 무엇인지는 호출측(graph)이 정한다 — §4 동결 시그니처 (src, out) 유지.
    aux_src 를 주면 같은 embed 호출 1회로 두 점수를 함께 낸다(M-34 c: 질문·근거 병기).
    gate_on='aux' 면 aux 점수로 게이트한다. 타임아웃·오류는 전부 fail-open.
    lang 은 용어집 주입의 src 축 선택(in → term_in, 그 외 term_vi) — 게이트 판정 무관.
    """
    if not (src or "").strip() or not (out or "").strip():
        return _fail_open("empty_input")
    if timeout_s is not None and timeout_s <= 0:
        return _fail_open("no_budget", timed_out=True)

    prompt, injected = build_backtrans_prompt(out, lang)   # 용어집 주입(기본 on) — 실패·0개면 원 프롬프트
    t_bt = time.perf_counter()
    result = complete(prompt.format(text=out), "local", timeout_s=timeout_s)
    back_ms = int((time.perf_counter() - t_bt) * 1000)

    if result.error is not None:
        return _fail_open(result.error, timed_out=_is_timeout(result.error), back_ms=back_ms)

    back_text = result.text.strip()
    if not back_text:
        return _fail_open("empty_backtranslation", back_ms=back_ms)

    has_aux = bool((aux_src or "").strip())
    texts = [back_text, src] + ([aux_src] if has_aux else [])
    try:
        vectors = embed(texts)                      # 되번역 1회 · 임베딩 1회 (M-34 c)
    except Exception as exc:                        # 임베딩 실패도 동형 fail-open
        log.warning("verify: 임베딩 실패 — fail-open (%s)", exc)
        return _fail_open(f"embed_failed[{type(exc).__name__}]", back_ms=back_ms, back_text=back_text)

    score_src = cosine(vectors[0], vectors[1])
    score_aux = cosine(vectors[0], vectors[2]) if has_aux else None
    score = score_aux if (gate_on == "aux" and score_aux is not None) else score_src
    return Verify(
        score=score,
        passed=score >= gate_tau(),
        score_src=score_src,
        score_aux=score_aux,
        back_text=back_text,
        back_ms=back_ms,
        inj_terms=tuple(injected),
    )


SAFETY_CATEGORY = "safety"


def is_high_risk(cls: Cls | None, chunks: list[Chunk]) -> bool:
    """WORKORDER V4-1 "안전만 차단" 의 선별자 — 검색 청크에 safety 가 하나라도 있으면 고위험.

    §4 시그니처(cls, chunks) 유지. 질의분류 OR 항은 agents.classify 가 스텁이라 유보 —
    cls 를 주면 그때 OR 로 합류시킨다(현재 graph 는 None 을 넘긴다).
    """
    if cls is not None and getattr(cls, "category", None) == SAFETY_CATEGORY:
        return True
    return any(c.category == SAFETY_CATEGORY for c in chunks)
