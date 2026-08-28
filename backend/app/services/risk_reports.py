"""위험보고 저장소 — 접수·이력(M-08·M-08a·M-08b). [새봄]

M-08b ①: 접수는 LLM 비의존 결정론 경로. 이 모듈은 llm_adapter 를 import 하지 않는다 —
로컬 LLM 이 정지해도 POST /reports 는 원문 적재 + 202 로 완결된다(신고 소실 0).
요약 생성은 workers/job_runner.py 가 별도로 담당한다.

M-08a 역할 분담:
- risk_reports 컬럼(status·acked_by/at·resolved_by/at·resolution_note) = 현재 상태 스냅숏(조회 소스)
- risk_report_events = 전이·확인·열람 전 이력(감사·lineage 정본). **append-only — INSERT 만**
- 전이 시 양쪽 기록(컬럼 갱신 + 이벤트 1행). 이력 질의는 events 만 정본

컬럼·값 집합은 db/migrations/001_tenant_template.sql 이 정본(R4).
"""

from __future__ import annotations

import json
import logging

from app.services import tenancy

log = logging.getLogger(__name__)

# 001 정본 값 집합
STATUS_SUBMITTED = "submitted"
STATE_QUEUED = "queued"
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_FAILED = "failed"          # local_failed(3회 소진)의 실패 종단값
SOURCE_TEXT = "text"
SOURCE_VOICE = "voice"

JOB_KIND_SUMMARIZE = "summarize_report"
MAX_ATTEMPTS = 3                 # WORKORDER V3-1 "3회 실패 시 보존+알림"

# 이벤트 action 어휘
EV_SUBMITTED = "report_submitted"
EV_SUMMARY_DONE = "summary_done"
EV_SUMMARY_FAILED = "summary_failed"

_INSERT_REPORT = """
INSERT INTO risk_reports (worker_id, source, original_text, lang, status, processing_state)
VALUES (%(worker_id)s, %(source)s, %(original_text)s, %(lang)s, %(status)s, %(processing_state)s)
RETURNING id
"""

# append-only — 이 모듈에 risk_report_events 대상 UPDATE/DELETE 는 존재하지 않는다 (M-08a)
_INSERT_EVENT = """
INSERT INTO risk_report_events (report_id, actor, action, from_state, to_state, detail)
VALUES (%(report_id)s, %(actor)s, %(action)s, %(from_state)s, %(to_state)s, %(detail)s)
"""

_INSERT_JOB = """
INSERT INTO jobs (kind, payload) VALUES (%(kind)s, %(payload)s::jsonb) RETURNING id
"""

_SELECT_REPORT = """
SELECT id, source, original_text, lang, ko_summary, severity, status,
       processing_state, reporter_confirmed, created_at, processed_at
FROM risk_reports WHERE id = %(id)s
"""

_UPDATE_SUMMARY_DONE = """
UPDATE risk_reports
SET ko_summary = %(ko_summary)s, severity = %(severity)s,
    processing_state = %(state)s, processed_at = now()
WHERE id = %(id)s
"""

_UPDATE_STATE = """
UPDATE risk_reports SET processing_state = %(state)s WHERE id = %(id)s
"""


def record_event(
    cur,
    report_id: int,
    action: str,
    *,
    actor: str = "system",
    from_state: str | None = None,
    to_state: str | None = None,
    detail: str | None = None,
) -> None:
    """risk_report_events 에 1행 추가. append-only — 갱신·삭제 경로는 두지 않는다."""
    cur.execute(
        _INSERT_EVENT,
        {
            "report_id": report_id,
            "actor": actor,
            "action": action,
            "from_state": from_state,
            "to_state": to_state,
            "detail": detail,
        },
    )


def submit_text_report(
    original_text: str, lang: str | None = None, worker_id: int | None = None
) -> dict:
    """텍스트 위험보고 접수 — 원문 적재 + 요약 잡 enqueue + 접수 이벤트를 한 트랜잭션으로.

    LLM 을 호출하지 않는다(M-08b ①). 반환 = {"id", "status"}.
    """
    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                _INSERT_REPORT,
                {
                    "worker_id": worker_id,
                    "source": SOURCE_TEXT,
                    "original_text": original_text,
                    "lang": lang,
                    "status": STATUS_SUBMITTED,
                    "processing_state": STATE_QUEUED,
                },
            )
            report_id = cur.fetchone()[0]

            cur.execute(
                _INSERT_JOB,
                {
                    "kind": JOB_KIND_SUMMARIZE,
                    "payload": json.dumps({"report_id": report_id}, ensure_ascii=False),
                },
            )
            job_id = cur.fetchone()[0]

            record_event(
                cur,
                report_id,
                EV_SUBMITTED,
                to_state=STATUS_SUBMITTED,
                detail=f"job={job_id} kind={JOB_KIND_SUMMARIZE}",
            )
        conn.commit()

    log.info("reports: 접수 report_id=%s job=%s lang=%s", report_id, job_id, lang)
    return {"id": report_id, "status": STATUS_SUBMITTED}


def get_report(report_id: int) -> dict | None:
    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_REPORT, {"id": report_id})
            row = cur.fetchone()
    if row is None:
        return None
    keys = (
        "id", "source", "original_text", "lang", "ko_summary", "severity",
        "status", "processing_state", "reporter_confirmed", "created_at", "processed_at",
    )
    return dict(zip(keys, row))


def mark_summary_done(cur, report_id: int, ko_summary: str, severity: str) -> None:
    """요약 성공 — 스냅숏 갱신 + 이벤트 1행 (M-08a 양쪽 기록)."""
    cur.execute(
        _UPDATE_SUMMARY_DONE,
        {"id": report_id, "ko_summary": ko_summary, "severity": severity, "state": STATE_DONE},
    )
    record_event(
        cur,
        report_id,
        EV_SUMMARY_DONE,
        from_state=STATE_RUNNING,
        to_state=STATE_DONE,
        detail=f"severity={severity}",
    )


def mark_summary_failed(cur, report_id: int, reason: str) -> None:
    """local_failed(3회 소진) — 원문은 그대로 두고 처리상태만 실패 종단값으로 (M-08b ②).

    원문 삭제·변형 경로는 두지 않는다. 관리자 알림은 호출부가 ERROR 로 남긴다.
    """
    cur.execute(_UPDATE_STATE, {"id": report_id, "state": STATE_FAILED})
    record_event(
        cur,
        report_id,
        EV_SUMMARY_FAILED,
        from_state=STATE_RUNNING,
        to_state=STATE_FAILED,
        detail=reason,
    )


def mark_running(cur, report_id: int) -> None:
    cur.execute(_UPDATE_STATE, {"id": report_id, "state": STATE_RUNNING})
