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
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import auth as auth_service, risk_reports
from app.workers import job_runner

client = TestClient(app, client=("127.0.0.1", 50000))

CREATED_AT = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
CREATED_AT_ISO = CREATED_AT.isoformat()


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


JWT_SECRET_TEST = "test-secret-for-d4-confirm-auth"


@pytest.fixture(autouse=True)
def _base_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/test")
    monkeypatch.setenv("API_ROLE", "core")
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET_TEST)     # confirm 인증 필수(D-4 A)
    monkeypatch.delenv("TENANT_SLUG", raising=False)


def _worker_headers(wid: int = 5) -> dict:
    """D-4 A — confirm 은 보호 엔드포인트다. 유효 access 토큰을 실제로 발급해 붙인다."""
    jwt = auth_service.issue_token_pair(wid, "demo")["jwt"]
    return {"Authorization": f"Bearer {jwt}"}


# ── M-08b ①: 결정론 접수 ──────────────────────────────────

def test_intake_module_has_no_llm_dependency():
    """접수 경로는 llm_adapter 를 import 하지 않는다 — ollama 정지와 무관하게 동작."""
    assert not hasattr(risk_reports, "complete")
    assert not hasattr(risk_reports, "llm_adapter")


def test_submit_text_report_single_transaction(monkeypatch):
    store = _store(rows=[("INSERT INTO risk_reports", (77, CREATED_AT)), ("INSERT INTO jobs", (9,))])
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))

    out = risk_reports.submit_text_report("프레스 안전덮개가 열려 있습니다", lang="vi")

    assert out == {"id": 77, "status": "submitted", "created_at": CREATED_AT_ISO}
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
    store = _store(rows=[("INSERT INTO risk_reports", (78, CREATED_AT)), ("INSERT INTO jobs", (10,))])
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))

    risk_reports.submit_text_report("원문만 있음")

    assert _params_for(store, "INSERT INTO risk_reports")[0]["lang"] is None


def test_post_reports_returns_202(monkeypatch):
    store = _store(rows=[("INSERT INTO risk_reports", (81, CREATED_AT)), ("INSERT INTO jobs", (11,))])
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))

    r = client.post(
        "/api/v1/reports", json={"original_text": "컨베이어 비상정지 미작동", "lang": "vi"}
    )

    assert r.status_code == 202
    assert r.json() == {"id": 81, "status": "submitted", "created_at": CREATED_AT_ISO}


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


def test_summary_done_records_statement_clock_not_transaction_now(monkeypatch):
    """D-8 — 요약 완료 시각은 clock_timestamp()(문장 시각)다.

    now() 는 트랜잭션 시작 시각이라 process_once 의 단일 트랜잭션 안에서 도는 요약 LLM
    소요가 통째로 빠진다 — processed_at - created_at 이 0 에 수렴하는 원인.
    """
    store = _store(rows=[
        ("FOR UPDATE SKIP LOCKED", (9, "summarize_report", {"report_id": 77}, 0)),
        ("SELECT original_text", ("프레스 원문",)),
    ])
    monkeypatch.setattr(job_runner.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))
    _patch_llm_ok(monkeypatch, severity="high")

    assert job_runner.process_once() is True

    upd = [q for q in _sqls(store) if "SET ko_summary" in q][0]
    assert "processed_at = clock_timestamp()" in upd
    assert "processed_at = now()" not in upd

    ev_sql = [q for q in _sqls(store) if "INSERT INTO risk_report_events" in q][-1]
    assert "created_at" in ev_sql and "clock_timestamp()" in ev_sql   # 열 DEFAULT 의존 제거
    assert _params_for(store, "INSERT INTO risk_report_events")[-1]["action"] == "summary_done"


def test_other_event_paths_keep_column_default(monkeypatch):
    """D-8 범위 밖 — 접수 경로 이벤트는 열 DEFAULT(now()) 그대로다."""
    store = _store(rows=[("INSERT INTO risk_reports", (77, CREATED_AT)), ("INSERT INTO jobs", (9,))])
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))

    risk_reports.submit_text_report("프레스 안전덮개가 열려 있습니다", lang="vi")

    ev_sql = [q for q in _sqls(store) if "INSERT INTO risk_report_events" in q][-1]
    assert "clock_timestamp()" not in ev_sql
    assert "created_at" not in ev_sql                     # 열 목록에 없음 = DEFAULT 사용


