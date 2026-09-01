"""M-05a — POST /admin/unanswered/{id}/answer + ingest_answer job. [새봄]

검증 대상 계약:
- 전이: open → answered 1회(FOR UPDATE), admin_answer·answered_at 갱신,
  answered_by(integer FK)는 NULL 유지(M-15b)
- jobs kind='ingest_answer' 1행 적재 → 응답 {id, status, answered_at, ingest_job_id}
- admin_events 1행(M-08d): action='unanswered_answered', target_type='unanswered',
  target_id=question_id, actor = M-15b 단일 주입 지점
- 라우터 404/422/200 · edge 는 M-28c 릴레이 경유 · 폴러 디스패치
- 적재: documents(origin='admin_answer') + chunks(meta category 'general'·draft false)
  + unanswered_queue.ingested_doc_id 갱신, 임베딩 1024 (M-02)
- 3중 대조: §3 등재 문안 ↔ 구현

네트워크·LLM 실호출 없음 — embed 는 mock.
"""

import asyncio
import io
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app, build_app
from app.services import approval, relay
from app.workers import job_runner, relay_poller

client = TestClient(app, client=("127.0.0.1", 50000))

AT = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
AT_ISO = AT.isoformat()

QUESTION_ID = 41
QUEUE_ID = 3
JOB_ID = 88
DOC_ID = 101
ANSWER = "프레스 일상 점검은 매 8시간마다 실시합니다."


class Cursor:
    """SQL 조각 → fetchone 값 매핑 (approval/job_runner 는 fetchone 만 쓴다)."""

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


def _store(returns):
    return {"calls": [], "returns": returns, "commits": 0, "connects": 0}


def _transition_store(status="open"):
    return _store([
        ("FROM unanswered_queue WHERE question_id", (QUEUE_ID, status)),
        ("RETURNING answered_at", (AT,)),
        ("INSERT INTO jobs", (JOB_ID,)),
    ])


def _patch(monkeypatch, store):
    monkeypatch.setattr(approval.tenancy, "connect", fake_connect(store))


def _sqls(store):
    return [c[0] for c in store["calls"]]


def _event(store):
    return [c[1] for c in store["calls"] if "INSERT INTO admin_events" in c[0]][0]


@pytest.fixture(autouse=True)
def _base_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/test")
    monkeypatch.setenv("API_ROLE", "core")
    relay.queue.reset()
    yield
    relay.queue.reset()


# ── 전이 ──────────────────────────────────────────────────

def test_answer_transitions_and_queues_job(monkeypatch):
    store = _transition_store()
    _patch(monkeypatch, store)

    out = approval.answer_unanswered(QUESTION_ID, ANSWER)

    assert out == {
        "id": QUEUE_ID, "status": "answered",
        "answered_at": AT_ISO, "ingest_job_id": JOB_ID,
    }
    sqls = _sqls(store)
    assert "FOR UPDATE" in sqls[0]
    up = [s for s in sqls if s.strip().upper().startswith("UPDATE")][0]
    assert "admin_answer" in up and "answered_at = now()" in up
    assert "answered_by" not in up            # M-15b — integer FK 는 NULL 유지
    job = [c[1] for c in store["calls"] if "INSERT INTO jobs" in c[0]][0]
    assert job["kind"] == "ingest_answer" == approval.JOB_KIND_INGEST_ANSWER
    assert '"question_id": 41' in job["payload"] and '"unanswered_id": 3' in job["payload"]
    assert store["commits"] == 1


def test_answer_records_admin_event(monkeypatch):
    store = _transition_store()
    _patch(monkeypatch, store)

    approval.answer_unanswered(QUESTION_ID, ANSWER)

    ev = _event(store)
    assert ev["action"] == "unanswered_answered" == approval.EV_UNANSWERED_ANSWERED
    assert ev["target_type"] == "unanswered" == approval.TARGET_UNANSWERED
    assert ev["target_id"] == QUESTION_ID          # 총괄 확정 — queue id 아님
    assert (ev["from_state"], ev["to_state"]) == ("open", "answered")
    # M-15b 단일 주입 지점 재사용 — 새 리터럴 금지
    assert ev["actor"] == approval.ADMIN_ACTOR_UNAUTHENTICATED == "admin:unauthenticated"
    assert ev["detail"] == '{"ingested_doc_id": null, "text_len": %d}' % len(ANSWER)


def test_answer_only_from_open(monkeypatch):
    store = _transition_store("answered")
    _patch(monkeypatch, store)

    with pytest.raises(approval.TransitionError):
        approval.answer_unanswered(QUESTION_ID, ANSWER)
    assert not any(s.strip().upper().startswith("UPDATE") for s in _sqls(store))
    assert not any("INSERT INTO admin_events" in s for s in _sqls(store))
    assert not any("INSERT INTO jobs" in s for s in _sqls(store))


