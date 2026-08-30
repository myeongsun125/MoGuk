"""관리자 승인큐 — glossary 후보·무근거 질의 목록 (총괄 확정 0830). [새봄]

이번 커밋 범위 = **목록 조회(읽기 전용)**. 전이(approve/reject)는 감사 이벤트 수용처
판정(0-c A/B 상신) 후 별도 반영한다 — 이벤트 없이 상태만 바꾸는 구현은 두지 않는다.

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

import logging

from app.services import tenancy

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
