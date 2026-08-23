"""백트랜슬레이션 검증 + 고위험 판정 (M-10). τ = M-10a 실측값 — tenant_settings에서 읽는다. [새봄]"""

from dataclasses import dataclass

from app.agents.classify import Cls
from app.agents.retrieve import Chunk


@dataclass(frozen=True)
class Verify:
    score: float
    passed: bool


def verify_backtranslation(src: str, out: str) -> Verify:
    raise NotImplementedError("[새봄] agents.verify.verify_backtranslation")


def is_high_risk(cls: Cls, chunks: list[Chunk]) -> bool:
    # 질의분류(cls.category=='safety') OR 청크 메타(chunks[].meta.category=='safety')
    raise NotImplementedError("[새봄] agents.verify.is_high_risk")
