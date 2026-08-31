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
STATUS_ACKNOWLEDGED = "acknowledged"
STATUS_RESOLVED = "resolved"
# M-08 단방향 상태머신 — 스킵·역행 없음
NEXT_STATUS = {STATUS_SUBMITTED: STATUS_ACKNOWLEDGED, STATUS_ACKNOWLEDGED: STATUS_RESOLVED}
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
EV_ACKNOWLEDGED = "report_acknowledged"
EV_RESOLVED = "report_resolved"
EV_ORIGINAL_VIEWED = "original_viewed"
EV_REPORTER_CONFIRMED = "reporter_confirmed"
EV_REPORTER_CORRECTED = "reporter_corrected"

# M-15b(미결): 관리자 인증 부재 — 전이·원문 열람 행위자 임시값.
# **주입 지점은 이 상수 1곳뿐이다.** 관리자 인증 도입 시 여기만 교체한다.
# 'system' 은 워커·자동 처리 규약이라 사용하지 않는다.
ADMIN_ACTOR_UNAUTHENTICATED = "admin:unauthenticated"


def worker_actor(worker_id: int | None) -> str:
    """M-28b identity 소비 — 근로자 행위자 표기(001 actor 주석 규약)."""
    return f"worker:{worker_id}" if worker_id is not None else "worker:unauthenticated"


# M-08b ④: 서버가 도출하는 신원·상태 필드는 요청 본문으로 받지 않는다(무시 아님 — 400).
IDENTITY_FIELDS = frozenset(
    {"worker_id", "admin_id", "reporter", "reporter_id", "actor",
     "tenant", "tenant_slug", "acked_by", "resolved_by", "status", "id"}
)


def identity_fields_in(body: object) -> list[str]:
    """본문에 섞인 금지 필드 목록(정렬). 없으면 빈 리스트."""
    if not isinstance(body, dict):
        return []
    return sorted(set(body) & IDENTITY_FIELDS)


class TransitionError(Exception):
    """M-08 단방향 위반(스킵·역행) 또는 대상 없음 — 라우터가 422/404 로 변환."""


class ReportNotFound(Exception):
    """대상 보고 없음 — 404."""

_INSERT_REPORT = """
INSERT INTO risk_reports (worker_id, source, original_text, lang, status, processing_state)
VALUES (%(worker_id)s, %(source)s, %(original_text)s, %(lang)s, %(status)s, %(processing_state)s)
RETURNING id, created_at
"""

# append-only — 이 모듈에 risk_report_events 대상 UPDATE/DELETE 는 존재하지 않는다 (M-08a)
_INSERT_EVENT = """
INSERT INTO risk_report_events (report_id, actor, action, from_state, to_state, detail)
VALUES (%(report_id)s, %(actor)s, %(action)s, %(from_state)s, %(to_state)s, %(detail)s)
"""

# D-8: created_at 을 명시 기록하는 변형. 001 의 열 DEFAULT now() 는 트랜잭션 시작 시각이라
# 요약 완료처럼 긴 트랜잭션 끝에 남는 이벤트에서는 실제 기록 시점과 어긋난다.
# summary_done 전용 — 접수·전이·확인 경로는 위 _INSERT_EVENT(열 DEFAULT) 그대로다.
_INSERT_EVENT_CLOCK = """
INSERT INTO risk_report_events (report_id, actor, action, from_state, to_state, detail, created_at)
VALUES (%(report_id)s, %(actor)s, %(action)s, %(from_state)s, %(to_state)s, %(detail)s, clock_timestamp())
"""

_INSERT_JOB = """
INSERT INTO jobs (kind, payload) VALUES (%(kind)s, %(payload)s::jsonb) RETURNING id
"""

_SELECT_REPORT = """
SELECT id, source, original_text, lang, ko_summary, severity, status,
       processing_state, reporter_confirmed, created_at, processed_at
FROM risk_reports WHERE id = %(id)s
"""

# D-8: processed_at 은 clock_timestamp()(문장 시각). now() 는 **트랜잭션 시작 시각**이라
# job_runner.process_once 의 단일 트랜잭션 안에서 도는 요약 LLM 소요가 통째로 빠져
# processed_at - created_at 이 0 에 수렴한다(총괄 확정 산출식 = 픽업 대기 + 요약).
_UPDATE_SUMMARY_DONE = """
UPDATE risk_reports
SET ko_summary = %(ko_summary)s, severity = %(severity)s,
    processing_state = %(state)s, processed_at = clock_timestamp()
WHERE id = %(id)s
"""

_UPDATE_STATE = """
UPDATE risk_reports SET processing_state = %(state)s WHERE id = %(id)s
"""

# M-15b 판정 1: 스냅숏은 시각·비고만 갱신. acked_by·resolved_by(integer)는 NULL 유지 —
# 행위자는 risk_report_events.actor 단독 기록.
_SELECT_STATUS_FOR_UPDATE = "SELECT status FROM risk_reports WHERE id = %(id)s FOR UPDATE"

