"""M-41 — 문서 업로드·자동 적재 백엔드. [새봄]

검증 대상 계약:
- POST /admin/documents {title, category, text, filename?} → 202 {id, job_id}
  documents(origin='upload', source='upload:'+filename, 부재 시 'upload:direct') 1행 +
  jobs(kind='ingest_document', payload={document_id, text}) 1행
- 422 2종: text 빈 값 / category 4종('process','instruction','safety','equipment') 밖
- JSON 본문만 — multipart·신규 의존성 없음

fake cursor(needle) — 네트워크·DB·임베딩 실호출 없음.
"""

import json as _json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import documents

client = TestClient(app, client=("127.0.0.1", 50000))


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
        return None

    def fetchall(self):
        for needle, value in self.store.get("many", []):
            if needle in self._last:
                return value
        return []


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
        yield FakeConn(store)

    return _connect


def _store(**kw):
    base = {"calls": [], "rows": [], "many": [], "commits": 0}
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


GOOD = {"title": "선반 점검 절차", "category": "instruction",
        "text": "## 점검\n\n시동 전 척 조임을 확인한다.", "filename": "lathe.md"}


def _upload_store():
    return _store(rows=[("INSERT INTO documents", (31,)), ("INSERT INTO jobs", (77,))])


# ── POST 202 — documents·jobs 행 생성 ─────────────────────

def test_upload_returns_202_with_ids(monkeypatch):
    store = _upload_store()
    monkeypatch.setattr(documents.tenancy, "connect", fake_connect(store))

    r = client.post("/api/v1/admin/documents", json=GOOD)

    assert r.status_code == 202, r.text
    assert r.json() == {"id": 31, "job_id": 77}
    assert store["commits"] == 1

    d = _params_for(store, "INSERT INTO documents")[0]
    assert d == {"title": "선반 점검 절차", "category": "instruction", "source": "upload:lathe.md"}
    sql = [s for s in _sqls(store) if "INSERT INTO documents" in s][0]
    assert "'upload'" in sql                                   # origin 고정값
    j = _params_for(store, "INSERT INTO jobs")[0]
    assert j["kind"] == "ingest_document"
    assert _json.loads(j["payload"]) == {"document_id": 31, "text": GOOD["text"]}  # 원문 무변형


def test_upload_without_filename_uses_direct_source(monkeypatch):
    """filename 부재 시 source='upload:direct' (계약 외 — 자결값)."""
    store = _upload_store()
    monkeypatch.setattr(documents.tenancy, "connect", fake_connect(store))

    r = client.post("/api/v1/admin/documents",
                    json={k: v for k, v in GOOD.items() if k != "filename"})

    assert r.status_code == 202
    assert _params_for(store, "INSERT INTO documents")[0]["source"] == "upload:direct"


# ── 422 2종 — 저장소 무호출 ───────────────────────────────

@pytest.mark.parametrize("bad", [
    {**GOOD, "text": ""},
    {**GOOD, "text": "   \n  "},
    {**GOOD, "category": "general"},          # 4종 밖
    {**GOOD, "category": "SAFETY"},           # 대소문자 불일치도 이탈
])
def test_upload_invalid_422_no_db(monkeypatch, bad):
    def _boom(*a, **k):
        pytest.fail("검증 실패인데 저장소를 호출했다")

    monkeypatch.setattr(documents.tenancy, "connect", _boom)

    assert client.post("/api/v1/admin/documents", json=bad).status_code == 422


@pytest.mark.parametrize("category", documents.CATEGORY_VALUES)
def test_upload_all_four_categories_accepted(monkeypatch, category):
    store = _upload_store()
    monkeypatch.setattr(documents.tenancy, "connect", fake_connect(store))

    r = client.post("/api/v1/admin/documents", json={**GOOD, "category": category})

    assert r.status_code == 202, r.text


def test_category_values_match_001_check():
    assert documents.CATEGORY_VALUES == ("process", "instruction", "safety", "equipment")


