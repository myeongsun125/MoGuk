"""관리자 승인큐 — glossary 후보·무근거 질의 목록 (총괄 확정 0830). [새봄]

범위 = 목록 조회 + 전이(approve/reject, unanswered answer). 전이는 admin_events 1행을 함께 남긴다(M-08d).

M-08d 배선:
- 수용처 = admin_events (범용 감사 — actor text·target_type/target_id·from/to·detail)
- actor = risk_reports.ADMIN_ACTOR_UNAUTHENTICATED 재사용 (M-15b 단일 주입 지점, 새 리터럴 금지)
- glossary.approved_by 는 integer FK 라 NULL 유지(M-15b 판정 1 동일), approved_at 은 승인 시각만 갱신
- reject 사유를 담을 컬럼이 001 glossary 에 없다 — glossary.note 는 용어 설명이라 덮으면 자료가
  사라진다. 따라서 사유는 admin_events.detail 에 남기고 note 는 건드리지 않는다

필드는 001 정본 전사 (db/migrations/001_tenant_template.sql, R4):
  glossary(id, term_ko, term_vi, term_in, note, status, source_question_id, approved_by, approved_at)
    · status CHECK ('draft','approved','rejected') — 승인/반려 종단값이 001 에 실재
    · created_at 컬럼은 001 에 없다 — 목록 정렬은 id 기준
  unanswered_queue(id, question_id, status, admin_answer, answered_by, answered_at, ingested_doc_id)
    · status CHECK ('open','answered')
    · 적재 대상은 M-05a 2종(no_chunks·no_answer)뿐 — 시스템 오류는 agents/graph.py 가 걸러
      애초에 넣지 않는다(테이블에 사유 컬럼은 없다)
질문 본문은 questions 조인으로 얻는다(unanswered_queue.question_id FK).
"""

from __future__ import annotations

import json
import logging

from app.services import admin_events, tenancy
from app.services.risk_reports import ADMIN_ACTOR_UNAUTHENTICATED

log = logging.getLogger(__name__)

# 001 CHECK 집합
GLOSSARY_STATUS = ("draft", "approved", "rejected")
UNANSWERED_STATUS = ("open", "answered")

GLOSSARY_DEFAULT_STATUS = "draft"
UNANSWERED_DEFAULT_STATUS = "open"

# §3 등재 문안·PR 계약 표와 3중 대조되는 응답 키 (001 실명 그대로)
GLOSSARY_KEYS = (
    "id", "term_ko", "term_vi", "term_in", "note",
    "status", "source_question_id", "approved_by", "approved_at",
)
UNANSWERED_KEYS = (
    "id", "question_id", "status", "question", "lang",
    "question_created_at", "admin_answer", "answered_at",
)

_LIST_GLOSSARY = """
SELECT id, term_ko, term_vi, term_in, note, status, source_question_id, approved_by, approved_at
FROM glossary
WHERE (%(status)s::text IS NULL OR status = %(status)s)
ORDER BY id
"""

_LIST_UNANSWERED = """
SELECT u.id, u.question_id, u.status, q.question, q.lang, q.created_at, u.admin_answer, u.answered_at
FROM unanswered_queue u
LEFT JOIN questions q ON q.id = u.question_id
WHERE (%(status)s::text IS NULL OR u.status = %(status)s)
ORDER BY u.id DESC
"""


def _iso(value):
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _row(keys, row) -> dict:
    out = dict(zip(keys, row))
    for k in ("approved_at", "answered_at", "question_created_at"):
        if k in out:
            out[k] = _iso(out[k])
    return out


def list_glossary(status: str | None = GLOSSARY_DEFAULT_STATUS) -> list[dict]:
    """용어 후보 목록. 기본 필터 draft — status=None 이면 전체."""
    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_LIST_GLOSSARY, {"status": status or None})   # ?status= 빈 값 = 전체
            rows = cur.fetchall()
    return [_row(GLOSSARY_KEYS, r) for r in rows]


def list_unanswered(status: str | None = UNANSWERED_DEFAULT_STATUS) -> list[dict]:
    """무근거 질의 대기 목록(M-05·M-05a). 기본 필터 open — status=None 이면 전체."""
    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_LIST_UNANSWERED, {"status": status or None})   # ?status= 빈 값 = 전체
            rows = cur.fetchall()
    return [_row(UNANSWERED_KEYS, r) for r in rows]


# ── 전이 (M-08d) ──────────────────────────────────────────

EV_GLOSSARY_APPROVED = "glossary_approved"
EV_GLOSSARY_REJECTED = "glossary_rejected"
TARGET_GLOSSARY = "glossary"

# draft 에서만 전이한다 — 승인·반려 후 되돌리는 경로는 두지 않는다(M-08 단방향 패턴).
GLOSSARY_TRANSITIONS = {"approve": "approved", "reject": "rejected"}
GLOSSARY_FROM_STATE = "draft"


class TransitionError(Exception):
    """draft 아닌 항목에 전이 시도 — 라우터가 422 로 변환."""


class TermNotFound(Exception):
    """대상 용어 없음 — 404."""


_SELECT_STATUS_FOR_UPDATE = "SELECT status FROM glossary WHERE id = %(id)s FOR UPDATE"

# approved_by(integer FK)는 건드리지 않는다 — M-15b 판정 1 과 동일. 행위자는 admin_events.actor 단독.
_APPROVE = "UPDATE glossary SET status = %(to_state)s, approved_at = now() WHERE id = %(id)s"
# reject 는 승인 시각이 아니므로 approved_at 을 채우지 않는다. 사유는 admin_events.detail.
_REJECT = "UPDATE glossary SET status = %(to_state)s WHERE id = %(id)s"


