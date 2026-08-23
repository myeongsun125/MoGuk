"""학습카드·퀴즈 — 시드 + generate_quiz 드래프트 + 관리자 승인 (M-11). [새봄]"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class QuizDraft:
    title: str
    source_doc_id: int | None
    items: list[dict] = field(default_factory=list)  # {"q_ko","q_vi","q_in","choices":[..],"answer_idx","explain"}
    status: str = "draft"


def generate_quiz(doc_ids: list[int]) -> QuizDraft:
    raise NotImplementedError("[새봄] modules.learning.generate_quiz")
