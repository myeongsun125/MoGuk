"""M-19 적용 지점 — risk_reports.original_text 봉인 저장 + 이중 읽기. [새봄]

검증 대상 계약:
- 쓰기 1지점(접수 INSERT): 저장값이 "enc1:" 접두 봉인문이고 평문이 남지 않는다
- 키 미설정 시 접수(쓰기)가 CryptoKeyError 로 실패한다 — 평문 폴백 저장 없음
- 읽기 4지점(get_report · 관리자 상세 · confirm 대상 · 요약 job)이 평문을 돌려준다
- 마커 없는 기존 행(평문)은 그대로 통과한다 — 이중 읽기

fake cursor·env 주입 — 네트워크·LLM 실호출 없음.
"""

import base64
import os
from datetime import datetime, timezone

import pytest

from app.services import crypto, risk_reports
from app.workers import job_runner

AT = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
PLAIN = "프레스 방호장치가 작동하지 않습니다."
REPORT_ID = 12


@pytest.fixture(autouse=True)
def _keyed(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/test")
    monkeypatch.setenv(crypto.KEY_ENV, base64.urlsafe_b64encode(os.urandom(32)).decode())
    yield


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
        return self.store.get("rows", [])


class Conn:
    def __init__(self, store):
        self.store = store

    def cursor(self):
        return Cursor(self.store)

    def commit(self):
        self.store["commits"] += 1


def fake_connect(store):
    from contextlib import contextmanager

    @contextmanager
    def _connect(slug=None):
        store["connects"] += 1
        yield Conn(store)

    return _connect


def _store(returns, rows=None):
    return {"calls": [], "returns": returns, "rows": rows or [],
            "commits": 0, "connects": 0}


def _patch(monkeypatch, store):
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))


def _param(store, needle, key):
    return [c[1] for c in store["calls"] if needle in c[0]][0][key]


# ── 쓰기 ──────────────────────────────────────────────────

def _submit_store():
    return _store([
        ("INSERT INTO risk_reports", (REPORT_ID, AT)),
        ("INSERT INTO jobs", (5,)),
    ])


def test_submit_stores_sealed_text(monkeypatch):
    store = _submit_store()
    _patch(monkeypatch, store)

    risk_reports.submit_text_report(PLAIN, "ko")

    stored = _param(store, "INSERT INTO risk_reports", "original_text")
    assert stored.startswith(crypto.ENC_MARKER)
    assert PLAIN not in stored                       # 평문이 컬럼에 남지 않는다
    assert crypto.open_text(stored) == PLAIN         # 복호하면 원문
    assert store["commits"] == 1


def test_submit_without_key_fails(monkeypatch):
    """평문 폴백 쓰기 금지 — 키가 없으면 접수가 실패해야 한다."""
    monkeypatch.delenv(crypto.KEY_ENV, raising=False)
    store = _submit_store()
    _patch(monkeypatch, store)

    with pytest.raises(crypto.CryptoKeyError):
        risk_reports.submit_text_report(PLAIN, "ko")
    assert not any("INSERT INTO risk_reports" in c[0] for c in store["calls"])
    assert store["commits"] == 0


# ── 읽기 4지점 ────────────────────────────────────────────

def _detail_row(text):
    # _DETAIL_KEYS 16개 순서대로
    return (REPORT_ID, "text", text, "ko", "요약", "high", "submitted", "done",
            False, None, None, None, None, None, AT, AT)


def _report_row(text):
    # get_report 키 11개
    return (REPORT_ID, "text", text, "ko", "요약", "high", "submitted", "done", False, AT, AT)


@pytest.mark.parametrize("sealed", [True, False])
def test_get_report_returns_plaintext(monkeypatch, sealed):
    stored = crypto.seal_text(PLAIN) if sealed else PLAIN
    store = _store([("SELECT id, source, original_text", _report_row(stored))])
    _patch(monkeypatch, store)

    out = risk_reports.get_report(REPORT_ID)
    assert out["original_text"] == PLAIN


@pytest.mark.parametrize("sealed", [True, False])
def test_admin_detail_returns_plaintext(monkeypatch, sealed):
    stored = crypto.seal_text(PLAIN) if sealed else PLAIN
    store = _store([("SELECT id, source, original_text", _detail_row(stored))], rows=[])
    _patch(monkeypatch, store)

    out = risk_reports.get_report_detail(REPORT_ID)
    assert out["original_text"] == PLAIN
    assert out["events"] == []


@pytest.mark.parametrize("sealed", [True, False])
def test_confirm_local_failed_echo_is_plaintext(monkeypatch, sealed):
    """M-08c ③ 원문 에코 — 암호문이 응답으로 새지 않는다."""
    stored = crypto.seal_text(PLAIN) if sealed else PLAIN
    store = _store([("SELECT processing_state, original_text",
                     (risk_reports.STATE_FAILED, stored))])
    _patch(monkeypatch, store)

    out = risk_reports.confirm(REPORT_ID, "confirmed")
    assert out["result"] == "local_failed"
    assert out["original_text"] == PLAIN


@pytest.mark.parametrize("sealed", [True, False])
def test_summarize_job_decrypts_before_llm(monkeypatch, sealed):
    stored = crypto.seal_text(PLAIN) if sealed else PLAIN
    seen = {}

    def _summarize(text):
        seen["text"] = text
        return ("요약", "high")

    monkeypatch.setattr(job_runner, "summarize_report", _summarize)
    monkeypatch.setattr(job_runner.risk_reports, "mark_running", lambda cur, rid: None)
    monkeypatch.setattr(job_runner.risk_reports, "mark_summary_done",
                        lambda cur, rid, ko, sev: None)
    store = _store([("SELECT original_text FROM risk_reports", (stored,))])

    job_runner._handle_summarize(Cursor(store), {"id": 1, "payload": {"report_id": REPORT_ID}})

    assert seen["text"] == PLAIN                     # 복호된 평문이 LLM 으로 간다
    assert crypto.ENC_MARKER not in seen["text"]


# ── 누출 방지 ─────────────────────────────────────────────

def test_list_and_public_keys_exclude_original_text():
    """목록·근로자 조회 응답에는 원문 자체가 없다 — 암호문도 나가지 않는다."""
    assert "original_text" not in risk_reports._LIST_KEYS
    assert "original_text" not in risk_reports._PUBLIC_KEYS