def test_summary_failed_leaves_processed_at_null(monkeypatch):
    """무회귀 — 실패 경로는 processed_at 을 건드리지 않는다(_UPDATE_STATE)."""
    store = _fail_store(attempts=2)
    monkeypatch.setattr(job_runner.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))
    _patch_llm_fail(monkeypatch)

    assert job_runner.process_once() is True

    state_sql = [q for q in _sqls(store) if "SET processing_state" in q]
    assert state_sql and all("processed_at" not in q for q in state_sql)
    assert not any("SET ko_summary" in q for q in _sqls(store))
    ev = _params_for(store, "INSERT INTO risk_report_events")[-1]
    assert ev["action"] == "summary_failed" and ev["to_state"] == "failed"


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


# ── c6: edge → 릴레이 → core 접수 왕복 (M-08b 배선) ───────

@pytest.mark.asyncio
async def test_reports_relay_roundtrip_edge_to_core(monkeypatch):
    """근로자 앱 경로: edge POST /reports → 릴레이 pending → core 디스패치 → respond → 202."""
    import asyncio

    import httpx

    from app.main import build_app
    from app.services import relay
    from app.workers import relay_poller

    monkeypatch.setenv("API_ROLE", "edge")
    monkeypatch.setenv("RELAY_HOLD_S", "3")
    monkeypatch.setenv("RELAY_EDGE_WAIT_S", "5")
    relay.queue.reset()

    # core 측 디스패치가 쓰는 저장소는 스텁 DB 로 대체
    store = _store(rows=[("INSERT INTO risk_reports", (91, CREATED_AT)), ("INSERT INTO jobs", (12,))])
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))

    edge = build_app("edge")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=edge), base_url="http://edge"
    ) as c:
        posted = asyncio.create_task(
            c.post("/api/v1/reports", json={"original_text": "컨베이어 끼임 위험", "lang": "vi"})
        )

        pend = await c.get("/internal/relay/pending")
        items = pend.json()["items"]
        assert len(items) == 1
        assert items[0]["method"] == "POST" and items[0]["path"] == "/api/v1/reports"
        # 릴레이 payload 는 검증 완료된 모델 덤프 — source 기본값이 채워져 넘어간다
        assert items[0]["body"] == {
            "original_text": "컨베이어 끼임 위험", "lang": "vi", "source": "text",
        }

        # core 폴러의 로컬 디스패치 (HTTP 재귀 없음)
        status, payload = relay_poller.dispatch(
            items[0]["method"], items[0]["path"], items[0]["body"]
        )
        assert status == 202 and payload == {"id": 91, "status": "submitted", "created_at": CREATED_AT_ISO}

        rr = await c.post(
            f"/internal/relay/{items[0]['request_id']}/respond",
            json={"status_code": status, "body": payload},
        )
        assert rr.status_code == 200

        resp = await posted

    assert resp.status_code == 202
    assert resp.json() == {"id": 91, "status": "submitted", "created_at": CREATED_AT_ISO}

    # core 측에서 접수 3종(원문·잡·이벤트)이 한 트랜잭션으로 기록됐다
    sqls = _sqls(store)
    assert any("INSERT INTO risk_reports" in s for s in sqls)
    assert any("INSERT INTO jobs" in s for s in sqls)
    assert any("INSERT INTO risk_report_events" in s for s in sqls)
    assert store["commits"] == 1

    relay.queue.reset()


def test_relay_dispatch_supports_reports(monkeypatch):
    from app.workers import relay_poller

    store = _store(rows=[("INSERT INTO risk_reports", (92, CREATED_AT)), ("INSERT INTO jobs", (13,))])
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))

    status, body = relay_poller.dispatch(
        "POST", "/api/v1/reports", {"original_text": "원문", "lang": None}
    )

    assert status == 202
    assert body == {"id": 92, "status": "submitted", "created_at": CREATED_AT_ISO}


def test_relay_dispatch_reports_requires_post():
    from app.workers import relay_poller

    status, body = relay_poller.dispatch("GET", "/api/v1/reports", {})
    assert status == 404 and "디스패치 대상 아님" in body["detail"]