_ACK = """
UPDATE risk_reports SET status = %(to_state)s, acked_at = now() WHERE id = %(id)s
"""

_RESOLVE = """
UPDATE risk_reports
SET status = %(to_state)s, resolved_at = now(), resolution_note = %(note)s
WHERE id = %(id)s
"""

_LIST_REPORTS = """
SELECT id, ko_summary, severity, status, processing_state, reporter_confirmed, created_at
FROM risk_reports
WHERE (%(status)s::text IS NULL OR status = %(status)s)
ORDER BY id DESC
"""

_SELECT_DETAIL = """
SELECT id, source, original_text, lang, ko_summary, severity, status, processing_state,
       reporter_confirmed, acked_by, acked_at, resolved_by, resolved_at, resolution_note,
       created_at, processed_at
FROM risk_reports WHERE id = %(id)s
"""

_SELECT_PUBLIC = """
SELECT id, status, processing_state, reporter_confirmed, created_at
FROM risk_reports WHERE id = %(id)s
"""

_SELECT_EVENTS = """
SELECT id, actor, action, from_state, to_state, detail, created_at
FROM risk_report_events WHERE report_id = %(id)s ORDER BY id
"""

_SELECT_CONFIRM_TARGET = """
SELECT processing_state, original_text FROM risk_reports WHERE id = %(id)s FOR UPDATE
"""