def test_answer_missing_target(monkeypatch):
    store = _store([("FROM unanswered_queue WHERE question_id", None)])
    _patch(monkeypatch, store)
    with pytest.raises(approval.UnansweredNotFound):
        approval.answer_unanswered(999, ANSWER)


@pytest.mark.parametrize("bad", [None, "", "   ", "\n\t"])
def test_answer_requires_text(monkeypatch, bad):
    store = _transition_store()
    _patch(monkeypatch, store)
    with pytest.raises(approval.InvalidAnswer):
        approval.answer_unanswered(QUESTION_ID, bad)
    assert store["connects"] == 0            # DB 를 열기 전에 막는다


# ── 라우터 ────────────────────────────────────────────────

def test_endpoint_returns_contract_keys(monkeypatch):
    store = _transition_store()
    _patch(monkeypatch, store)
    r = client.post(f"/api/v1/admin/unanswered/{QUESTION_ID}/answer", json={"text": ANSWER})
    assert r.status_code == 200
    assert r.json() == {
        "id": QUEUE_ID, "status": "answered",
        "answered_at": AT_ISO, "ingest_job_id": JOB_ID,
    }


def test_endpoint_404_when_missing(monkeypatch):
    store = _store([("FROM unanswered_queue WHERE question_id", None)])
    _patch(monkeypatch, store)
    r = client.post("/api/v1/admin/unanswered/999/answer", json={"text": ANSWER})
    assert r.status_code == 404


def test_endpoint_422_when_not_open(monkeypatch):
    store = _transition_store("answered")
    _patch(monkeypatch, store)
    r = client.post(f"/api/v1/admin/unanswered/{QUESTION_ID}/answer", json={"text": ANSWER})
    assert r.status_code == 422


@pytest.mark.parametrize("body", [{}, {"text": ""}, {"text": "   "}])
def test_endpoint_422_when_text_missing_or_blank(monkeypatch, body):
    store = _transition_store()
    _patch(monkeypatch, store)
    r = client.post(f"/api/v1/admin/unanswered/{QUESTION_ID}/answer", json=body)
    assert r.status_code == 422


def test_endpoint_rejects_identity_fields(monkeypatch):
    """M-08b ④ — 행위자·상태는 서버가 결정한다."""
    store = _transition_store()
    _patch(monkeypatch, store)
    r = client.post(
        f"/api/v1/admin/unanswered/{QUESTION_ID}/answer",
        json={"text": ANSWER, "actor": "admin:1"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_edge_role_relays(monkeypatch):
    """M-28c — edge 는 DB 자격이 없다. 릴레이 큐 경유로 core 회신을 그대로 투과한다."""
    monkeypatch.setenv("API_ROLE", "edge")
    monkeypatch.setenv("RELAY_HOLD_S", "3")
    monkeypatch.setenv("RELAY_EDGE_WAIT_S", "5")

    def _boom(*a, **kw):
        raise AssertionError("edge 에서 저장소를 직접 호출하면 안 된다")

    monkeypatch.setattr(approval, "answer_unanswered", _boom)
    app_edge = build_app("edge")
    payload = {"id": QUEUE_ID, "status": "answered",
               "answered_at": AT_ISO, "ingest_job_id": JOB_ID}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_edge), base_url="http://edge"
    ) as c:
        task = asyncio.create_task(
            c.post(f"/api/v1/admin/unanswered/{QUESTION_ID}/answer", json={"text": ANSWER})
        )
        pend = await c.get("/internal/relay/pending")
        items = pend.json()["items"]
        assert len(items) == 1
        assert items[0]["method"] == "POST"
        assert items[0]["path"] == f"/api/v1/admin/unanswered/{QUESTION_ID}/answer"
        assert items[0]["body"] == {"text": ANSWER}
        await c.post(f"/internal/relay/{items[0]['request_id']}/respond",
                     json={"status_code": 200, "body": payload})
        r = await task

    assert r.status_code == 200 and r.json() == payload


# ── 폴러 디스패치 ─────────────────────────────────────────

def test_poller_dispatches_answer(monkeypatch):
    seen = {}

    def _fn(question_id, text):
        seen.update(question_id=question_id, text=text)
        return {"id": QUEUE_ID, "status": "answered", "answered_at": AT_ISO,
                "ingest_job_id": JOB_ID}

    monkeypatch.setattr("app.services.approval.answer_unanswered", _fn)
    status, body = relay_poller.dispatch(
        "POST", f"/api/v1/admin/unanswered/{QUESTION_ID}/answer", {"text": ANSWER}
    )
    assert status == 200 and body["ingest_job_id"] == JOB_ID
    assert seen == {"question_id": QUESTION_ID, "text": ANSWER}