def test_identity_field_in_body_returns_400(monkeypatch):
    """M-08b ④ 동형 가드 — 관리자 POST 공통."""
    def _boom(*a, **k):
        pytest.fail("가드가 400 을 내야 하는데 저장소를 호출했다")

    monkeypatch.setattr(documents.tenancy, "connect", _boom)
    r = client.post("/api/v1/admin/documents", json={**GOOD, "actor": "admin:1"})

    assert r.status_code == 400, r.text
    assert r.json()["detail"]["fields"] == ["actor"]


# ══ ② 청킹 — split_document (빈 줄·마크다운 제목 경계, 800자 이하) ══

def test_split_blank_line_and_heading_boundaries():
    text = "## 1장\n첫 문단이다.\n\n둘째 문단이다.\n### 1.1\n셋째 문단이다."
    parts = documents.split_document(text)

    assert parts == ["## 1장\n첫 문단이다.", "둘째 문단이다.", "### 1.1\n셋째 문단이다."]
    assert all(len(p) <= documents.CHUNK_MAX_CHARS for p in parts)


def test_split_short_text_single_chunk():
    parts = documents.split_document("한 문단짜리 짧은 본문.")
    assert parts == ["한 문단짜리 짧은 본문."]          # 최소 1개 보장


def test_split_oversize_block_line_boundary():
    """800자 초과 블록 — 줄 경계 누적 분할, 전 청크 ≤800."""
    line = "가" * 300
    text = "\n".join([line] * 4)                       # 한 블록 1203자
    parts = documents.split_document(text)

    assert len(parts) == 2
    assert all(len(p) <= documents.CHUNK_MAX_CHARS for p in parts)
    assert "".join(parts).replace("\n", "") == "가" * 1200   # 내용 소실 없음


def test_split_single_long_line_hard_cut():
    """줄바꿈 없는 초장문 — 800자 고정 절단(자결)."""
    parts = documents.split_document("나" * 1700)

    assert [len(p) for p in parts] == [800, 800, 100]
    assert "".join(parts) == "나" * 1700


# ══ ② 잡 핸들러 — _handle_ingest_document ══════════════════

from app.workers import job_runner

DOC_TEXT = "## 점검\n시동 전 척 조임 확인.\n\n방호덮개 상태를 확인한다."   # 청크 2개 본문


def _fake_vec(n):
    return [[0.1, 0.2, 0.3]] * n


def test_handler_chunks_embeds_and_inserts(monkeypatch):
    seen = {}

    def fake_embed(texts):
        seen["texts"] = list(texts)
        return _fake_vec(len(texts))

    monkeypatch.setattr(job_runner, "embed", fake_embed)
    store = _store(rows=[("SELECT category FROM documents", ("instruction",))])
    cur = FakeCursor(store)

    job_runner._handle_ingest_document(
        cur, {"id": 77, "payload": {"document_id": 31, "text": DOC_TEXT}, "attempts": 0}
    )

    parts = documents.split_document(DOC_TEXT)
    assert len(parts) >= 2                                     # 계약 지정 — n ≥ 2 본문
    assert seen["texts"] == parts                              # 배치 임베딩 1회
    ins = _params_for(store, "INSERT INTO chunks")
    assert len(ins) == len(parts)
    assert [p["chunk_idx"] for p in ins] == list(range(len(parts)))   # 0 부터
    assert [p["content"] for p in ins] == parts
    for p in ins:
        assert _json.loads(p["meta"]) == {
            "category": "instruction", "origin": "upload", "draft": False,
        }                                                      # 계약 3키 고정


def test_handler_missing_document_raises(monkeypatch):
    monkeypatch.setattr(job_runner, "embed",
                        lambda texts: pytest.fail("문서가 없는데 임베딩을 호출했다"))
    store = _store(rows=[("SELECT category FROM documents", None)])

    with pytest.raises(job_runner.IngestDocumentError):
        job_runner._handle_ingest_document(
            FakeCursor(store), {"id": 77, "payload": {"document_id": 999, "text": "x"}, "attempts": 0}
        )
    assert not any("INSERT INTO chunks" in s for s in _sqls(store))


