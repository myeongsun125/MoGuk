"""질의 분류 — intent/category/lang. [새봄]"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Cls:
    intent: str
    category: str  # process|instruction|safety|equipment
    lang: str  # vi|in


def classify(text: str) -> Cls:
    raise NotImplementedError("[새봄] agents.classify.classify")