_SET_REPORTER_CONFIRMED = """
UPDATE risk_reports SET reporter_confirmed = true WHERE id = %(id)s
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
    at_clock: bool = False,
) -> None:
    """risk_report_events 에 1행 추가. append-only — 갱신·삭제 경로는 두지 않는다.

    at_clock=True 면 created_at 을 clock_timestamp() 로 명시한다(D-8). 기본값은 001 의
    열 DEFAULT now() 를 그대로 쓴다 — 짧은 트랜잭션에서는 둘이 같고, 기존 경로를 건드리지 않는다.
    """
    cur.execute(
        _INSERT_EVENT_CLOCK if at_clock else _INSERT_EVENT,
        {
            "report_id": report_id,
            "actor": actor,
            "action": action,
            "from_state": from_state,
            "to_state": to_state,
            "detail": detail,
        },
    )


def _iso(value) -> str | None:
    """DB timestamptz → ISO8601 문자열."""
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def submit_text_report(
    original_text: str,
    lang: str | None = None,
    source: str = SOURCE_TEXT,
    worker_id: int | None = None,
) -> dict:
    """텍스트 위험보고 접수 — 원문 적재 + 요약 잡 enqueue + 접수 이벤트를 한 트랜잭션으로.

    LLM 을 호출하지 않는다(M-08b ①). 반환 = {"id", "status", "created_at"} (M-08b ④).
    worker_id 는 인증 컨텍스트에서 서버가 도출한다 — 요청 본문으로 받지 않는다.
    """
    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                _INSERT_REPORT,
                {
                    "worker_id": worker_id,
                    "source": source,
                    "original_text": original_text,
                    "lang": lang,
                    "status": STATUS_SUBMITTED,
                    "processing_state": STATE_QUEUED,
                },
            )
            report_id, created_at = cur.fetchone()

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

    log.info("reports: 접수 report_id=%s job=%s lang=%s source=%s", report_id, job_id, lang, source)
    return {"id": report_id, "status": STATUS_SUBMITTED, "created_at": _iso(created_at)}


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
        at_clock=True,                      # D-8 — 요약 완료 시각은 문장 시각으로
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


# ── M-08 전이 (관리자) ────────────────────────────────────

_DETAIL_KEYS = (
    "id", "source", "original_text", "lang", "ko_summary", "severity", "status",
    "processing_state", "reporter_confirmed", "acked_by", "acked_at", "resolved_by",
    "resolved_at", "resolution_note", "created_at", "processed_at",
)
_EVENT_KEYS = ("id", "actor", "action", "from_state", "to_state", "detail", "created_at")
_LIST_KEYS = (
    "id", "ko_summary", "severity", "status", "processing_state", "reporter_confirmed",
    "created_at",
)
_PUBLIC_KEYS = ("id", "status", "processing_state", "reporter_confirmed", "created_at")


def _row(keys, row) -> dict:
    out = dict(zip(keys, row))
    for k in ("created_at", "acked_at", "resolved_at", "processed_at"):
        if k in out:
            out[k] = _iso(out[k])
    return out


def _transition(report_id: int, expected_from: str, sql: str, action: str, params: dict) -> dict:
    """단방향 전이 1회. 스냅숏(시각·비고) 갱신 + events 1행 (M-08a 양쪽 기록).

    acked_by·resolved_by 는 건드리지 않는다 — 001 정본 integer, 행위자는 events.actor 단독(M-15b).
    """
    to_state = NEXT_STATUS[expected_from]
    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_STATUS_FOR_UPDATE, {"id": report_id})
            row = cur.fetchone()
            if row is None:
                raise ReportNotFound(f"report_id={report_id}")
            current = row[0]
            if current != expected_from:
                raise TransitionError(f"{current} → {to_state} 불가 (단방향: {expected_from} 에서만)")

            cur.execute(sql, {"id": report_id, "to_state": to_state, **params})
            record_event(
                cur,
                report_id,
                action,
                actor=ADMIN_ACTOR_UNAUTHENTICATED,
                from_state=current,
                to_state=to_state,
                detail=params.get("note"),
            )
        conn.commit()
    log.info("reports: 전이 report_id=%s %s → %s", report_id, expected_from, to_state)
    return {"id": report_id, "status": to_state}


def acknowledge(report_id: int) -> dict:
    """submitted → acknowledged."""
    return _transition(report_id, STATUS_SUBMITTED, _ACK, EV_ACKNOWLEDGED, {})


def resolve(report_id: int, note: str | None = None) -> dict:
    """acknowledged → resolved. 정정은 새 보고 + 원 보고 참조 — 역행 경로는 두지 않는다."""
    return _transition(report_id, STATUS_ACKNOWLEDGED, _RESOLVE, EV_RESOLVED, {"note": note})


# ── 조회 ──────────────────────────────────────────────────

def list_reports(status: str | None = None) -> list[dict]:
    """관리자 목록 — original_text 미포함(M-08b 기재 필드)."""
    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_LIST_REPORTS, {"status": status})
            rows = cur.fetchall()
    return [_row(_LIST_KEYS, r) for r in rows]


def get_report_detail(report_id: int) -> dict:
    """관리자 상세 + events[]. original_text 를 실어 보내므로 original_viewed 이벤트를 남긴다.

    acked_by·resolved_by 는 인증 도입 전까지 null 로 나간다(additive — 판정 3).
    """
    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_DETAIL, {"id": report_id})
            row = cur.fetchone()
            if row is None:
                raise ReportNotFound(f"report_id={report_id}")
            detail = _row(_DETAIL_KEYS, row)

            # 원문 열람 감사 (M-08a) — events append 만, 컬럼 무변경
            record_event(
                cur,
                report_id,
                EV_ORIGINAL_VIEWED,
                actor=ADMIN_ACTOR_UNAUTHENTICATED,
                detail="admin detail view",
            )
            cur.execute(_SELECT_EVENTS, {"id": report_id})
            detail["events"] = [_row(_EVENT_KEYS, r) for r in cur.fetchall()]
        conn.commit()
    return detail


def get_report_public(report_id: int) -> dict:
    """근로자 상태 조회 — 5필드 한정. events[]·original_text 미포함, 감사 비대상(총괄 확정)."""
    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_PUBLIC, {"id": report_id})
            row = cur.fetchone()
    if row is None:
        raise ReportNotFound(f"report_id={report_id}")
    return _row(_PUBLIC_KEYS, row)


# ── M-08c 보고자 확인 루프 (비차단) ───────────────────────

RESULT_CONFIRMED = "confirmed"
RESULT_CORRECTED = "corrected"


def confirm(
    report_id: int,
    result: str,
    corrected_text: str | None = None,
    worker_id: int | None = None,
) -> dict:
    """요약 확인/정정. 접수·관리자 노출을 막지 않는다(M-08c ①).

    local_failed 건은 확인 대상이 아니라 원문 에코 + 접수 안내만 돌려준다(M-08c ③).
    """
    actor = worker_actor(worker_id)
    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_CONFIRM_TARGET, {"id": report_id})
            row = cur.fetchone()
            if row is None:
                raise ReportNotFound(f"report_id={report_id}")
            processing_state, original_text = row

            if processing_state == STATE_FAILED:
                # M-08c ③ — 상태 변경·이벤트 없이 안내만
                return {
                    "id": report_id,
                    "result": "local_failed",
                    "original_text": original_text,
                    "message": "요약 생성에 실패했습니다. 신고는 정상 접수되었으며 관리자가 원문을 직접 확인합니다.",
                }

            if result == RESULT_CONFIRMED:
                cur.execute(_SET_REPORTER_CONFIRMED, {"id": report_id})
                record_event(cur, report_id, EV_REPORTER_CONFIRMED, actor=actor)
                out = {"id": report_id, "result": RESULT_CONFIRMED, "reporter_confirmed": True}
            else:
                record_event(
                    cur, report_id, EV_REPORTER_CORRECTED, actor=actor, detail=corrected_text
                )
                cur.execute(
                    _INSERT_JOB,
                    {
                        "kind": JOB_KIND_SUMMARIZE,
                        "payload": json.dumps(
                            {"report_id": report_id, "reason": EV_REPORTER_CORRECTED},
                            ensure_ascii=False,
                        ),
                    },
                )
                job_id = cur.fetchone()[0]
                out = {
                    "id": report_id,
                    "result": RESULT_CORRECTED,
                    "requeued_job_id": job_id,
                    "reporter_confirmed": False,
                }
        conn.commit()
    log.info("reports: 확인 루프 report_id=%s result=%s actor=%s", report_id, result, actor)
    return out
