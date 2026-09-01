"""neg_lexicon.py — KO 부정어 사전 단일 출처 (D13-A).

scripts/seed_check.py 에 있던 정의를 문구·정규식 무변경으로 이관했다.
seed_check 와 백엔드(trace 기록)가 같은 객체를 참조한다 — 복제 금지.
"""
from __future__ import annotations

import re


# ko 사전 (2026-08-29 총괄 확정): 장형 부정(-지 않다/-지 못하다)·금지형(-지 말다/-여서는 안 되다)·
# 존재 부정(없다)·계사 부정(아니다) 포함. 단형 안/못, 명사 '금지', '모르다' 제외.
KO_NEG_LEXICON = re.compile(
    r"(지\s?않|지\s?못|지\s?마|지\s?말|(?:어|아|여|해|워|라|서)서는\s?(?:안|아니)\s?(?:되|됩)"
    r"|없(?=다|습|어|으|는|이|음|을|고|지)|아니(?=다|ㅂ|에|야|고|며|라|오)|아닙|아닌)")


def ko_neg(s: str) -> int:
    return len(KO_NEG_LEXICON.findall(s))
