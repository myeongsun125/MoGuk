"""admin_events — 관리자 전이 감사 로그 (M-08d). [새봄]

risk_report_events(M-08a)의 범용판. report_id FK 대신 target_type/target_id 로
대상을 가리켜 glossary·unanswered 등 여러 승인큐 전이를 한 테이블에 담는다.

**append-only** — 이 모듈에 UPDATE/DELETE 경로는 존재하지 않는다(M-08a 동일 규약).
actor 는 호출부가 넘긴다. 관리자 인증 부재 구간의 값은 M-15b 단일 주입 지점
(risk_reports.ADMIN_ACTOR_UNAUTHENTICATED)이며 여기서 리터럴을 새로 만들지 않는다.

컬럼은 db/migrations/001_tenant_template.sql 이 정본(R4).
"""

from __future__ import annotations

import logging

from app.services import tenancy

log = logging.getLogger(__name__)

# 001 정본 컬럼 = 응답 키. §3 등재 문안·계약 표와 3중 대조된다.
EVENT_KEYS = (
    "id", "actor", "target_type", "target_id",
    "action", "from_state", "to_state", "detail", "created_at",
)

# 조회 시간대 — 대시보드(B)와 같은 값을 쓴다. 버킷·"오늘" 판정 일관성.
EVENTS_TZ = "Asia/Seoul"

LIMIT_DEFAULT = 50
LIMIT_MAX = 200

# append-only — 이 모듈에 admin_events 대상 UPDATE/DELETE 는 존재하지 않는다 (M-08d)
_INSERT = """
INSERT INTO admin_events (actor, target_type, target_id, action, from_state, to_state, detail)
VALUES (%(actor)s, %(target_type)s, %(target_id)s, %(action)s, %(from_state)s, %(to_state)s, %(detail)s)
"""

# 필터: 날짜(Asia/Seoul 일자)·target_type. 정렬 id DESC — created_at 동률에도 삽입 역순이 보장된다.
_SELECT = """
SELECT id, actor, target_type, target_id, action, from_state, to_state, detail, created_at
FROM admin_events
WHERE (%(date)s::text IS NULL OR (created_at AT TIME ZONE %(tz)s)::date = %(date)s::date)
  AND (%(target_type)s::text IS NULL OR target_type = %(target_type)s)
ORDER BY id DESC
LIMIT %(limit)s OFFSET %(offset)s
"""


def record(
    cur,
    *,
    actor: str | None,
    target_type: str,
    target_id: int,
    action: str,
    from_state: str | None = None,
    to_state: str | None = None,
    detail: str | None = None,
) -> None:
    """감사 이벤트 1행 추가. 호출부의 커서·트랜잭션을 그대로 쓴다(전이와 원자적으로 남는다)."""
    cur.execute(
        _INSERT,
        {
            "actor": actor,
            "target_type": target_type,
            "target_id": target_id,
            "action": action,
            "from_state": from_state,
            "to_state": to_state,
            "detail": detail,
        },
    )


def _iso(value):
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def clamp_limit(limit: int | None) -> int:
    """limit 기본 50 · 최대 200. 0 이하는 기본값으로."""
    if limit is None or limit <= 0:
        return LIMIT_DEFAULT
    return min(int(limit), LIMIT_MAX)


def list_events(
    date: str | None = None,
    target_type: str | None = None,
    limit: int | None = LIMIT_DEFAULT,
    offset: int = 0,
) -> list[dict]:
    """감사 로그 조회 — 읽기 전용. date 는 'YYYY-MM-DD'(Asia/Seoul 일자)."""
    params = {
        "date": date or None,
        "target_type": target_type or None,
        "tz": EVENTS_TZ,
        "limit": clamp_limit(limit),
        "offset": max(int(offset or 0), 0),
    }
    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT, params)
            rows = cur.fetchall()
    out = []
    for r in rows:
        item = dict(zip(EVENT_KEYS, r))
        item["created_at"] = _iso(item["created_at"])
        out.append(item)
    return out
