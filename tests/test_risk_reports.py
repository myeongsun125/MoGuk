"""V3-1 위험보고 접수·워커 단위 테스트 — 네트워크·DB 없음(전부 스텁). [새봄]

검증 대상 계약:
- M-08b ①: POST /reports 는 LLM 비의존 결정론 경로 — 원문 적재 + jobs enqueue +
  report_submitted 이벤트를 한 트랜잭션으로, 202 {id, status:'submitted'}
- M-08b ②: 3회 소진(local_failed) → 원문 보존 + processing_state='failed'(001 정본) +
  admin_alert ERROR + summary_failed 이벤트. 외부 LLM 폴백 없음
- M-08a: risk_report_events 는 INSERT 전용(append-only), 전이 시 스냅숏+이벤트 양쪽 기록
- M-17·M-30: 요약은 tier="local", timeout_s=None
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import risk_reports
from app.workers import job_runner

client = TestClient(app, client=("127.0.0.1", 50000))


# ── 가짜 DB ───────────────────────────────────────────────

class FakeCursor:
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.store["calls"].append((sql, params))
        self._last = sql

    def fetchone(self):
        for needle, value in self.store.get("rows", []):
            if needle in self._last:
                return value
        return (self.store.get("default_id", 1),)


class FakeConn:
    def __init__(self, store):
        self.store = store

    def cursor(self):
        return FakeCursor(self.store)

    def commit(self):
        self.store["commits"] = self.store.get("commits", 0) + 1


def fake_connect(store):
    from contextlib import contextmanager

    @contextmanager
    def _connect(slug=None):
        store["connects"] = store.get("connects", 0) + 1
        yield FakeConn(store)

    return _connect


def _store(**kw):
    base = {"calls": [], "rows": [], "commits": 0}
    base.update(kw)
    return base


def _sqls(store):
    return [c[0] for c in store["calls"]]


def _params_for(store, needle):
    return [c[1] for c in store["calls"] if needle in c[0]]


@pytest.fixture(autouse=True)
def _base_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/test")
    monkeypatch.setenv("API_ROLE", "core")
    monkeypatch.delenv("TENANT_SLUG", raising=False)


# ── M-08b ①: 결정론 접수 ──────────────────────────────────

def test_intake_module_has_no_llm_dependency():
    """접수 경로는 llm_adapter 를 import 하지 않는다 — ollama 정지와 무관하게 동작."""
    assert not hasattr(risk_reports, "complete")
    assert not hasattr(risk_reports, "llm_adapter")


def test_submit_text_report_single_transaction(monkeypatch):
    store = _store(rows=[("INSERT INTO risk_reports", (77,)), ("INSERT INTO jobs", (9,))])
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))

    out = risk_reports.submit_text_report("프레스 안전덮개가 열려 있습니다", lang="vi")

    assert out == {"id": 77, "status": "submitted"}
    sqls = _sqls(store)
    assert any("INSERT INTO risk_reports" in s for s in sqls)
    assert any("INSERT INTO jobs" in s for s in sqls)
    assert any("INSERT INTO risk_report_events" in s for s in sqls)
    assert store["connects"] == 1 and store["commits"] == 1  # 단일 커넥션·단일 트랜잭션

    rep = _params_for(store, "INSERT INTO risk_reports")[0]
    assert rep["source"] == "text"
    assert rep["original_text"] == "프레스 안전덮개가 열려 있습니다"
    assert rep["lang"] == "vi"
    assert rep["status"] == "submitted"
    assert rep["processing_state"] == "queued"

    job = _params_for(store, "INSERT INTO jobs")[0]
    assert job["kind"] == "summarize_report"
    assert json.loads(job["payload"]) == {"report_id": 77}

    ev = _params_for(store, "INSERT INTO risk_report_events")[0]
    assert ev["action"] == "report_submitted"
    assert ev["to_state"] == "submitted"
    assert ev["report_id"] == 77


def test_submit_text_report_lang_optional(monkeypatch):
    store = _store(rows=[("INSERT INTO risk_reports", (78,)), ("INSERT INTO jobs", (10,))])
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))

    risk_reports.submit_text_report("원문만 있음")

    assert _params_for(store, "INSERT INTO risk_reports")[0]["lang"] is None


def test_post_reports_returns_202(monkeypatch):
    store = _store(rows=[("INSERT INTO risk_reports", (81,)), ("INSERT INTO jobs", (11,))])
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))

    r = client.post(
        "/api/v1/reports", json={"original_text": "컨베이어 비상정지 미작동", "lang": "vi"}
    )

    assert r.status_code == 202
    assert r.json() == {"id": 81, "status": "submitted"}


def test_post_reports_rejects_empty_text():
    assert client.post("/api/v1/reports", json={"original_text": ""}).status_code == 422
    assert client.post("/api/v1/reports", json={}).status_code == 422


# ── 요약 생성: 로컬 티어 고정 ─────────────────────────────

def test_summarize_uses_local_tier_only(monkeypatch):
    seen = {}

    def _complete(prompt, tier, timeout_s=None):
        seen.update(tier=tier, timeout_s=timeout_s, prompt=prompt)
        from app.services.llm_adapter import LLMResult

        return LLMResult(
            text='{"ko_summary": "안전덮개 개방 상태", "severity": "high"}',
            tier_used="local", model="qwen3:8b", latency_ms=10,
        )

    monkeypatch.setattr(job_runner, "complete", _complete)

    ko, sev = job_runner.summarize_report("프레스 안전덮개 열림")

    assert (ko, sev) == ("안전덮개 개방 상태", "high")
    assert seen["tier"] == "local"          # M-17: 위험보고 원문은 로컬 고정
    assert seen["timeout_s"] is None        # M-30: 티어 설정값 위임
    assert "프레스 안전덮개 열림" in seen["prompt"]


def test_summarize_raises_on_adapter_error(monkeypatch):
    from app.services.llm_adapter import LLMResult

    monkeypatch.setattr(
        job_runner, "complete",
        lambda p, t, timeout_s=None: LLMResult(
            text="", tier_used="local", model="qwen3:4b", latency_ms=1,
            error="local_failed[qwen3:8b:timeout,qwen3:4b:timeout]",
        ),
    )
    with pytest.raises(job_runner.LocalSummaryError, match="local_failed"):
        job_runner.summarize_report("원문")


@pytest.mark.parametrize(
    "text",
    ['{"ko_summary": "", "severity": "high"}',
     '{"ko_summary": "요약", "severity": "critical"}',
     "설명만 있고 JSON 없음",
     '{"ko_summary": "요약", '],
)
def test_parse_summary_rejects_bad_output(text):
    with pytest.raises(job_runner.LocalSummaryError):
        job_runner._parse_summary(text)


def test_parse_summary_tolerates_surrounding_text():
    ko, sev = job_runner._parse_summary('답변: {"ko_summary": "요약문", "severity": "low"} 끝')
    assert (ko, sev) == ("요약문", "low")


# ── 워커: 성공 경로 ───────────────────────────────────────

def _patch_llm_ok(monkeypatch, severity="medium"):
    from app.services.llm_adapter import LLMResult

    monkeypatch.setattr(
        job_runner, "complete",
        lambda p, t, timeout_s=None: LLMResult(
            text=json.dumps({"ko_summary": "요약", "severity": severity}, ensure_ascii=False),
            tier_used="local", model="qwen3:8b", latency_ms=5,
        ),
    )


def test_worker_success_updates_snapshot_and_event(monkeypatch):
    store = _store(rows=[
        ("FOR UPDATE SKIP LOCKED", (9, "summarize_report", {"report_id": 77}, 0)),
        ("SELECT original_text", ("프레스 원문",)),
    ])
    monkeypatch.setattr(job_runner.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))
    _patch_llm_ok(monkeypatch, severity="high")

    assert job_runner.process_once() is True

    sqls = _sqls(store)
    assert any("FOR UPDATE SKIP LOCKED" in s for s in sqls)       # 기존 패턴 준수
    assert any("status='running'" in s for s in sqls)
    upd = _params_for(store, "SET ko_summary")[0]
    assert upd == {"id": 77, "ko_summary": "요약", "severity": "high", "state": "done"}
    ev = [p for p in _params_for(store, "INSERT INTO risk_report_events")]
    assert ev[-1]["action"] == "summary_done" and ev[-1]["to_state"] == "done"
    assert any("status='done'" in s for s in sqls)


def test_worker_returns_false_on_empty_queue(monkeypatch):
    store = _store(rows=[("FOR UPDATE SKIP LOCKED", None)])
    monkeypatch.setattr(job_runner.tenancy, "connect", fake_connect(store))

    assert job_runner.process_once() is False


# ── 워커: 실패 경로 (M-08b ②) ────────────────────────────

def _fail_store(attempts: int):
    return _store(rows=[
        ("FOR UPDATE SKIP LOCKED", (9, "summarize_report", {"report_id": 77}, attempts)),
        ("SELECT original_text", ("프레스 원문",)),
    ])


def _patch_llm_fail(monkeypatch):
    from app.services.llm_adapter import LLMResult

    monkeypatch.setattr(
        job_runner, "complete",
        lambda p, t, timeout_s=None: LLMResult(
            text="", tier_used="local", model="qwen3:4b", latency_ms=1,
            error="local_failed[qwen3:8b:timeout,qwen3:4b:timeout]",
        ),
    )


@pytest.mark.parametrize("attempts", [0, 1])
def test_worker_retries_before_exhaustion(monkeypatch, attempts):
    store = _fail_store(attempts)
    monkeypatch.setattr(job_runner.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))
    _patch_llm_fail(monkeypatch)

    job_runner.process_once()

    sqls = _sqls(store)
    assert any("status='queued'" in s for s in sqls)               # 재시도 예약
    assert not any("status='failed'" in s for s in sqls)
    assert not any("summary_failed" in json.dumps(p, ensure_ascii=False, default=str)
                   for p in _params_for(store, "INSERT INTO risk_report_events"))


def test_worker_local_failed_after_3_attempts(monkeypatch, caplog):
    store = _fail_store(2)  # 이번 실패로 3회 소진
    monkeypatch.setattr(job_runner.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))
    _patch_llm_fail(monkeypatch)

    with caplog.at_level("ERROR"):
        job_runner.process_once()

    sqls = _sqls(store)
    # 잡은 failed, 보고서 처리상태는 001 정본 실패 종단값
    assert any("status='failed'" in s for s in sqls)
    state = [p for p in _params_for(store, "SET processing_state") if p["state"] == "failed"]
    assert state and state[0]["id"] == 77
    # 원문 보존 — 원문 삭제·변형 SQL 없음
    assert not any("DELETE" in s.upper() for s in sqls)
    assert not any("original_text =" in s or "original_text=" in s for s in sqls)
    # 감사 이벤트 + 관리자 알림
    ev = _params_for(store, "INSERT INTO risk_report_events")[-1]
    assert ev["action"] == "summary_failed" and ev["to_state"] == "failed"
    assert "local_failed" in ev["detail"]
    assert "admin_alert" in caplog.text and "원문 보존됨" in caplog.text


def test_worker_failure_does_not_touch_external_tier(monkeypatch):
    """외부 폴백 금지 — 워커는 tier='external' 로 어댑터를 부르지 않는다."""
    store = _fail_store(2)
    monkeypatch.setattr(job_runner.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))
    tiers = []

    from app.services.llm_adapter import LLMResult

    def _complete(prompt, tier, timeout_s=None):
        tiers.append(tier)
        return LLMResult(text="", tier_used="local", model="qwen3:4b", latency_ms=1,
                         error="local_failed[x]")

    monkeypatch.setattr(job_runner, "complete", _complete)

    job_runner.process_once()

    assert tiers == ["local"]


# ── STT 스텁 (V5) ─────────────────────────────────────────

def test_stt_branch_is_stub_and_unused():
    with pytest.raises(NotImplementedError, match="V5"):
        job_runner._transcribe_pending({"report_id": 1})


def test_stt_job_kind_is_not_reachable_from_summarize(monkeypatch):
    """summarize_report 잡은 STT 분기를 타지 않는다."""
    store = _store(rows=[
        ("FOR UPDATE SKIP LOCKED", (9, "summarize_report", {"report_id": 77}, 0)),
        ("SELECT original_text", ("원문",)),
    ])
    monkeypatch.setattr(job_runner.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(
        job_runner, "_transcribe_pending", lambda p: pytest.fail("STT 분기 진입")
    )
    _patch_llm_ok(monkeypatch)

    job_runner.process_once()
