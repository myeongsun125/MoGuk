"""jobs 폴러 — FOR UPDATE SKIP LOCKED, attempts<3 백오프. 3회 실패 시 failed + 관리자 알림 (M-08). [새봄]"""


def run_jobs(poll_s: float = 2.0) -> None:
    raise NotImplementedError("[새봄] workers.job_runner.run_jobs")


def summarize_report(text: str) -> tuple[str, str]:
    """→ (ko_summary, severity). 로컬 티어 고정. severity ∈ {high, medium, low}."""
    raise NotImplementedError("[새봄] workers.job_runner.summarize_report")