@pytest.mark.parametrize(
    "exc,expected",
    [(approval.UnansweredNotFound, 404), (approval.TransitionError, 422),
     (approval.InvalidAnswer, 422)],
)
def test_poller_maps_errors(monkeypatch, exc, expected):
    def _fn(question_id, text):
        raise exc("boom")

    monkeypatch.setattr("app.services.approval.answer_unanswered", _fn)
    status, _ = relay_poller.dispatch(
        "POST", f"/api/v1/admin/unanswered/{QUESTION_ID}/answer", {"text": ANSWER}
    )
    assert status == expected


# ── 적재 job ──────────────────────────────────────────────

VEC = [0.01] * 1024


def _ingest_store():
    return _store([
        ("SELECT question FROM questions", ("프레스 점검 주기는?",)),
        ("INSERT INTO documents", (DOC_ID,)),
    ])


def _job():
    return {"id": JOB_ID, "kind": "ingest_answer", "attempts": 0,
            "payload": {"unanswered_id": QUEUE_ID, "question_id": QUESTION_ID, "text": ANSWER}}


def test_ingest_inserts_document_and_chunk(monkeypatch):
    monkeypatch.setattr(job_runner, "embed", lambda texts: [VEC])
    store = _ingest_store()
    job_runner._handle_ingest_answer(Cursor(store), _job())

    doc = [c[1] for c in store["calls"] if "INSERT INTO documents" in c[0]][0]
    doc_sql = [c[0] for c in store["calls"] if "INSERT INTO documents" in c[0]][0]
    assert "'admin_answer'" in doc_sql          # 001:31 CHECK 값
    assert "NULL" in doc_sql                   # category 는 001 CHECK 4값에 general 이 없다
    assert doc["title"].startswith("관리자 답변") and doc["source"] == f"unanswered:{QUEUE_ID}"

    chunk = [c[1] for c in store["calls"] if "INSERT INTO chunks" in c[0]][0]
    assert chunk["document_id"] == DOC_ID and chunk["content"] == ANSWER
    assert chunk["embedding"].startswith("[") and chunk["embedding"].count(",") == 1023
    assert '"category": "general"' in chunk["meta"] and '"draft": false' in chunk["meta"]
    assert '"role"' not in chunk["meta"]        # M-29a 배제 대상이 아니다


def test_ingest_updates_ingested_doc_id(monkeypatch):
    monkeypatch.setattr(job_runner, "embed", lambda texts: [VEC])
    store = _ingest_store()
    job_runner._handle_ingest_answer(Cursor(store), _job())
    upd = [c for c in store["calls"] if "ingested_doc_id" in c[0]][0]
    assert upd[1] == {"doc_id": DOC_ID, "id": QUEUE_ID}


@pytest.mark.parametrize(
    "payload",
    [{"unanswered_id": QUEUE_ID, "question_id": QUESTION_ID, "text": "  "},
     {"unanswered_id": QUEUE_ID, "text": ANSWER}],
)
def test_ingest_rejects_bad_payload(monkeypatch, payload):
    monkeypatch.setattr(job_runner, "embed", lambda texts: [VEC])
    store = _ingest_store()
    job = _job()
    job["payload"] = payload
    with pytest.raises(job_runner.IngestAnswerError):
        job_runner._handle_ingest_answer(Cursor(store), job)


def test_job_dispatch_routes_ingest_answer(monkeypatch):
    """kind 디스패치가 ingest_answer 를 잡는다 — 미지원 kind 로 실패하지 않는다."""
    seen = {}
    monkeypatch.setattr(job_runner, "_handle_ingest_answer",
                        lambda cur, job: seen.update(kind=job["kind"]))
    store = _store([("FROM jobs", (JOB_ID, "ingest_answer", _job()["payload"], 0))])
    monkeypatch.setattr(job_runner.tenancy, "connect", fake_connect(store))

    assert job_runner.process_once() is True
    assert seen == {"kind": "ingest_answer"}
    assert any("status='done'" in c[0] for c in store["calls"])


# ── 3중 대조 ──────────────────────────────────────────────

def test_skeleton_line_matches_implementation():
    root = Path(__file__).resolve().parents[1]
    text = io.open(root / "docs/skeleton-v3.md", encoding="utf-8").read()
    lines = [l for l in text.split("\n") if l.startswith("POST /admin/unanswered/")]
    assert len(lines) == 1, lines
    line = lines[0]
    for token in ("{text}", "status:'answered'", "answered_at", "ingest_job_id",
                  "admin_answer", "general"):
        assert token in line, token
