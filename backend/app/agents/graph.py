"""그래프 엔트리 — classify → retrieve → translate → verify (≤3홉). [새봄]

V2-2 범위: retrieve(top-k=4) → 근거 강제 프롬프트 → complete(tier="local") → 응답 조립.
- 응답 언어 = 질의 lang (총괄 재판정 0830) — 프롬프트 상단 [출력 언어] 블록 + [답변] 헤더에 중복 지시.
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
from datetime import datetime, timezone

from app.agents.neg_lexicon import ko_neg
from app.agents.num_compare import num_compare
from app.agents.retrieve import Chunk, retrieve
from app.agents.verify import Verify, is_high_risk, verify_backtranslation
from app.models import Worker
from app.services import tenancy
from app.services.llm_adapter import _env, _env_float, complete, deadline_s

log = logging.getLogger(__name__)

TOP_K = 4

# M-34 c: 되번역 예산 — 시도별 상한(env)과 M-30 요청 예산 잔여 중 작은 값.
DEFAULT_BACKTRANS_TIMEOUT_S = 10.0
DEFAULT_GATE_SRC = "question"      # M-34 c Q6: 게이트 축 = 원질문(질의 lang 그대로, ko 변환 금지)
GATE_SRC_VALUES = ("question", "chunks")

# 근거가 없을 때 모델이 내야 하는 정확한 토큰. 이 값이 응답에 있으면 grounded=false 로 판정한다.
NO_ANSWER = "NO_ANSWER"

_LANG_NAME = {"vi": "베트남어", "in": "인도네시아어", "ko": "한국어"}
# 원어 표기 병기 — 언어명만으로는 모델이 근거 자료 언어(한국어)로 이어쓰는 경향이 있다.
_LANG_NATIVE = {"vi": "Tiếng Việt", "in": "Bahasa Indonesia", "ko": "한국어"}

# 근거 강제 프롬프트 (BLUEPRINT §4-1) — 청크 밖 지식 사용 금지.
# 출력 언어 지시는 규칙 목록 안이 아니라 상단 독립 블록 + [답변] 헤더에 중복 배치한다 —
# 규칙 3 말미에 길이 규약과 섞여 있을 때 vi 질의에 한국어로 답하는 사례가 실측됐다(EC2 0830).
PROMPT_TEMPLATE = """당신은 제조 사업장의 안전·작업 안내 도우미입니다.

[출력 언어] {lang_label}
- 답변 전체를 {lang_name}로 작성하십시오. 근거 자료의 언어와 무관합니다.
- 근거 자료가 다른 언어면 내용을 {lang_name}로 옮겨 답하십시오. 다른 언어를 섞지 마십시오.
- 이 지시는 아래 규칙보다 우선합니다. 단 {no_answer} 는 번역하지 말고 그대로 출력하십시오.

규칙(반드시 지킬 것):
1. 아래 [근거 자료]에 있는 내용만으로 답하십시오. 자료 밖의 일반 지식·추측을 절대 쓰지 마십시오.
2. 자료로 질문에 답할 수 없으면 다른 말을 덧붙이지 말고 정확히 {no_answer} 한 단어만 출력하십시오.
3. 답할 수 있으면 {lang_name}로만, 3문장 이내로 간결하게 답하십시오.

[근거 자료]
{context}

[질문]
{question}

