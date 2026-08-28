"""그래프 엔트리 — classify → retrieve → translate → verify (≤3홉). [새봄]

V2-2 범위: retrieve(top-k=4) → 근거 강제 프롬프트 → complete(tier="local") → 응답 조립.
- 근거 없음(검색 0건 또는 모델이 NO_ANSWER 반환) → grounded=false → 답변 차단 + unanswered_queue(M-05).
- questions(qa_logs) 기록: grounded·sources·trace(M-09 lineage)·latency_ms.
- 티어 정책(M-17): 사업장 지식 질의는 로컬 고정 — tier="local", timeout_s=None(티어 설정값, M-30).
- verify 는 V4-1(M-10) 전이라 구조만 채운다. τ 기반 게이트 판정은 V4 에서 구현.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field

from app.agents.retrieve import Chunk, retrieve
from app.models import Worker
from app.services import tenancy
from app.services.llm_adapter import complete

log = logging.getLogger(__name__)

TOP_K = 4

# 근거가 없을 때 모델이 내야 하는 정확한 토큰. 이 값이 응답에 있으면 grounded=false 로 판정한다.
NO_ANSWER = "NO_ANSWER"

_LANG_NAME = {"vi": "베트남어", "in": "인도네시아어", "ko": "한국어"}

# 근거 강제 프롬프트 (BLUEPRINT §4-1) — 청크 밖 지식 사용 금지.
PROMPT_TEMPLATE = """당신은 제조 사업장의 안전·작업 안내 도우미입니다.

규칙(반드시 지킬 것):
1. 아래 [근거 자료]에 있는 내용만으로 답하십시오. 자료 밖의 일반 지식·추측을 절대 쓰지 마십시오.
2. 자료로 질문에 답할 수 없으면 다른 말을 덧붙이지 말고 정확히 {no_answer} 한 단어만 출력하십시오.
3. 답할 수 있으면 {lang_name}로만, 3문장 이내로 간결하게 답하십시오.

[근거 자료]
{context}

[질문]
{question}

[답변]"""


@dataclass(frozen=True)
class Answer:
    answer: str
    sources: list[dict] = field(default_factory=list)
    verify: dict = field(default_factory=dict)  # {score, passed, gated}
    trace_id: str = ""


_INSERT_QUESTION = """
INSERT INTO questions (worker_id, lang, source, question, answer, grounded, sources, trace, latency_ms)
VALUES (%(worker_id)s, %(lang)s, 'text', %(question)s, %(answer)s, %(grounded)s,
        %(sources)s::jsonb, %(trace)s::jsonb, %(latency_ms)s)
