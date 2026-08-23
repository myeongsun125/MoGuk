"""그래프 엔트리 — classify → retrieve → translate → verify (≤3홉). [새봄]"""

from dataclasses import dataclass, field

from app.models import Worker


@dataclass(frozen=True)
class Answer:
    answer: str
    sources: list[dict] = field(default_factory=list)
    verify: dict = field(default_factory=dict)  # {score, passed, gated}
    trace_id: str = ""


def answer(question: str, lang: str, worker: Worker) -> Answer:
    raise NotImplementedError("[새봄] agents.graph.answer")