# ── M-08b ④ 계약: source · 금지 필드 · created_at ─────────

def test_source_defaults_to_text(monkeypatch):
    store = _store(rows=[("INSERT INTO risk_reports", (93, CREATED_AT)), ("INSERT INTO jobs", (14,))])
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))

    r = client.post("/api/v1/reports", json={"original_text": "원문"})

    assert r.status_code == 202
    assert _params_for(store, "INSERT INTO risk_reports")[0]["source"] == "text"


def test_source_voice_rejected_until_v5():
    """001 CHECK 집합은 수용하되 voice 는 audio 없이 성립 불가 → 501 (V5 해제)."""
    r = client.post("/api/v1/reports", json={"original_text": "원문", "source": "voice"})

    assert r.status_code == 501
    assert r.json()["detail"]["error"] == "voice_intake_not_available"


def test_source_unknown_value_is_422():
    r = client.post("/api/v1/reports", json={"original_text": "원문", "source": "sms"})
    assert r.status_code == 422


@pytest.mark.parametrize(
    "field", ["tenant", "tenant_slug", "reporter", "reporter_id", "worker_id", "status", "id"]
)
def test_forbidden_body_fields_rejected_with_400(field, monkeypatch):
    """테넌트·reporter 등 서버 도출 값은 무시가 아니라 400 거부 (M-08b ④, 위조 방지)."""
    monkeypatch.setattr(
        risk_reports.tenancy, "connect",
        lambda *a, **k: pytest.fail("거부돼야 하는데 저장소 호출됨"),
    )

    r = client.post("/api/v1/reports", json={"original_text": "원문", field: "x"})

    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["error"] == "forbidden_fields"
    assert detail["fields"] == [field]
    assert detail["allowed"] == ["lang", "original_text", "source"]


def test_created_at_present_and_iso(monkeypatch):
    store = _store(rows=[("INSERT INTO risk_reports", (94, CREATED_AT)), ("INSERT INTO jobs", (15,))])
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))

    body = client.post("/api/v1/reports", json={"original_text": "원문"}).json()

    assert set(body) == {"id", "status", "created_at"}
    assert body["created_at"] == "2026-08-29T12:00:00+00:00"
    datetime.fromisoformat(body["created_at"])  # ISO8601 파싱 가능


def test_dispatch_passes_source_through(monkeypatch):
    from app.workers import relay_poller

    store = _store(rows=[("INSERT INTO risk_reports", (95, CREATED_AT)), ("INSERT INTO jobs", (16,))])
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))

    status, body = relay_poller.dispatch(
        "POST", "/api/v1/reports", {"original_text": "원문", "lang": "vi", "source": "text"}
    )

    assert status == 202
    assert set(body) == {"id", "status", "created_at"}
    assert _params_for(store, "INSERT INTO risk_reports")[0]["source"] == "text"


# ═══ PR-2: M-08 상태머신·조회·M-08c 확인 루프 ═══════════

ADMIN_ACTOR = "admin:unauthenticated"


def _t_store(status="submitted", **kw):
    """전이용 스텁 — SELECT status FOR UPDATE 가 현재 상태를 돌려준다."""
    return _store(rows=[("SELECT status FROM risk_reports", (status,))], **kw)


# ── 전이: 정상 ────────────────────────────────────────────

def test_ack_updates_snapshot_and_event(monkeypatch):
    store = _t_store("submitted")
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))

    out = risk_reports.acknowledge(5)

    assert out == {"id": 5, "status": "acknowledged"}
    sqls = _sqls(store)
    # 스냅숏: 시각만 갱신 — acked_by 는 건드리지 않는다(M-15b 판정 1)
    ack_sql = [s for s in sqls if "acked_at = now()" in s][0]
    assert "acked_by" not in ack_sql
    # 이벤트에 행위자 단독 기록
    ev = _params_for(store, "INSERT INTO risk_report_events")[-1]
    assert ev["actor"] == ADMIN_ACTOR
    assert ev["action"] == "report_acknowledged"
    assert (ev["from_state"], ev["to_state"]) == ("submitted", "acknowledged")
    assert store["commits"] == 1


