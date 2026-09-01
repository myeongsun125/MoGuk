"""PII 마스킹(표시 계층) — 연락처 3형태·국제번호 + 오탐 금지 6건 (총괄 지시 0902). [새봄]

사번(emp_no) 규칙 없음 — 001_tenant_template.sql:20 `emp_no text UNIQUE`(형식 제약 없음),
invites._validate 는 비어있지 않음만 검사 → 형식 미확정으로 제외(지시 "추측 금지").

적용 지점 검증은 fake cursor(test_report_seal 동형) — 네트워크·DB 실호출 없음.
"""

from datetime import datetime, timezone

import pytest

from app.services import risk_reports
from app.services.pii_mask import MASK_ENV, mask_pii

AT = datetime(2026, 9, 2, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _default_on(monkeypatch):
    """기본값(on) 검증 — 개발 환경에 PII_MASK 가 설정돼 있어도 격리한다."""
    monkeypatch.delenv(MASK_ENV, raising=False)
    yield


# ── 국내 휴대폰 3형태 (하이픈·공백·무구분) ────────────────

@pytest.mark.parametrize("raw, masked", [
    ("010-1234-5678", "010-****-5678"),
    ("010 1234 5678", "010 **** 5678"),
    ("01012345678", "010****5678"),
])
def test_kr_mobile_three_forms(raw, masked):
    assert mask_pii(f"연락처는 {raw} 입니다") == f"연락처는 {masked} 입니다"


# ── 국제번호 (+84·+62) ────────────────────────────────────

def test_vn_intl_spaced():
    assert mask_pii("+84 912 345 678") == "+84 *** *** 678"


def test_vn_intl_compact():
    assert mask_pii("+84912345678") == "+84******678"


def test_id_intl_spaced():
    assert mask_pii("+62 812 3456 7890") == "+62 *** **** *890"


# ── 오탐 금지 6건 — 치수·수치 표기는 원문 그대로 ──────────

@pytest.mark.parametrize("text", ["20mm", "320ms", "0.45", "3/3", "2026-09-02", "7427b14"])
def test_no_false_positive(text):
    assert mask_pii(text) == text


def test_no_false_positive_in_sentence():
    s = "게이트 τ 0.45, 인용률 3/3, 지연 320ms, 틈새 20mm — 2026-09-02 head 7427b14"
    assert mask_pii(s) == s


def test_longer_digit_run_untouched():
    """010 뒤 8자리 초과·앞자리 연속 — 더 긴 숫자열 내부 부분 일치 금지."""
    assert mask_pii("계좌 9010-1234-5678") == "계좌 9010-1234-5678"
    assert mask_pii("일련번호 010123456789") == "일련번호 010123456789"


# ── env off · 비문자열 통과 ───────────────────────────────

def test_env_off_returns_verbatim(monkeypatch):
    monkeypatch.setenv(MASK_ENV, "off")
    assert mask_pii("010-1234-5678 / +84 912 345 678") == "010-1234-5678 / +84 912 345 678"


def test_none_passthrough():
    assert mask_pii(None) is None


# ── 적용 지점 — 관리자 응답 조립 시점만 (fake cursor, test_report_seal 동형) ──

class Cursor:
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.store["calls"].append((sql, params))

    def fetchone(self):
        sql = self.store["calls"][-1][0]
        for needle, value in self.store["returns"]:
            if needle in sql:
                return value
        return None

    def fetchall(self):
        sql = self.store["calls"][-1][0]
        return self.store["rows"] if "FROM risk_reports" in sql else []


class Conn:
    def __init__(self, store):
        self.store = store

    def cursor(self):
        return Cursor(self.store)

    def commit(self):
        self.store["commits"] += 1


def _patch(monkeypatch, store):
    from contextlib import contextmanager

    @contextmanager
    def _connect(slug=None):
        yield Conn(store)

    monkeypatch.setattr(risk_reports.tenancy, "connect", _connect)


def _store(returns, rows=None):
    return {"calls": [], "returns": returns, "rows": rows or [], "commits": 0}


ORIGINAL = "연락처 010-1234-5678 문의"
SUMMARY = "보고자 +84 912 345 678 연락 요망"


def _detail_row():
    # _DETAIL_KEYS 16개 순서대로 — original_text 는 평문 행(M-19 이중 읽기 마커 없음)
    return (7, "text", ORIGINAL, "vi", SUMMARY, "high", "submitted", "done",
            False, None, None, None, None, None, AT, AT)


def test_admin_detail_masks_display_fields(monkeypatch):
    store = _store([("SELECT id, source, original_text", _detail_row())])
    _patch(monkeypatch, store)

    out = risk_reports.get_report_detail(7)

    assert out["original_text"] == "연락처 010-****-5678 문의"
    assert out["ko_summary"] == "보고자 +84 *** *** 678 연락 요망"
    # 저장 경로 무접촉 — 이 함수의 쓰기는 원문 열람 감사 이벤트 INSERT 1건뿐
    writes = [c[0] for c in store["calls"] if "INSERT" in c[0] or "UPDATE" in c[0]]
    assert len(writes) == 1 and "risk_report_events" in writes[0]


def test_admin_list_masks_ko_summary(monkeypatch):
    store = _store([], rows=[(7, "호출 010 9876 5432 요청", "high", "submitted", "done", False, AT)])
    _patch(monkeypatch, store)

    out = risk_reports.list_reports()

    assert out[0]["ko_summary"] == "호출 010 **** 5432 요청"


def test_admin_list_none_summary_passthrough(monkeypatch):
    """요약 생성 전(ko_summary NULL) 행 — 마스킹이 None 을 건드리지 않는다."""
    store = _store([], rows=[(8, None, None, "submitted", "queued", False, AT)])
    _patch(monkeypatch, store)

    out = risk_reports.list_reports()

    assert out[0]["ko_summary"] is None
