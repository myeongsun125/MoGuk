"""jobs 폴러 — FOR UPDATE SKIP LOCKED, attempts<3 백오프. 3회 실패 시 failed + 관리자 알림 (M-08·M-08b). [새봄]

M-08b ②: 요약·severity 생성 실패(재시도 3회 소진 = local_failed)는
- 원문 보존(삭제·변형 없음) + processing_state='failed'(001 정본 실패 종단값)
- 관리자 알림(admin_alert ERROR 로그) + summary_failed 이벤트(M-08a)
- **외부 LLM 폴백 금지** — 원문 민감성. 이 모듈은 tier="local" 만 호출하며
  tier="external" 문자열이 코드 경로에 존재하지 않는다.

요약 재생성은 V5(M-08b ③). STT 경로는 V5 — 아래 스텁 분기는 호출되지 않는다.
"""

from __future__ import annotations

import json
import logging
import time

from app.services import risk_reports, tenancy
from app.services.llm_adapter import complete

log = logging.getLogger(__name__)

BACKOFF_S = 5.0  # attempts 재시도 간격 (run_after 로 지연)

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
    original_text = row[0]
    if not original_text:
        raise LocalSummaryError(f"report_id={report_id} 원문 비어 있음")

    risk_reports.mark_running(cur, report_id)
    ko_summary, severity = summarize_report(original_text)
    risk_reports.mark_summary_done(cur, report_id, ko_summary, severity)


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


def run_jobs(poll_s: float = 2.0) -> None:
    """기동~정지까지 반복. 큐가 비면 poll_s 만큼 쉰다."""
    log.info("job_runner: 시작 (poll_s=%s)", poll_s)
    while True:
        try:
            if not process_once():
                time.sleep(poll_s)
        except Exception as exc:  # noqa: BLE001 — DB 단절 등도 루프를 끊지 않는다
            log.error("job_runner: 폴링 오류 %s: %s", type(exc).__name__, exc)
            time.sleep(poll_s)
