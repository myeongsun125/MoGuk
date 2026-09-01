"""num_compare.py — 숫자 토큰 다중집합 대조 (C-lite (a) trace 기록용). [새봄]

원문(게이트 src)과 되번역문에서 숫자 토큰을 뽑아 다중집합으로 비교한다.
게이트 판정에는 관여하지 않는다 — trace.verify 실측 기록 전용.

숫자 토큰 규칙:
  ① 천단위 구분자: 1,200 -> 1200 (숫자,숫자3자리 형태만 제거. "3, 4개" 같은 나열은 미결합)
  ② 소수점: 1.5 그대로. 문말 마침표는 토큰에 포함하지 않는다(뒤에 숫자가 와야 소수점).
  ③ 범위: 1~1.5 / 3~4 는 물결·하이픈이 구분자이므로 독립 토큰 2개로 추출된다.
  ④ 단위 접미: 20 mm / 20mm / 25kg / 320 ms — 단위는 토큰에 포함하지 않고 수치만 비교한다.
     (단위 자체가 바뀐 오염은 이 축에서 잡지 않는다 — 한계)
  ⑤ 표기 정규화: 8 과 8.0 은 같은 값으로 본다(Decimal normalize).
  ⑥ 전각 숫자·한글 수사(세 번)·한자 수사는 추출 대상이 아니다 — 한계.
"""

from __future__ import annotations

import re
from collections import Counter
from decimal import Decimal, InvalidOperation

_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def num_tokens(s: str) -> list[str]:
    """문자열에서 숫자 토큰을 정규화해 추출한다."""
    s = _THOUSANDS.sub("", s or "")
    out: list[str] = []
    for m in _NUMBER.findall(s):
        try:
            d = Decimal(m).normalize()
        except InvalidOperation:
            continue
        out.append(format(d, "f"))     # 1E+2 같은 지수 표기를 피한다
    return out


def num_compare(src: str, back: str) -> dict:
    """다중집합 비교 결과. mismatch=True 면 숫자가 달라진 것."""
    a, b = Counter(num_tokens(src)), Counter(num_tokens(back))
    src_only = sorted((a - b).elements())
    back_only = sorted((b - a).elements())
    return {
        "mismatch": bool(src_only or back_only),
        "src_only": src_only,
        "back_only": back_only,
    }
