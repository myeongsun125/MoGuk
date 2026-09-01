"""PII 마스킹 — 관리자 응답 표시 계층 전용, 저장값 무접촉 (총괄 지시 0902). [새봄]

적용 지점(2곳뿐 — services/risk_reports.py):
- 관리자 상세(get_report_detail): original_text·ko_summary
- 관리자 목록(list_reports): ko_summary
접수·워커(요약 LLM 입력)·근로자 확인 에코 경로에는 적용하지 않는다 — DB 저장값·원본 무변경.

env PII_MASK 기본 on — 명시적 off 값만 끈다(agents/verify._flag_off 동형).

규칙·출력 형식은 총괄 확정 전 잠정 — 확정이 오면 MASK_RULES 의 해당 행 1줄만 교체한다.
사번(emp_no) 규칙 없음: 001_tenant_template.sql:20 `emp_no text UNIQUE`(형식 제약 없음),
invites._validate(:88-99) 는 비어있지 않음만 검사 — 형식 미확정이라 연락처만 구현(지시 "추측 금지").
이름 마스킹 없음(지시 — 대상 아님).
"""

from __future__ import annotations

import os
import re

MASK_ENV = "PII_MASK"

# 국내 휴대폰 010+8자리 — 하이픈·공백·무구분 3형태만. 구분자는 백레퍼런스로 동일 반복을
# 강제하고, (?<!\d)·(?!\d) 경계로 더 긴 숫자열 내부 부분 일치를 막는다(오탐 가드).
_KR_MOBILE_RE = re.compile(r"(?<!\d)010([- ]?)(\d{4})\1(\d{4})(?!\d)")

# 베트남 +84 · 인도네시아 +62 — 리터럴 국가번호 접두 필수, 뒤로 7~12자리(공백·하이픈 허용).
# 일반 숫자 나열은 '+' 접두가 없어 닿지 않는다(오탐 가드 — 광범위 숫자 매칭 금지).
_INTL_RE = re.compile(r"\+(?:84|62)(?:[- ]?\d){7,12}(?!\d)")


def _mask_intl(m: re.Match) -> str:
    """국가번호·구분자 보존, 마지막 3자리 외 숫자를 * 로 (+84 912 345 678 → +84 *** *** 678)."""
    head, rest = m.group(0)[:3], m.group(0)[3:]
    digit_at = [i for i, ch in enumerate(rest) if ch.isdigit()]
    keep = set(digit_at[-3:])
    return head + "".join(
        "*" if ch.isdigit() and i not in keep else ch for i, ch in enumerate(rest)
    )


# 규칙표 — 1행 = 1규칙(패턴, 치환). 출력 형식 확정이 오면 해당 행만 교체한다.
# 국제번호를 먼저 적용해 "+62 010 …" 류가 국내 규칙에 겹쳐 닿지 않게 한다.
MASK_RULES: tuple = (
    (_INTL_RE, _mask_intl),             # +84·+62 → 마지막 3자리만 노출 (잠정)
    (_KR_MOBILE_RE, r"010\1****\1\3"),  # 010 → 가운데 4자리 * (잠정)
)


def _mask_off() -> bool:
    """기본 on 플래그 — 명시적 off 값만 끈다."""
    return (os.getenv(MASK_ENV) or "").strip().lower() in ("0", "false", "off", "no")


def mask_pii(text: str | None) -> str | None:
    """표시용 마스킹. off·None·비문자열은 원값 그대로 — 반환값을 저장 경로에 쓰지 않는다."""
    if not isinstance(text, str) or _mask_off():
        return text
    for pattern, repl in MASK_RULES:
        text = pattern.sub(repl, text)
    return text
