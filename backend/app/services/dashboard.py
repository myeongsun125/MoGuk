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
# M-38 학습 KPI 4키는 말미에 추가만 한다 — 기존 키 제거·개명 금지(총괄 지시 0902).
RESPONSE_KEYS = (
    "open_reports",
    "reports_by_status",
    "unanswered_open",
    "citation_rate",
    "reports_today_hourly",
    "generated_at",
    "timezone",
    "per_worker",
    "per_module",
    "completion_rate",
    "avg_comprehension",
)
CITATION_KEYS = ("answered", "with_sources", "rate")
TREND_KEYS = ("hour", "count")
PER_WORKER_KEYS = ("worker_id", "quiz_set_id", "score", "label", "created_at")
PER_MODULE_KEYS = ("module", "n", "avg_score")
COMPLETION_KEYS = ("workers_attempted", "workers_activated", "rate")

# A·B — 한 번의 GROUP BY (A = submitted 칸)
_SQL_STATUS = "SELECT status, count(*) FROM risk_reports GROUP BY status"

# C
_SQL_UNANSWERED = "SELECT count(*) FROM unanswered_queue WHERE status = 'open'"

# D — 분모 = 답변 방출(§3:234). grounded 만으로는 threshold 차단 행
#     (grounded=true·gated=true·sources=[])이 분모에 남는다 — trace.verify.gated 로
#     분모·분자 양쪽에서 제외한다. 판별자는 run_ask 첫 구현(403f027)부터 전 행에
#     기록됐고, 키 부재 행은 NULL → IS DISTINCT FROM 이 미차단으로 계산(하위 호환).
_SQL_CITATION = """
SELECT count(*) FILTER (WHERE grounded
                          AND (trace -> 'verify' -> 'gated') IS DISTINCT FROM 'true'::jsonb),
       count(*) FILTER (WHERE grounded
                          AND (trace -> 'verify' -> 'gated') IS DISTINCT FROM 'true'::jsonb
                          AND jsonb_array_length(sources) > 0)
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

# ── 학습 KPI (M-38) — 라벨 경계(80/90)는 v_comprehension 뷰(001:69)에 하드코딩. 무접촉. ──

_SQL_PER_WORKER = """
SELECT worker_id, quiz_set_id, score, label, created_at
FROM v_comprehension ORDER BY worker_id, quiz_set_id
"""

_SQL_PER_MODULE = """
SELECT qs.module, count(*), avg(v.score)
FROM v_comprehension v JOIN quiz_sets qs ON qs.id = v.quiz_set_id
GROUP BY qs.module ORDER BY qs.module
"""

# 분모 = 활성 근로자(activated_at 존재), 분자 = 시도 근로자(quiz_attempts DISTINCT worker_id)
_SQL_COMPLETION = """
SELECT (SELECT count(DISTINCT worker_id) FROM quiz_attempts WHERE worker_id IS NOT NULL),
       (SELECT count(*) FROM workers WHERE activated_at IS NOT NULL)
"""

_SQL_AVG_COMPREHENSION = "SELECT avg(score) FROM v_comprehension"


def _num(value):
    """DB numeric → JSON 수 — 정수값은 int, 아니면 float."""
    if value is None:
        return None
    f = float(value)
    return int(f) if f.is_integer() else f


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

            # 학습 KPI (M-38) — 전부 SELECT, 라벨은 뷰 계산값 그대로
            cur.execute(_SQL_PER_WORKER)
            per_worker = [
                {"worker_id": w, "quiz_set_id": s, "score": _num(sc), "label": lb,
                 "created_at": at.isoformat() if hasattr(at, "isoformat") else at}
                for w, s, sc, lb, at in cur.fetchall()
            ]
            cur.execute(_SQL_PER_MODULE)
            per_module = [
                {"module": m, "n": int(n), "avg_score": round(float(avg), 1)}
                for m, n, avg in cur.fetchall()
            ]
            cur.execute(_SQL_COMPLETION)
            attempted, activated = (int(x or 0) for x in cur.fetchone())
            cur.execute(_SQL_AVG_COMPREHENSION)
            avg_row = cur.fetchone()
            avg_comprehension = (
                round(float(avg_row[0]), 1) if avg_row and avg_row[0] is not None else None
            )

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
        # M-38 학습 KPI — 추가만(기존 키 무변경). completion 분모 0 이면 rate null.
        "per_worker": per_worker,
        "per_module": per_module,
        "completion_rate": {
            "workers_attempted": attempted,
            "workers_activated": activated,
            "rate": round(attempted / activated, 4) if activated else None,
        },
        "avg_comprehension": avg_comprehension,
    }