def test_handler_empty_text_raises():
    with pytest.raises(job_runner.IngestDocumentError):
        job_runner._handle_ingest_document(
            FakeCursor(_store()), {"id": 77, "payload": {"document_id": 31, "text": "  "}, "attempts": 0}
        )


def test_process_once_dispatches_ingest_document(monkeypatch):
    """kind 배선 — 성공 시 기존 done 처리 그대로."""
    monkeypatch.setattr(job_runner, "embed", lambda texts: _fake_vec(len(texts)))
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/test")
    store = _store(rows=[
        ("FOR UPDATE SKIP LOCKED", (77, "ingest_document", {"document_id": 31, "text": DOC_TEXT}, 0)),
        ("SELECT category FROM documents", ("safety",)),
    ])
    monkeypatch.setattr(job_runner.tenancy, "connect", fake_connect(store))

    assert job_runner.process_once() is True

    assert any("status='done'" in s for s in _sqls(store))     # 기존 done 경로
    assert len(_params_for(store, "INSERT INTO chunks")) == len(documents.split_document(DOC_TEXT))


def test_list_documents_fields_order_and_join(monkeypatch):
    """③ GET — 8필드·최신순(id DESC 질의)·chunk_count·job_status 조인, 잡 없는 문서 null."""
    import datetime as _dt

    at = _dt.datetime(2026, 9, 2, 9, 0, tzinfo=_dt.timezone.utc)
    store = _store(many=[("FROM documents d", [
        (31, "선반 점검 절차", "instruction", "upload", "upload:lathe.md", at, 3, "done"),
        (2, "PR-120 크랭크 프레스 작업 매뉴얼", "equipment", "seed",
         "data/seed/manuals/press_manual.md", at, 42, None),
    ])])
    monkeypatch.setattr(documents.tenancy, "connect", fake_connect(store))

    r = client.get("/api/v1/admin/documents")

    assert r.status_code == 200, r.text
    body = r.json()
    assert [tuple(row) for row in body] == [documents.LIST_KEYS] * 2   # 8필드·키 순서
    assert body[0]["id"] == 31 and body[0]["job_status"] == "done"
    assert body[0]["chunk_count"] == 3
    assert body[1]["job_status"] is None                   # 잡 없는 기존 문서 — null(자결)
    assert body[0]["created_at"] == "2026-09-02T09:00:00+00:00"

    sql = [s for s in _sqls(store) if "FROM documents d" in s][0]
    assert "ORDER BY d.id DESC" in sql                     # 최신순
    assert "count(*) FROM chunks" in sql                   # chunk_count 조인
    assert "kind = 'ingest_document'" in sql               # job_status 조인(해당 잡 최신)
    assert "ORDER BY j.id DESC LIMIT 1" in sql


def test_list_documents_read_only(monkeypatch):
    store = _store(many=[("FROM documents d", [])])
    monkeypatch.setattr(documents.tenancy, "connect", fake_connect(store))

    assert client.get("/api/v1/admin/documents").json() == []
    for sql, _ in store["calls"]:
        assert sql.strip().split()[0].upper() == "SELECT", sql
    assert store["commits"] == 0


def test_process_once_failure_uses_existing_retry(monkeypatch):
    """실패 시 기존 _fail_job 경로 그대로 — attempts 1 재시도."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/test")
    store = _store(rows=[
        ("FOR UPDATE SKIP LOCKED", (77, "ingest_document", {"document_id": 999, "text": "x"}, 0)),
        ("SELECT category FROM documents", None),              # 문서 없음 → 예외
    ])
    monkeypatch.setattr(job_runner.tenancy, "connect", fake_connect(store))

    assert job_runner.process_once() is True

    retry = _params_for(store, "SET status='queued'")
    assert retry and retry[0]["attempts"] == 1                 # 기존 백오프 재시도
    assert not any("status='done'" in s for s in _sqls(store))
