"""관리자 대시보드 KPI — 읽기 전용 집계 (총괄 확정 0830). [새봄]

KPI 4종 + 추이. 쓰기·이벤트 기록 없음 — SELECT 만 수행한다.

A. open_reports        미확인 위험보고 수 = risk_reports WHERE status='submitted'
B. reports_by_status   submitted/acknowledged/resolved 각 건수 (% 없음, 건수 그대로)
C. unanswered_open     무근거 질의 대기 수 = unanswered_queue WHERE status='open'
D. citation_rate       근거 인용률 — 분모 = 답변 방출 질의(gated 제외), 분자 = 출처 제시 응답
   · 방출 판별 = questions.grounded (run_ask 는 grounded=false 시 answer 를 NULL 로 적재)
   · 출처 판별 = jsonb_array_length(questions.sources) > 0
   · gated 건수는 분모에 넣지 않는다 — 그쪽은 C 담당 (M-05a 정합)
   · 게이트 설계상 100% 가 기대값이다. 미만이면 수치를 만지지 말고 원인을 보고한다.
추이. reports_today_hourly  오늘(KST) 시간대별 보고 건수 — 7일 집계 아님.
   · 버킷 경계 = created_at AT TIME ZONE 'Asia/Seoul' 의 date_trunc('hour')
   · "오늘" = 같은 변환의 date 가 now() 변환 date 와 같은 행
   · 00시부터 현재 시각(서버 now 기준)까지 빈 시간대는 count=0 으로 채운다 — 라이브 그래프용

A 는 B 의 submitted 칸과 같은 값이라 한 번의 GROUP BY 로 함께 구한다 —
쿼리를 나누면 동시 쓰기 상황에서 두 값이 어긋날 수 있다(값 정의는 동일).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from app.services import tenancy

log = logging.getLogger(__name__)

# 시연 기준 시간대. 버킷 경계·"오늘" 판정 양쪽에 같은 값을 쓴다.
DASHBOARD_TZ = "Asia/Seoul"

STATUS_KEYS = ("submitted", "acknowledged", "resolved")   # 001 CHECK 집합과 동일

# §3 등재 문안·PR 계약 표와 3중 대조되는 응답 최상위 키.
RESPONSE_KEYS = (
    "open_reports",
    "reports_by_status",
    "unanswered_open",
    "citation_rate",
    "reports_today_hourly",
    "generated_at",
    "timezone",
)
CITATION_KEYS = ("answered", "with_sources", "rate")
TREND_KEYS = ("hour", "count")

# A·B — 한 번의 GROUP BY (A = submitted 칸)
_SQL_STATUS = "SELECT status, count(*) FROM risk_reports GROUP BY status"

# C
_SQL_UNANSWERED = "SELECT count(*) FROM unanswered_queue WHERE status = 'open'"

# D — 분모는 grounded(방출)만. gated 는 제외한다.
_SQL_CITATION = """
SELECT count(*) FILTER (WHERE grounded),
       count(*) FILTER (WHERE grounded AND jsonb_array_length(sources) > 0)
FROM questions
"""

# 추이 — 오늘(KST) 시간대별. 서버 now() 를 같은 쿼리에서 받아 클록 스큐를 없앤다.
_SQL_TREND = """
SELECT to_char(date_trunc('hour', created_at AT TIME ZONE %(tz)s), 'YYYY-MM-DD HH24') AS bucket,
       count(*)
FROM risk_reports
WHERE (created_at AT TIME ZONE %(tz)s)::date = (now() AT TIME ZONE %(tz)s)::date
GROUP BY 1
ORDER BY 1
"""

_SQL_NOW = "SELECT to_char(now() AT TIME ZONE %(tz)s, 'YYYY-MM-DD HH24:MI:SS')"


def _bucket_label(day: str, hour: int) -> str:
    return f"{day} {hour:02d}"


def _hourly_series(rows: list[tuple], now_local: str) -> list[dict]:
    """00시~현재 시각까지 zero-fill. rows = [(YYYY-MM-DD HH, count), …]."""
    counts = {r[0]: int(r[1]) for r in rows}
    day, clock = now_local.split(" ")
    last_hour = int(clock.split(":")[0])
    return [
        {"hour": f"{day}T{h:02d}:00:00", "count": counts.get(_bucket_label(day, h), 0)}
        for h in range(last_hour + 1)
    ]


def get_dashboard() -> dict:
    """KPI 4종 + 오늘 시간대별 추이. 읽기 전용 — 커밋·이벤트 기록 없음."""
    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_SQL_STATUS)
            by_status = {k: 0 for k in STATUS_KEYS}
            for status, cnt in cur.fetchall():
                if status in by_status:
                    by_status[status] = int(cnt)

            cur.execute(_SQL_UNANSWERED)
            unanswered_open = int(cur.fetchone()[0])

            cur.execute(_SQL_CITATION)
            answered, with_sources = (int(x or 0) for x in cur.fetchone())

            cur.execute(_SQL_NOW, {"tz": DASHBOARD_TZ})
            now_local = cur.fetchone()[0]

            cur.execute(_SQL_TREND, {"tz": DASHBOARD_TZ})
            trend = _hourly_series(cur.fetchall(), now_local)

    rate = round(with_sources / answered, 4) if answered else None
    if rate is not None and rate < 1.0:
        # 게이트 설계상 100% 가 기대값 — 미만이면 결함 신호다. 수치는 그대로 내보낸다.
        log.warning(
            "dashboard: 근거 인용률 %.4f (<1.0) — 방출 %d건 중 출처 있는 응답 %d건",
            rate, answered, with_sources,
        )
    return {
        "open_reports": by_status["submitted"],
        "reports_by_status": by_status,
        "unanswered_open": unanswered_open,
        "citation_rate": {"answered": answered, "with_sources": with_sources, "rate": rate},
        "reports_today_hourly": trend,
        "generated_at": now_local.replace(" ", "T"),
        "timezone": DASHBOARD_TZ,
    }
