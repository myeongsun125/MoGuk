"""용어사전 주입 번역 — 외부 티어 허용(M-17), 실패 시 로컬 폴백. [새봄]"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Term:
    term_ko: str
    term_vi: str | None = None
    term_in: str | None = None


def translate(text: str, src: str, tgt: str, glossary: list[Term]) -> str:
    raise NotImplementedError("[새봄] agents.translate.translate")