[답변 — {lang_label}로 작성]"""


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


def _iso(ts: float | None) -> str | None:
    """epoch 초 → ISO8601(UTC). None 은 그대로 둔다."""
    if ts is None:
        return None
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()


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
    name = _LANG_NAME.get(lang, _LANG_NAME["vi"])
    native = _LANG_NATIVE.get(lang, _LANG_NATIVE["vi"])
    return PROMPT_TEMPLATE.format(
        no_answer=NO_ANSWER,
        lang_name=name,
        # 원어 표기가 언어명과 같으면(ko) 괄호를 붙이지 않는다 — "한국어(한국어)" 방지
        lang_label=f"{name}({native})" if native != name else name,
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

    시스템 오류(retrieve/embed/DB 예외·LLM 생성 실패 local_failed)는 무근거가 아니므로
    enqueue_unanswered=False 로 들어온다 (M-05a — 측정 #2 근거 인용률 오염 방지).
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


def _gate_src() -> str:
    """GATE_SRC — question|chunks 외 값은 경고 후 기본축(question)으로 폴백한다."""
    raw = _env("GATE_SRC", DEFAULT_GATE_SRC)
    if raw in GATE_SRC_VALUES:
        return raw
    log.warning(
        "graph: env GATE_SRC=%r 가 %s 밖 — 기본값 %s 사용",
        raw, list(GATE_SRC_VALUES), DEFAULT_GATE_SRC,
    )
    return DEFAULT_GATE_SRC


def _backtrans_budget_s(t0: float) -> float:
    """되번역에 줄 시도별 timeout — env 상한과 M-30 요청 예산 잔여 중 작은 값.

    잔여는 run_ask 진입(t0) 기준으로 센다. complete() 는 호출마다 자기 예산을 새로 잡으므로
    (llm_adapter:15) 여기서 잔여를 깎아 넘겨야 요청당 총량이 LLM_DEADLINE_S 를 넘지 않는다.
    """
    cap = _env_float("BACKTRANS_TIMEOUT_S", DEFAULT_BACKTRANS_TIMEOUT_S)
    left = deadline_s() - (time.perf_counter() - t0)
    return min(cap, left)


def _rule_trace(src_text: str, back_text: str) -> dict:
    """C-lite (a): 규칙 축 실측(숫자 대조·부정어 극성). 게이트 판정에는 관여하지 않는다.

    비교축은 게이트 src(src_kind 가 고른 쪽)와 되번역문이다.
    주의: src_kind='question' 이면 src 가 질의 lang(vi/in)일 수 있다 — ko 사전인
    neg 축은 그때 src 히트가 0으로 잡히므로 delta 를 언어와 함께 읽어야 한다.
    """
    ns, nb = ko_neg(src_text or ""), ko_neg(back_text or "")
    return {
        "num": num_compare(src_text or "", back_text or ""),
        "neg": {"src": ns, "back": nb, "delta": nb - ns, "hit": abs(nb - ns) >= 1},
    }


def _backtrans_trace(
    bt: Verify | None,
    *,
    high_risk: bool,
    src_kind: str,
    chunks_joined: str = "",
    src_text: str = "",
) -> dict:
    """trace.verify 실측 — §3 응답(4키) 밖으로는 나가지 않는다."""
    base = {
        "high_risk": high_risk,
        "src_kind": src_kind,
        "chunks_joined_len": len(chunks_joined),
    }
    if bt is None:
        return dict(
            base, back_text=None, back_ms=None, timed_out=None, error=None,
            score_question=None, score_chunks=None, num=None, neg=None,
        )
    return dict(
        base,
        back_text=bt.back_text or None,
        back_ms=bt.back_ms,
        timed_out=bt.timed_out,
        error=bt.error,
        score_question=bt.score_src,
        score_chunks=bt.score_aux,
        **_rule_trace(src_text, bt.back_text or ""),
    )


def run_ask(
    question: str,
    lang: str,
    worker_id: int | None = None,
    relay_meta: dict | None = None,
) -> Answer:
    """POST /ask 본문. 근거 강제 → 무근거 차단(M-05) → qa_logs 기록(M-09).

    retrieve(embed HTTP·DB) 단계 예외는 격리한다 — 500 대신 §3 스키마로 gated 응답을 낸다.
    unanswered_queue 적재는 검색 0건·NO_ANSWER 2종만(M-05a) — retrieve 예외·local_failed 는 제외.

    relay_meta(M-28a 릴레이 경유 시에만 전달) = {"enqueued_at", "leased_at"} epoch 초.
    trace.relay 로만 남기고 API 응답(§3 4필드)에는 노출하지 않는다 — 측정 #4 재료.
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
    bt: Verify | None = None                  # M-34 c 되번역 결과(미수행이면 None)
    gate_src = _gate_src()                    # 요청당 1회 판정 — 오값이면 경고 후 question
    chunks_joined = ""                        # 게이트 aux 축(근거 결합문) — trace 길이 기록용
    gate_reason: str | None = None            # M-10b: 'grounding' | 'threshold' | None
    # M-05a: unanswered_queue 적재 대상은 "관리자 답변이 필요한 무근거" 2종뿐 —
    # 검색 0건(no_chunks)·NO_ANSWER. 시스템 오류(retrieve 예외·local_failed)는 미적재.
    unanswered_reason: str | None = None
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
        if result.error is not None:
            pass  # local_failed — 생성 실패는 시스템 오류, 미적재 (M-05a)
        elif is_no_answer(result.text):
            unanswered_reason = "no_answer"
        else:
            answer_text = result.text.strip()
            grounded = True
            # M-34 c: 되번역 게이트. src=원질문(질의 lang 그대로), aux=근거 청크 결합문(ko).
            chunks_joined = build_context(chunks)
            bt = verify_backtranslation(
                question,
                answer_text,
                aux_src=chunks_joined,
                gate_on="aux" if gate_src == "chunks" else "src",
                timeout_s=_backtrans_budget_s(t0),
            )
    else:
        trace["route"] = {"tier": None, "model": None, "ms": 0, "error": "no_chunks"}
        unanswered_reason = "no_chunks"

    # Q5: gated = (not grounded) OR (고위험 AND τ 미달). 비안전 τ 미달은 배지만(차단 없음).
    high_risk = is_high_risk(None, chunks)    # classify OR 항 유보 — cls 는 넘기지 않는다
    threshold_blocked = bool(grounded and high_risk and bt is not None and not bt.passed)
    if not grounded:
        gate_reason = "grounding"             # grounded=False 인 전 경로 공통(경로별 분기 없음)
    elif threshold_blocked:
        gate_reason = "threshold"             # 안전 질의 τ 미달 — WORKORDER V4-1 "안전만 차단"
    gated = (not grounded) or threshold_blocked
    if gated:
        sources = []
        answer_text = ""

    # M-34 c: 무근거 차단(gated)은 M-10b gate_reason='grounding' 으로 사유를 구분한다.
    # τ 게이트(threshold) 분기는 되번역 배선과 함께 이 위에서 grounded 를 내린다.
    verify = {
        "score": bt.score if bt is not None else None,
        "passed": bt.passed if bt is not None else grounded,
        "gated": gated,
        "gate_reason": gate_reason,
    }
    trace["verify"] = dict(
        verify,
        **_backtrans_trace(
            bt,
            high_risk=high_risk,
            src_kind=gate_src,
            chunks_joined=chunks_joined,
            src_text=chunks_joined if gate_src == "chunks" else question,
        ),
    )
    trace["grounded"] = grounded

    latency_ms = int((time.perf_counter() - t0) * 1000)
    trace["latency_ms"] = latency_ms
    if relay_meta:
        # 측정 #4: 릴레이 왕복(적재→배포→회신)을 core 처리시간과 분리 계측
        trace["relay"] = {
            "enqueued_at": _iso(relay_meta.get("enqueued_at")),
            "leased_at": _iso(relay_meta.get("leased_at")),
            "responded_at": _iso(time.time()),
        }

    qid = _persist(
        worker_id=worker_id,
        lang=lang,
        question=question,
        answer_text=answer_text,
        grounded=grounded,
        sources=sources,
        trace=trace,
        latency_ms=latency_ms,
        # M-05a: 적재 = 검색 0건·NO_ANSWER 2종만. retrieve 예외·local_failed 는 제외
        enqueue_unanswered=unanswered_reason is not None,
    )
    if qid is not None:
        trace["question_id"] = qid

    return Answer(answer=answer_text, sources=sources, verify=verify, trace_id=trace_id)


def answer(question: str, lang: str, worker: Worker) -> Answer:
    """skeleton-v3 §4 동결 시그니처 — 인증(V3-2) 이후 라우터가 이 경로로 들어온다."""
    return run_ask(question, lang, worker_id=worker.id)
