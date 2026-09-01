"""jobs 폴러 — FOR UPDATE SKIP LOCKED, attempts<3 백오프. 3회 실패 시 failed + 관리자 알림 (M-08·M-08b). [새봄]

M-08b ②: 요약·severity 생성 실패(재시도 3회 소진 = local_failed)는
- 원문 보존(삭제·변형 없음) + processing_state='failed'(001 정본 실패 종단값)
- 관리자 알림(admin_alert ERROR 로그) + summary_failed 이벤트(M-08a)
- **외부 LLM 폴백 금지** — 원문 민감성. 이 모듈은 tier="local" 만 호출하며
  tier="external" 문자열이 코드 경로에 존재하지 않는다.

요약 재생성은 V5(M-08b ③). STT 경로는 V5 — 아래 스텁 분기는 호출되지 않는다.

M-05a: kind='ingest_answer' 는 관리자 답변을 documents(origin='admin_answer')+chunks 로
적재하고 unanswered_queue.ingested_doc_id 를 채운다. 실패는 위 요약과 같은
attempts 백오프·3회 failed 경로를 그대로 탄다.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time

from app.agents.retrieve import to_vector_literal
from app.services import approval, risk_reports, tenancy
from app.services.crypto import open_text
from app.services.llm_adapter import complete, embed

log = logging.getLogger(__name__)

BACKOFF_S = 5.0  # attempts 재시도 간격 (run_after 로 지연)
DEFAULT_POLL_S = 2.0             # 큐가 비었을 때 쉬는 간격 (기존 run_jobs 기본값과 동일)


def poll_s() -> float:
    """JOBS_POLL_S — 기본값은 run_jobs 의 기존 기본값 그대로. relay.py env 헬퍼 패턴(R4)."""
    raw = os.getenv("JOBS_POLL_S")
    if not raw:
        return DEFAULT_POLL_S
    try:
        value = float(raw)
    except ValueError:
        log.warning("job_runner: env JOBS_POLL_S=%r 가 숫자가 아님 — 기본값 %s 사용", raw, DEFAULT_POLL_S)
        return DEFAULT_POLL_S
    if value <= 0:
        log.warning("job_runner: env JOBS_POLL_S=%r 가 0 이하 — 기본값 %s 사용", raw, DEFAULT_POLL_S)
        return DEFAULT_POLL_S
    return value

SEVERITY_VALUES = ("high", "medium", "low")

# 로컬 티어 전용 요약 프롬프트. 근거는 신고 원문 하나뿐이므로 검색 없음.
SUMMARY_PROMPT = """다음은 제조 사업장 근로자가 올린 위험 신고 원문입니다.

규칙:
1. 아래 JSON 한 줄만 출력하십시오. 다른 말은 절대 덧붙이지 마십시오.
   {{"ko_summary": "<한국어 2문장 이내 요약>", "severity": "high"|"medium"|"low"}}
2. 원문에 없는 사실을 추측해 넣지 마십시오.
3. severity 기준 — high: 즉시 인명 위험 / medium: 부상 가능 / low: 경미·정비 요청

[신고 원문]
{text}

[JSON]"""

_CLAIM_JOB = """
SELECT id, kind, payload, attempts
FROM jobs
WHERE status = 'queued' AND run_after <= now()
ORDER BY id
FOR UPDATE SKIP LOCKED
LIMIT 1
"""

_JOB_RUNNING = "UPDATE jobs SET status='running', updated_at=now() WHERE id = %(id)s"
_JOB_DONE = "UPDATE jobs SET status='done', updated_at=now() WHERE id = %(id)s"
_JOB_RETRY = """
UPDATE jobs
SET status='queued', attempts=%(attempts)s, run_after = now() + (%(backoff)s || ' seconds')::interval,
    updated_at=now()