RETURNING id
"""

_INSERT_UNANSWERED = """
INSERT INTO unanswered_queue (question_id, status) VALUES (%(qid)s, 'open')
ON CONFLICT (question_id) DO NOTHING
"""


def build_context(chunks: list[Chunk]) -> str:
    """근거 블록 — 각 청크에 번호·출처를 붙여 모델이 인용 대상을 구분하게 한다."""
    blocks = []
    for i, c in enumerate(chunks, start=1):
        head = f"[{i}] 문서 {c.document_id}"
        if c.title:
            head += f" · {c.title}"
        if c.category:
            head += f" · {c.category}"
        blocks.append(f"{head}\n{c.content}")
    return "\n\n".join(blocks)


def build_prompt(question: str, lang: str, chunks: list[Chunk]) -> str:
    return PROMPT_TEMPLATE.format(
        no_answer=NO_ANSWER,
        lang_name=_LANG_NAME.get(lang, _LANG_NAME["vi"]),
        context=build_context(chunks),
        question=question,
    )


def is_no_answer(text: str) -> bool:
    """모델이 근거 부족을 신고했는지 — 규칙 2의 마커 검출."""
    return not text.strip() or NO_ANSWER in text.upper()


def _persist(
    *,
    worker_id: int | None,
    lang: str,
    question: str,
    answer_text: str | None,
    grounded: bool,
    sources: list[dict],
    trace: dict,
    latency_ms: int,
    enqueue_unanswered: bool,
) -> int | None:
    """questions 기록 + 무근거면 unanswered_queue 이관(M-05). 실패해도 응답은 막지 않는다.

    시스템 오류(retrieve/embed/DB)는 무근거가 아니므로 enqueue_unanswered=False 로 들어온다
    — 측정 #2(근거 인용률) 오염 방지.
    """
    try:
        with tenancy.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _INSERT_QUESTION,
                    {
                        "worker_id": worker_id,
                        "lang": lang,
                        "question": question,
                        # 측정 #2: grounded=false 인데 answer 가 남으면 안 된다 → 차단 시 NULL
                        "answer": answer_text if grounded else None,
                        "grounded": grounded,
                        "sources": json.dumps(sources, ensure_ascii=False),
                        "trace": json.dumps(trace, ensure_ascii=False),
                        "latency_ms": latency_ms,
                    },
                )
                qid = cur.fetchone()[0]
                if enqueue_unanswered:
                    cur.execute(_INSERT_UNANSWERED, {"qid": qid})
            conn.commit()
        return qid
    except Exception as exc:  # noqa: BLE001 — 기록 실패가 사용자 응답을 막지 않는다
        log.error("ask: qa_logs 기록 실패 — %s: %s", type(exc).__name__, exc)
        return None


def run_ask(question: str, lang: str, worker_id: int | None = None) -> Answer:
    """POST /ask 본문. 근거 강제 → 무근거 차단(M-05) → qa_logs 기록(M-09).

    retrieve(embed HTTP·DB) 단계 예외는 격리한다 — 500 대신 §3 스키마로 gated 응답을 내고,
    unanswered_queue 에는 넣지 않는다(시스템 오류 ≠ 무근거).
    """
    t0 = time.perf_counter()
    trace_id = uuid.uuid4().hex

    # retrieve = embed(ollama HTTP) + pgvector 조회(DB). 어느 쪽 실패든 500 을 내지 않고
    # §3 스키마로 내려보낸다. 시스템 오류는 "무근거"가 아니므로 unanswered_queue 에 넣지 않는다.
    t_ret = time.perf_counter()
    retrieve_error: str | None = None
    chunks: list[Chunk] = []
    try:
        chunks = retrieve(question, k=TOP_K)
    except Exception as exc:  # noqa: BLE001 — 검색 단계 장애 격리
        retrieve_error = f"retrieve_failed[{type(exc).__name__}]"
        log.error("ask: retrieve 실패 — %s: %s", type(exc).__name__, exc)
    retrieve_ms = int((time.perf_counter() - t_ret) * 1000)

    sources = [c.as_source() for c in chunks]
    trace: dict = {
        "trace_id": trace_id,
        "classify": {"lang": lang},
        "retrieve": {
            "k": TOP_K,
            "hits": len(chunks),
            "top_score": chunks[0].score if chunks else None,
            "chunk_ids": [c.id for c in chunks],
            "ms": retrieve_ms,
            "error": retrieve_error,
        },
    }

    answer_text = ""
    grounded = False
    if retrieve_error is not None:
        trace["route"] = {"tier": None, "model": None, "ms": 0, "error": retrieve_error}
    elif chunks:
        t_llm = time.perf_counter()
        # M-17 티어 정책: 사업장 지식 = 로컬 고정 / M-30: timeout_s=None → LLM_TIMEOUT_LOCAL_S
        result = complete(build_prompt(question, lang, chunks), "local", timeout_s=None)
        llm_ms = int((time.perf_counter() - t_llm) * 1000)
        trace["route"] = {
            "tier": result.tier_used,
            "model": result.model,
            "ms": llm_ms,
            "error": result.error,
        }
        if result.error is None and not is_no_answer(result.text):
            answer_text = result.text.strip()
            grounded = True
    else:
        trace["route"] = {"tier": None, "model": None, "ms": 0, "error": "no_chunks"}

    if not grounded:
        sources = []
        answer_text = ""

    # V4-1(M-10) 전 — 구조만 채운다. 무근거 차단은 gated 로 표면화(BLUEPRINT §4-1 응답 차단).
    verify = {"score": 0.0, "passed": grounded, "gated": not grounded}
    trace["verify"] = verify
    trace["grounded"] = grounded

    latency_ms = int((time.perf_counter() - t0) * 1000)
    trace["latency_ms"] = latency_ms

    qid = _persist(
        worker_id=worker_id,
        lang=lang,
        question=question,
        answer_text=answer_text,
        grounded=grounded,
        sources=sources,
        trace=trace,
        latency_ms=latency_ms,
        # M-05 는 "무근거 질문"의 이관 경로 — 시스템 오류는 대상이 아니다(측정 #2 오염 방지)
        enqueue_unanswered=not grounded and retrieve_error is None,
    )
    if qid is not None:
        trace["question_id"] = qid

    return Answer(answer=answer_text, sources=sources, verify=verify, trace_id=trace_id)


def answer(question: str, lang: str, worker: Worker) -> Answer:
    """skeleton-v3 §4 동결 시그니처 — 인증(V3-2) 이후 라우터가 이 경로로 들어온다."""
    return run_ask(question, lang, worker_id=worker.id)