def test_resolve_updates_note_and_event(monkeypatch):
    store = _t_store("acknowledged")
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))

    out = risk_reports.resolve(5, "현장 확인 후 조치 완료")

    assert out == {"id": 5, "status": "resolved"}
    res_sql = [s for s in _sqls(store) if "resolved_at = now()" in s][0]
    assert "resolution_note" in res_sql and "resolved_by" not in res_sql
    assert _params_for(store, "resolved_at = now()")[0]["note"] == "현장 확인 후 조치 완료"
    ev = _params_for(store, "INSERT INTO risk_report_events")[-1]
    assert ev["actor"] == ADMIN_ACTOR
    assert (ev["from_state"], ev["to_state"]) == ("acknowledged", "resolved")
    assert ev["detail"] == "현장 확인 후 조치 완료"


def test_transition_never_writes_acked_by_or_resolved_by(monkeypatch):
    """M-15b 판정 1: acked_by·resolved_by 는 NULL 유지 — 어떤 UPDATE 도 이 컬럼을 쓰지 않는다."""
    cases = (("submitted", risk_reports.acknowledge), ("acknowledged", risk_reports.resolve))
    for status, fn in cases:
        store = _t_store(status)
        monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))
        fn(5)
        for sql in _sqls(store):
            if sql.strip().upper().startswith("UPDATE"):
                assert "acked_by" not in sql and "resolved_by" not in sql, sql


# ── 전이: 스킵·역행 422 ───────────────────────────────────

@pytest.mark.parametrize(
    "current,fn",
    [("submitted", risk_reports.resolve),
     ("resolved", risk_reports.acknowledge),
     ("acknowledged", risk_reports.acknowledge),
     ("resolved", risk_reports.resolve)],
)
def test_transition_rejects_skip_and_reverse(monkeypatch, current, fn):
    store = _t_store(current)
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))

    with pytest.raises(risk_reports.TransitionError):
        fn(5)
    assert not any(s.strip().upper().startswith("UPDATE") for s in _sqls(store))
    assert not any("INSERT INTO risk_report_events" in s for s in _sqls(store))


def test_transition_missing_report(monkeypatch):
    store = _store(rows=[("SELECT status FROM risk_reports", None)])
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))
    with pytest.raises(risk_reports.ReportNotFound):
        risk_reports.acknowledge(999)


def test_admin_transition_endpoints_200(monkeypatch):
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(_t_store("submitted")))
    r1 = client.post("/api/v1/admin/reports/5/ack")
    assert r1.status_code == 200 and r1.json() == {"id": 5, "status": "acknowledged"}

    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(_t_store("acknowledged")))
    r2 = client.post("/api/v1/admin/reports/5/resolve", json={"note": "완료"})
    assert r2.status_code == 200 and r2.json() == {"id": 5, "status": "resolved"}


def test_admin_transition_endpoints_422_on_skip(monkeypatch):
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(_t_store("resolved")))
    assert client.post("/api/v1/admin/reports/5/ack").status_code == 422

    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(_t_store("submitted")))
    assert client.post("/api/v1/admin/reports/5/resolve", json={"note": "n"}).status_code == 422


# ── actor 주입 지점 1개 ───────────────────────────────────

def test_admin_actor_single_injection_point():
    """admin:unauthenticated 리터럴은 상수 정의 1곳에만 존재한다(M-15b)."""
    import subprocess
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    out = subprocess.run(
        ["git", "grep", "-n", "admin:unauthenticated", "--", "backend"],
        cwd=repo_root, capture_output=True, text=True, encoding="utf-8",
    ).stdout.strip().splitlines()
    assert len(out) == 1, out
    assert out[0].startswith("backend/app/services/risk_reports.py:")
    assert "ADMIN_ACTOR_UNAUTHENTICATED" in out[0]


def test_system_actor_not_used_for_transitions(monkeypatch):
    """system 은 워커·자동 처리 규약 — 전이에 쓰지 않는다."""
    store = _t_store("submitted")
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))
    risk_reports.acknowledge(5)
    assert _params_for(store, "INSERT INTO risk_report_events")[-1]["actor"] != "system"


# ── 조회 ──────────────────────────────────────────────────

class ListCursor(FakeCursor):
    def fetchall(self):
        return self.store.get("many", [])