WHERE id = %(id)s
"""
_JOB_FAILED = """
UPDATE jobs SET status='failed', attempts=%(attempts)s, updated_at=now() WHERE id = %(id)s
"""

_SELECT_ORIGINAL = "SELECT original_text FROM risk_reports WHERE id = %(id)s"


class LocalSummaryError(RuntimeError):
    """로컬 티어 요약 실패 — 외부 폴백 없이 재시도 대상으로만 쓴다."""


def _parse_summary(text: str) -> tuple[str, str]:
    raw = text.strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise LocalSummaryError(f"JSON 형태 아님: {raw[:80]!r}")
    try:
        data = json.loads(raw[start : end + 1])
    except ValueError as exc:
        raise LocalSummaryError(f"JSON 파싱 실패: {exc}") from exc
    ko_summary = str(data.get("ko_summary") or "").strip()
    severity = str(data.get("severity") or "").strip().lower()
    if not ko_summary:
        raise LocalSummaryError("ko_summary 비어 있음")
    if severity not in SEVERITY_VALUES:
        raise LocalSummaryError(f"severity 값 위반: {severity!r}")
    return ko_summary, severity


def summarize_report(text: str) -> tuple[str, str]:
    """→ (ko_summary, severity). 로컬 티어 고정. severity ∈ {high, medium, low}.

    M-17 티어 정책·M-08b ②: 외부 폴백 없음. M-30: timeout_s=None → LLM_TIMEOUT_LOCAL_S.
    """
    result = complete(SUMMARY_PROMPT.format(text=text), "local", timeout_s=None)
    if result.error is not None:
        raise LocalSummaryError(result.error)
    return _parse_summary(result.text)


def _transcribe_pending(payload: dict) -> str:
    """STT 스텁 자리 (M-18, V5). V4 범위는 텍스트 한정 — 이 분기는 호출되지 않는다."""
    raise NotImplementedError("[새봄] jobs kind='stt_summarize' — STT 연동은 V5")


def _handle_summarize(cur, job: dict) -> None:
    report_id = int(job["payload"]["report_id"])
    cur.execute(_SELECT_ORIGINAL, {"id": report_id})
    row = cur.fetchone()
    if row is None:
        raise LocalSummaryError(f"report_id={report_id} 없음")
    original_text = open_text(row[0])          # M-19 이중 읽기 — 복호 후 요약 LLM 에 넘긴다
    if not original_text:
        raise LocalSummaryError(f"report_id={report_id} 원문 비어 있음")

    risk_reports.mark_running(cur, report_id)
    # 이월: 요약 LLM(2~3s) 이 process_once 의 단일 트랜잭션을 점유한다 — 구조 변경은 별건.
    ko_summary, severity = summarize_report(original_text)
    risk_reports.mark_summary_done(cur, report_id, ko_summary, severity)


class IngestAnswerError(RuntimeError):
    """관리자 답변 적재 실패 — 요약과 같은 재시도 경로를 탄다."""


# 001:28-33 정본 컬럼. category 는 CHECK('process','instruction','safety','equipment') 라
# 'general' 을 넣을 수 없다 — NULL 로 두고 검색용 분류는 chunks.meta.category 가 갖는다.
_INSERT_DOCUMENT = """
INSERT INTO documents (title, category, origin, source, version, masked)
VALUES (%(title)s, NULL, 'admin_answer', %(source)s, 1, false)
RETURNING id
"""

_INSERT_CHUNK = """
INSERT INTO chunks (document_id, chunk_idx, content, embedding, meta)
VALUES (%(document_id)s, 0, %(content)s, %(embedding)s::vector, %(meta)s::jsonb)
"""

_SELECT_QUESTION = "SELECT question FROM questions WHERE id = %(id)s"
_SET_INGESTED_DOC = """
UPDATE unanswered_queue SET ingested_doc_id = %(doc_id)s WHERE id = %(id)s
"""

# 검색 노출용 meta. retrieve 는 meta->>'category' 를 sources.category 로 쓰고
# meta->>'role' <> 'case' 만 배제하므로 이 형태는 즉시 검색 후보가 된다(M-29a 무관).
CHUNK_META_CATEGORY = "general"
TITLE_MAX = 80


def _answer_title(cur, question_id: int) -> str:
    """documents.title 은 NOT NULL — 원 질문을 잘라 쓰고, 없으면 식별자로 대체한다."""
    cur.execute(_SELECT_QUESTION, {"id": question_id})
    row = cur.fetchone()
    question = (row[0] if row else None) or ""
    question = question.strip()
    if not question:
        return f"관리자 답변 (question_id={question_id})"
    return f"관리자 답변: {question[:TITLE_MAX]}"


def _handle_ingest_answer(cur, job: dict) -> None:
    """M-05a — 관리자 답변을 검색 코퍼스에 편입한다.

    documents(origin='admin_answer') 1건 + chunks 1건(임베딩 1024 고정, M-02) +
    unanswered_queue.ingested_doc_id 갱신을 잡 트랜잭션 안에서 끝낸다.
    """
    payload = job["payload"]
    text = (payload.get("text") or "").strip()
    if not text:
        raise IngestAnswerError(f"job={job['id']} payload.text 비어 있음")
    try:
        question_id = int(payload["question_id"])
        unanswered_id = int(payload["unanswered_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise IngestAnswerError(f"job={job['id']} payload 필드 위반: {exc}") from exc

    title = _answer_title(cur, question_id)
    cur.execute(_INSERT_DOCUMENT, {"title": title, "source": f"unanswered:{unanswered_id}"})
    doc_id = cur.fetchone()[0]

    vectors = embed([text])            # M-02a 단일 런타임 — 차원 위반은 embed 가 예외로 막는다
    cur.execute(
        _INSERT_CHUNK,
        {
            "document_id": doc_id,
            "content": text,
            "embedding": to_vector_literal(vectors[0]),
            "meta": json.dumps(
                {
                    "category": CHUNK_META_CATEGORY,
                    "draft": False,
                    "origin": "admin_answer",
                    "question_id": question_id,
                },
                ensure_ascii=False,
            ),
        },
    )
    cur.execute(_SET_INGESTED_DOC, {"doc_id": doc_id, "id": unanswered_id})
    log.info(
        "jobs: 관리자 답변 적재 job=%s question_id=%s document_id=%s",
        job["id"], question_id, doc_id,
    )


def _fail_job(cur, job: dict, exc: Exception) -> None:
    """attempts 증가 → 3회 소진 시 local_failed 처리. 원문은 건드리지 않는다."""
    attempts = int(job["attempts"]) + 1
    reason = f"{type(exc).__name__}: {exc}"
    if attempts < risk_reports.MAX_ATTEMPTS:
        cur.execute(_JOB_RETRY, {"id": job["id"], "attempts": attempts, "backoff": BACKOFF_S})
        log.warning(
            "jobs: 요약 실패 재시도 job=%s attempts=%s/%s · %s",
            job["id"], attempts, risk_reports.MAX_ATTEMPTS, reason,
        )
        return

    cur.execute(_JOB_FAILED, {"id": job["id"], "attempts": attempts})
    report_id = job["payload"].get("report_id")
    if report_id is not None:
        risk_reports.mark_summary_failed(
            cur, int(report_id), f"local_failed[{reason}] attempts={attempts}"
        )
    # 관리자 알림 (M-08b ② — WORKORDER "3회 실패 시 보존+알림")
    log.error(
        "admin_alert: 위험보고 요약 3회 실패 — 원문 보존됨, 직접 확인 필요 "
        "report_id=%s job=%s attempts=%s reason=%s",
        report_id, job["id"], attempts, reason,
    )


def process_once() -> bool:
    """잡 1건 처리. 처리했으면 True, 큐가 비었으면 False."""
    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_CLAIM_JOB)
            row = cur.fetchone()
            if row is None:
                return False
            job = {"id": row[0], "kind": row[1], "payload": row[2] or {}, "attempts": row[3]}
            cur.execute(_JOB_RUNNING, {"id": job["id"]})

            try:
                if job["kind"] == risk_reports.JOB_KIND_SUMMARIZE:
                    _handle_summarize(cur, job)
                elif job["kind"] == approval.JOB_KIND_INGEST_ANSWER:
                    _handle_ingest_answer(cur, job)
                elif job["kind"] == "stt_summarize":
                    _transcribe_pending(job["payload"])  # V5 — 현재 미사용 경로
                else:
                    raise LocalSummaryError(f"미지원 kind={job['kind']!r}")
            except Exception as exc:  # noqa: BLE001 — 개별 잡 실패가 폴러를 끊지 않는다
                _fail_job(cur, job, exc)
            else:
                cur.execute(_JOB_DONE, {"id": job["id"]})
        conn.commit()
    return True


def _idle(stop: threading.Event | None, seconds: float) -> None:
    """큐가 비었을 때의 대기. stop 이 있으면 신호 즉시 깨어난다(종료 지연 제거)."""
    if stop is None:
        time.sleep(seconds)
    else:
        stop.wait(seconds)


def run_jobs(poll_s: float = 2.0, stop: threading.Event | None = None) -> None:
    """기동~정지까지 반복. 큐가 비면 poll_s 만큼 쉰다.

    M-33: core-api lifespan 이 asyncio.to_thread 로 이 함수를 띄운다. 동기 루프라
    종료 신호는 스레드 안전한 threading.Event 를 쓴다(릴레이 폴러의 asyncio.Event 는
    코루틴 전용). stop=None 이면 기존 동작 그대로 무한 루프 — 기존 호출부 호환.
    """
    log.info("job_runner: 시작 (poll_s=%s)", poll_s)
    while stop is None or not stop.is_set():
        try:
            if not process_once():
                _idle(stop, poll_s)
        except Exception as exc:  # noqa: BLE001 — DB 단절 등도 루프를 끊지 않는다
            log.error("job_runner: 폴링 오류 %s: %s", type(exc).__name__, exc)
            _idle(stop, poll_s)
    log.info("job_runner: 정상 종료")
