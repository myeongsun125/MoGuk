"""SQLAlchemy 모델 — 스키마=테넌트 동적 바인딩(M-04). DDL 원본은 db/migrations/. [새봄]

현재는 agents/graph.answer 시그니처가 참조하는 Worker 자리표시자만 둔다.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Worker:
    id: int
    emp_no: str | None
    lang: str  # vi|in
    tenant_slug: str