def _with_many(store, many):
    store["many"] = many
    return store


def test_admin_list_excludes_original_text(monkeypatch):
    store = _with_many(_store(), [(1, "요약", "high", "submitted", "done", False, CREATED_AT)])
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(FakeConn, "cursor", lambda self: ListCursor(self.store))

    rows = risk_reports.list_reports("submitted")

    assert rows == [{
        "id": 1, "ko_summary": "요약", "severity": "high", "status": "submitted",
        "processing_state": "done", "reporter_confirmed": False, "created_at": CREATED_AT_ISO,
    }]
    assert "original_text" not in rows[0]
    assert _params_for(store, "FROM risk_reports")[0]["status"] == "submitted"


def test_admin_detail_records_original_viewed(monkeypatch):
    detail_row = (1, "text", "원문", "vi", "요약", "high", "acknowledged", "done",
                  False, None, None, None, None, None, CREATED_AT, None)
    store = _with_many(
        _store(rows=[("SELECT id, source, original_text", detail_row)]),
        [(9, ADMIN_ACTOR, "original_viewed", None, None, "admin detail view", CREATED_AT)],
    )
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(FakeConn, "cursor", lambda self: ListCursor(self.store))

    detail = risk_reports.get_report_detail(1)

    assert detail["original_text"] == "원문"
    assert detail["acked_by"] is None and detail["resolved_by"] is None   # 판정 3: null 노출
    assert detail["events"][0]["action"] == "original_viewed"
    ev = _params_for(store, "INSERT INTO risk_report_events")[-1]
    assert ev["action"] == "original_viewed" and ev["actor"] == ADMIN_ACTOR
    assert not any(s.strip().upper().startswith("UPDATE") for s in _sqls(store))


def test_worker_get_report_is_five_fields_and_not_audited(monkeypatch):
    store = _store(rows=[
        ("SELECT id, status, processing_state", (1, "submitted", "queued", False, CREATED_AT)),
    ])
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))

    r = client.get("/api/v1/reports/1")

    assert r.status_code == 200
    assert set(r.json()) == {"id", "status", "processing_state", "reporter_confirmed", "created_at"}
    assert "events" not in r.json() and "original_text" not in r.json()
    assert not any("INSERT INTO risk_report_events" in s for s in _sqls(store))


def test_worker_get_report_404(monkeypatch):
    store = _store(rows=[("SELECT id, status, processing_state", None)])
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))
    assert client.get("/api/v1/reports/999").status_code == 404


# ── M-08c 확인 루프 ───────────────────────────────────────

def _confirm_store(processing_state="done", original_text="원문"):
    return _store(rows=[
        ("SELECT processing_state, original_text", (processing_state, original_text)),
        ("INSERT INTO jobs", (77,)),
    ])


def test_confirm_confirmed_sets_snapshot_and_event(monkeypatch):
    store = _confirm_store()
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))

    out = risk_reports.confirm(1, "confirmed", worker_id=41)

    assert out == {"id": 1, "result": "confirmed", "reporter_confirmed": True}
    assert any("SET reporter_confirmed = true" in s for s in _sqls(store))
    ev = _params_for(store, "INSERT INTO risk_report_events")[-1]
    assert ev["action"] == "reporter_confirmed" and ev["actor"] == "worker:41"


def test_confirm_corrected_records_event_and_requeues(monkeypatch):
    store = _confirm_store()
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))

    out = risk_reports.confirm(1, "corrected", "정정된 요약", worker_id=41)

    assert out["result"] == "corrected" and out["requeued_job_id"] == 77
    ev = _params_for(store, "INSERT INTO risk_report_events")[-1]
    assert ev["action"] == "reporter_corrected" and ev["detail"] == "정정된 요약"
    job = _params_for(store, "INSERT INTO jobs")[0]
    assert json.loads(job["payload"]) == {"report_id": 1, "reason": "reporter_corrected"}
    assert not any("SET reporter_confirmed" in s for s in _sqls(store))