def _transition(term_id: int, action: str, sql: str, event: str, detail: str | None) -> dict:
    """draft → approved|rejected 1회. 스냅숏 갱신 + admin_events 1행을 한 트랜잭션으로."""
    to_state = GLOSSARY_TRANSITIONS[action]
    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_STATUS_FOR_UPDATE, {"id": term_id})
            row = cur.fetchone()
            if row is None:
                raise TermNotFound(f"glossary_id={term_id}")
            current = row[0]
            if current != GLOSSARY_FROM_STATE:
                raise TransitionError(
                    f"{current} → {to_state} 불가 ({GLOSSARY_FROM_STATE} 에서만)"
                )

            cur.execute(sql, {"id": term_id, "to_state": to_state})
            admin_events.record(
                cur,
                actor=ADMIN_ACTOR_UNAUTHENTICATED,
                target_type=TARGET_GLOSSARY,
                target_id=term_id,
                action=event,
                from_state=current,
                to_state=to_state,
                detail=detail,
            )
        conn.commit()
    log.info("glossary: 전이 id=%s %s → %s", term_id, GLOSSARY_FROM_STATE, to_state)
    return {"id": term_id, "status": to_state}


def approve_glossary(term_id: int) -> dict:
    """draft → approved. approved_at 갱신, approved_by 는 NULL 유지(M-15b)."""
    return _transition(term_id, "approve", _APPROVE, EV_GLOSSARY_APPROVED, None)


def reject_glossary(term_id: int, note: str | None = None) -> dict:
    """draft → rejected. 사유는 admin_events.detail 에 보존 — glossary.note 는 무접촉."""
    return _transition(term_id, "reject", _REJECT, EV_GLOSSARY_REJECTED, note)


# ── unanswered 답변 전이 (M-05a) ───────────────────────────

EV_UNANSWERED_ANSWERED = "unanswered_answered"
TARGET_UNANSWERED = "unanswered"

# jobs.kind — 001:126 주석의 'ingest_answer' 그대로. 적재는 job_runner 가 맡는다.
JOB_KIND_INGEST_ANSWER = "ingest_answer"

# open 에서만 전이한다 — answered 를 되돌리는 경로는 두지 않는다(M-08 단방향 패턴).
UNANSWERED_FROM_STATE = "open"
UNANSWERED_TO_STATE = "answered"


class UnansweredNotFound(Exception):
    """대상 무근거 질의 없음 — 404."""


class InvalidAnswer(Exception):
    """answer 본문 text 누락·공백 — 422."""


_SELECT_UNANSWERED_FOR_UPDATE = """
SELECT id, status FROM unanswered_queue WHERE question_id = %(question_id)s FOR UPDATE
"""

# answered_by(integer FK)는 건드리지 않는다 — M-15b 판정 1 과 동일. 행위자는 admin_events.actor 단독.
_ANSWER = """
UPDATE unanswered_queue
SET status = %(to_state)s, admin_answer = %(text)s, answered_at = now()
WHERE id = %(id)s
RETURNING answered_at
"""

# 적재는 비동기 — 전이 트랜잭션은 jobs 1행만 남기고 끝낸다(M-18 큐).
_INSERT_JOB = """
INSERT INTO jobs (kind, payload) VALUES (%(kind)s, %(payload)s::jsonb) RETURNING id
"""


def answer_unanswered(question_id: int, text: str | None) -> dict:
    """open → answered 1회 + ingest_answer job 적재를 한 트랜잭션으로.

    §3:240 응답 = {id, status:'answered', answered_at, ingest_job_id}.
    id 는 unanswered_queue.id — GET /admin/unanswered 목록의 id 와 같은 축이다
    (경로 파라미터는 question_id, admin_events.target_id 도 question_id).
    """
    body = (text or "").strip()
    if not body:
        raise InvalidAnswer("text 는 필수입니다 (공백 불가)")

    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_UNANSWERED_FOR_UPDATE, {"question_id": question_id})
            row = cur.fetchone()
            if row is None:
                raise UnansweredNotFound(f"question_id={question_id}")
            queue_id, current = row[0], row[1]
            if current != UNANSWERED_FROM_STATE:
                raise TransitionError(
                    f"{current} → {UNANSWERED_TO_STATE} 불가 ({UNANSWERED_FROM_STATE} 에서만)"
                )

            cur.execute(_ANSWER, {"id": queue_id, "to_state": UNANSWERED_TO_STATE, "text": body})
            answered_at = cur.fetchone()[0]

            payload = {
                "unanswered_id": queue_id,
                "question_id": question_id,
                "text": body,
            }
            cur.execute(
                _INSERT_JOB,
                {
                    "kind": JOB_KIND_INGEST_ANSWER,
                    "payload": json.dumps(payload, ensure_ascii=False),
                },
            )
            job_id = cur.fetchone()[0]

            # detail 은 001:164 상 text 컬럼이라 JSON 문자열로 싣는다.
            # ingested_doc_id 는 적재 job 이 끝나야 정해지므로 전이 시점에는 null 이다.
            admin_events.record(
                cur,
                actor=ADMIN_ACTOR_UNAUTHENTICATED,
                target_type=TARGET_UNANSWERED,
                target_id=question_id,
                action=EV_UNANSWERED_ANSWERED,
                from_state=current,
                to_state=UNANSWERED_TO_STATE,
                detail=json.dumps(
                    {"ingested_doc_id": None, "text_len": len(body)}, ensure_ascii=False
                ),
            )
        conn.commit()
    log.info(
        "unanswered: 답변 question_id=%s queue_id=%s job=%s", question_id, queue_id, job_id
    )
    return {
        "id": queue_id,
        "status": UNANSWERED_TO_STATE,
        "answered_at": _iso(answered_at),
        "ingest_job_id": job_id,
    }