def test_confirm_on_local_failed_echoes_original_only(monkeypatch):
    """M-08c ③ — 상태 변경·이벤트 없이 원문 에코 + 접수 안내."""
    store = _confirm_store(processing_state="failed")
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))

    out = risk_reports.confirm(1, "confirmed", worker_id=41)

    assert out["result"] == "local_failed" and out["original_text"] == "원문"
    assert "접수" in out["message"]
    assert not any("INSERT INTO risk_report_events" in s for s in _sqls(store))
    assert not any(s.strip().upper().startswith("UPDATE") for s in _sqls(store))


def test_confirm_endpoint_requires_authentication(monkeypatch):
    """D-4 A — 미인증 confirm 은 401. 이벤트도 남기지 않는다(반전, 전 규약은 200 허용)."""
    store = _confirm_store()
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))

    r = client.post("/api/v1/reports/1/confirm", json={"result": "confirmed"})

    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate") == "Bearer"
    assert not any("INSERT INTO risk_report_events" in q for q in _sqls(store))
    assert store["commits"] == 0


# 헤더 값은 ASCII 만 — httpx 가 비ASCII 헤더를 인코딩 단계에서 거부한다(제품 규약 무관).
@pytest.mark.parametrize("header", [None, "", "Token abc", "Bearer ", "Bearer not.a.jwt"])
def test_confirm_rejects_missing_or_bad_bearer(header, monkeypatch):
    """헤더 부재·접두 오류·위조 전부 401 — require_worker 현행 규약 그대로."""
    store = _confirm_store()
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))
    headers = {} if header is None else {"Authorization": header}

    r = client.post("/api/v1/reports/1/confirm", json={"result": "confirmed"}, headers=headers)

    assert r.status_code == 401
    assert not any("INSERT INTO risk_report_events" in q for q in _sqls(store))


def test_confirm_relay_path_rejects_missing_identity(monkeypatch):
    """릴레이는 라우터를 거치지 않는다 — identity None 이면 core 가 401 로 끊는다."""
    from app.workers import relay_poller

    store = _confirm_store()
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))

    status, body = relay_poller.dispatch(
        "POST", "/api/v1/reports/1/confirm", {"result": "confirmed"}, identity=None
    )

    assert status == 401
    assert body == {"detail": auth_service.AUTH_FAILED_MESSAGE}      # 사유 무구분
    assert not any("INSERT INTO risk_report_events" in q for q in _sqls(store))


def test_confirm_dispatch_consumes_identity(monkeypatch):
    from app.workers import relay_poller

    store = _confirm_store()
    monkeypatch.setattr(risk_reports.tenancy, "connect", fake_connect(store))

    status, body = relay_poller.dispatch(
        "POST", "/api/v1/reports/1/confirm", {"result": "confirmed"}, None, {"wid": 41}
    )

    assert status == 200 and body["result"] == "confirmed"
    assert _params_for(store, "INSERT INTO risk_report_events")[-1]["actor"] == "worker:41"


def test_confirm_rejects_unknown_result():
    r = client.post(
        "/api/v1/reports/1/confirm", json={"result": "maybe"}, headers=_worker_headers()
    )
    assert r.status_code == 422                       # 인증 통과 후 본문 검증에서 걸린다


# ── 신원 본문 400 (M-08b ④ — 전이·confirm 전부) ──────────

@pytest.mark.parametrize(
    "field", ["worker_id", "admin_id", "actor", "acked_by", "resolved_by", "status"]
)
def test_identity_fields_rejected_on_transition_and_confirm(field, monkeypatch):
    def _boom(*a, **k):
        pytest.fail("거부돼야 하는데 저장소 호출됨")

    monkeypatch.setattr(risk_reports.tenancy, "connect", _boom)
    cases = (
        ("/api/v1/admin/reports/5/ack", {field: 1}),
        ("/api/v1/admin/reports/5/resolve", {"note": "n", field: 1}),
        ("/api/v1/reports/1/confirm", {"result": "confirmed", field: 1}),
    )
    for path, body in cases:
        # confirm 은 D-4 A 로 인증 필수 — 인증을 통과시킨 뒤에도 400 가드가 걸리는지 본다.
        headers = _worker_headers() if path.endswith("/confirm") else {}
        r = client.post(path, json=body, headers=headers)
        assert r.status_code == 400, (path, r.status_code)
        assert r.json()["detail"]["error"] == "forbidden_fields"
        assert field in r.json()["detail"]["fields"]
