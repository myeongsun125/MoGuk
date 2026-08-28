"""V2-2 RAG /ask 단위 테스트 — 네트워크·DB 없음(전부 mock/스텁). [새봄]

검증 대상 계약:
- skeleton-v3 §3: POST /ask {question, lang} → {answer, sources[], verify:{score,passed,gated}, trace_id}
- skeleton-v3 §4 동결: retrieve(query, k=4, meta_filter=None) / embed(texts) -> 1024차원
- M-02a: 임베딩 런타임 = ollama /api/embed 단일, 모델 EMBED_MODEL(기본 bge-m3)
- M-05 / BLUEPRINT §4-1: grounded=false → 답변 차단 + unanswered_queue insert(status='open')
- M-09: questions.trace 에 classify → retrieve(hit·score) → route.tier → verify 기록
- M-17·M-30: /ask 는 tier="local", timeout_s=None 으로 어댑터를 호출한다

실데이터 E2E(마이그레이션 적용·chunks 적재·ollama 모델)는 보류 — 여기서는 DB·ollama 를 스텁으로 대체.
"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agents import graph, retrieve as retrieve_mod
from app.agents.retrieve import Chunk, retrieve, to_vector_literal
from app.main import app
from app.services import llm_adapter, tenancy

client = TestClient(app)


# ── 가짜 DB (psycopg 커넥션 최소 인터페이스) ───────────────────

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

    def fetchall(self):
        return self.store.get("rows", [])

    def fetchone(self):
        return (self.store.get("question_id", 101),)


class FakeConn:
    def __init__(self, store):
        self.store = store

    def cursor(self):
        return FakeCursor(self.store)

    def commit(self):
        self.store["committed"] = True


def fake_connect(store):
    from contextlib import contextmanager

    @contextmanager
    def _connect(slug=None):
        store["connects"] = store.get("connects", 0) + 1
        yield FakeConn(store)

    return _connect


def _store(**kw):
    base = {"calls": [], "rows": [], "committed": False}
    base.update(kw)
    return base


def _vec(dim=1024, value=0.1):
    return [value] * dim


def _chunk(i=1, category="safety", title="프레스 작업 안전수칙"):
    return Chunk(
        id=10 + i,
        document_id=i,
        content=f"프레스 작업 전 비상정지 버튼과 안전덮개를 확인한다. ({i})",
        meta={"category": category},
        score=0.9 - i * 0.01,
        title=title,
        category=category,
    )


@pytest.fixture(autouse=True)
def _base_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/test")
    monkeypatch.delenv("EMBED_MODEL", raising=False)
    monkeypatch.delenv("TENANT_SLUG", raising=False)


# ── embed() — M-02a ───────────────────────────────────────

def _embed_response(vectors):
    request = httpx.Request("POST", "http://127.0.0.1:1/api/embed")
    return httpx.Response(200, json={"embeddings": vectors}, request=request)


def test_embed_uses_ollama_api_embed_with_bge_m3(monkeypatch):
    seen = {}

    def _post(url, json=None, timeout=None, **kwargs):
        seen.update(url=url, json=json, timeout=timeout)
        return _embed_response([_vec()])

    monkeypatch.setattr(llm_adapter.httpx, "post", _post)

    out = llm_adapter.embed(["프레스 안전"])

    assert seen["url"] == "http://127.0.0.1:1/api/embed"
    assert seen["json"]["model"] == "bge-m3"
    assert seen["json"]["input"] == ["프레스 안전"]
    assert seen["timeout"] == 25.0  # LLM_TIMEOUT_LOCAL_S (M-30)
    assert len(out) == 1 and len(out[0]) == 1024


def test_embed_model_override(monkeypatch):
    monkeypatch.setenv("EMBED_MODEL", "bge-m3:latest")
    seen = {}
    monkeypatch.setattr(
        llm_adapter.httpx,
        "post",
        lambda url, json=None, timeout=None, **k: (seen.update(json=json), _embed_response([_vec()]))[1],
    )
    llm_adapter.embed(["q"])
    assert seen["json"]["model"] == "bge-m3:latest"


def test_embed_rejects_wrong_dimension(monkeypatch):
    monkeypatch.setattr(
        llm_adapter.httpx, "post", lambda *a, **k: _embed_response([_vec(dim=768)])
    )
    with pytest.raises(ValueError, match="차원 불일치"):
        llm_adapter.embed(["q"])


def test_embed_rejects_count_mismatch(monkeypatch):
    monkeypatch.setattr(llm_adapter.httpx, "post", lambda *a, **k: _embed_response([_vec()]))
    with pytest.raises(ValueError, match="벡터"):
        llm_adapter.embed(["a", "b"])


def test_embed_empty_input_skips_call(monkeypatch):
    monkeypatch.setattr(
        llm_adapter.httpx, "post", lambda *a, **k: pytest.fail("빈 입력인데 호출됨")
    )
    assert llm_adapter.embed([]) == []


# ── retrieve() — skeleton §4 동결 ─────────────────────────

def test_retrieve_signature_is_frozen():
    import inspect

    sig = inspect.signature(retrieve)
    assert list(sig.parameters) == ["query", "k", "meta_filter"]
    assert sig.parameters["k"].default == 4
    assert sig.parameters["meta_filter"].default is None


def test_retrieve_top_k_and_source_shape(monkeypatch):
    store = _store(
        rows=[
            (11, 1, "본문 1", {"category": "safety"}, "프레스 안전수칙", "safety", 0.93),
            (12, 2, "본문 2", {"category": "process"}, "공정 지시서", "process", 0.81),
        ]
    )
    monkeypatch.setattr(retrieve_mod.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(retrieve_mod, "embed", lambda texts: [_vec()])

    chunks = retrieve("프레스 점검", k=2)

    assert [c.id for c in chunks] == [11, 12]
    assert chunks[0].as_source() == {
        "document_id": 1,
        "chunk_id": 11,
        "title": "프레스 안전수칙",
        "category": "safety",
    }
    sql, params = store["calls"][0]
    assert params["k"] == 2
    assert params["meta"] is None
    assert params["vec"].startswith("[") and params["vec"].endswith("]")
    assert "<=>" in sql and "LIMIT" in sql


def test_retrieve_meta_filter_goes_to_jsonb_containment(monkeypatch):
    store = _store(rows=[])
    monkeypatch.setattr(retrieve_mod.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(retrieve_mod, "embed", lambda texts: [_vec()])

    retrieve("q", k=4, meta_filter={"category": "safety"})

    sql, params = store["calls"][0]
    assert json.loads(params["meta"]) == {"category": "safety"}
    assert "c.meta @> %(meta)s::jsonb" in sql


def test_retrieve_blank_query_skips_db(monkeypatch):
    monkeypatch.setattr(
        retrieve_mod.tenancy, "connect", lambda *a, **k: pytest.fail("빈 질의인데 DB 접속")
    )
    assert retrieve("   ") == []


def test_to_vector_literal_format():
    assert to_vector_literal([0.5, -1.0]) == "[0.5,-1.0]"


# ── tenancy ───────────────────────────────────────────────

def test_tenant_schema_prefix_and_validation():
    assert tenancy.tenant_schema("axis_demo") == "tenant_axis_demo"
    for bad in ("", "Axis", "a-b", "a;drop"):
        with pytest.raises(ValueError):
            tenancy.tenant_schema(bad)


def test_tenant_slug_default_and_env(monkeypatch):
    assert tenancy.tenant_slug() == "axis_demo"
    monkeypatch.setenv("TENANT_SLUG", "other_site")
    assert tenancy.tenant_slug() == "other_site"


# ── 근거 강제 프롬프트 ─────────────────────────────────────

def test_prompt_contains_chunk_text_and_rules():
    chunks = [_chunk(1), _chunk(2)]
    p = graph.build_prompt("프레스 점검 절차는?", "vi", chunks)

    for c in chunks:
        assert c.content in p
    assert "프레스 점검 절차는?" in p
    assert graph.NO_ANSWER in p
    assert "자료 밖의 일반 지식" in p
    assert "베트남어" in p  # lang=vi


def test_prompt_lang_switches_output_language():
    assert "인도네시아어" in graph.build_prompt("q", "in", [_chunk(1)])
    assert "한국어" in graph.build_prompt("q", "ko", [_chunk(1)])


@pytest.mark.parametrize(
    "text,expected",
    [("NO_ANSWER", True), ("  no_answer  ", True), ("", True), ("안전화를 착용하세요.", False)],
)
def test_is_no_answer(text, expected):
    assert graph.is_no_answer(text) is expected


# ── run_ask — grounded 경로 ───────────────────────────────

def _patch_llm(monkeypatch, text="안전덮개를 확인하세요.", error=None):
    seen = {}

    def _complete(prompt, tier, timeout_s=None):
        seen.update(prompt=prompt, tier=tier, timeout_s=timeout_s)
        return llm_adapter.LLMResult(
            text=text, tier_used="local", model="qwen3:8b", latency_ms=5, error=error
        )

    monkeypatch.setattr(graph, "complete", _complete)
    return seen


def test_run_ask_grounded_records_sources_and_trace(monkeypatch):
    store = _store(question_id=7)
    monkeypatch.setattr(graph.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(graph, "retrieve", lambda q, k=4: [_chunk(1), _chunk(2)])
    seen = _patch_llm(monkeypatch)

    result = graph.run_ask("프레스 점검?", "vi")

    assert result.answer == "안전덮개를 확인하세요."
    assert len(result.sources) == 2
    assert result.sources[0]["chunk_id"] == 11
    assert result.verify == {"score": 0.0, "passed": True, "gated": False}
    assert len(result.trace_id) == 32

    # M-17·M-30: 로컬 고정 + 티어 설정값 위임
    assert seen["tier"] == "local"
    assert seen["timeout_s"] is None

    # questions insert 1건, unanswered_queue insert 없음
    sqls = [c[0] for c in store["calls"]]
    assert any("INSERT INTO questions" in s for s in sqls)
    assert not any("unanswered_queue" in s for s in sqls)

    params = [c[1] for c in store["calls"] if "INSERT INTO questions" in c[0]][0]
    assert params["grounded"] is True
    assert params["answer"] == "안전덮개를 확인하세요."
    assert params["latency_ms"] is not None
    trace = json.loads(params["trace"])
    assert trace["classify"] == {"lang": "vi"}
    assert trace["retrieve"]["hits"] == 2 and trace["retrieve"]["k"] == 4
    assert trace["retrieve"]["top_score"] == pytest.approx(0.89)
    assert trace["route"]["tier"] == "local"
    assert trace["route"]["model"] == "qwen3:8b"
    assert trace["verify"] == {"score": 0.0, "passed": True, "gated": False}
    assert trace["grounded"] is True
    assert json.loads(params["sources"])[0]["title"] == "프레스 작업 안전수칙"


def test_run_ask_uses_top_k_4(monkeypatch):
    store = _store()
    monkeypatch.setattr(graph.tenancy, "connect", fake_connect(store))
    seen = {}

    def _retrieve(q, k=4):
        seen["k"] = k
        return [_chunk(1)]

    monkeypatch.setattr(graph, "retrieve", _retrieve)
    _patch_llm(monkeypatch)

    graph.run_ask("q", "vi")

    assert seen["k"] == 4


# ── run_ask — 무근거 차단 (M-05) ──────────────────────────

def test_run_ask_no_chunks_blocks_and_enqueues(monkeypatch):
    store = _store(question_id=42)
    monkeypatch.setattr(graph.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(graph, "retrieve", lambda q, k=4: [])
    monkeypatch.setattr(
        graph, "complete", lambda *a, **k: pytest.fail("검색 0건인데 LLM 호출됨")
    )

    result = graph.run_ask("사규에 없는 질문", "vi")

    assert result.answer == ""
    assert result.sources == []
    assert result.verify == {"score": 0.0, "passed": False, "gated": True}

    sqls = [c[0] for c in store["calls"]]
    assert any("INSERT INTO unanswered_queue" in s for s in sqls)
    q_params = [c[1] for c in store["calls"] if "INSERT INTO questions" in c[0]][0]
    assert q_params["grounded"] is False
    assert q_params["answer"] is None  # 측정 #2: grounded=false 면 answer NULL
    u_params = [c[1] for c in store["calls"] if "unanswered_queue" in c[0]][0]
    assert u_params == {"qid": 42}
    assert "'open'" in [c[0] for c in store["calls"] if "unanswered_queue" in c[0]][0]


def test_run_ask_no_answer_marker_blocks_and_enqueues(monkeypatch):
    """검색은 됐지만 모델이 근거 부족을 신고 → 차단 + 이관."""
    store = _store(question_id=43)
    monkeypatch.setattr(graph.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(graph, "retrieve", lambda q, k=4: [_chunk(1)])
    _patch_llm(monkeypatch, text="NO_ANSWER")

    result = graph.run_ask("자료 밖 질문", "vi")

    assert result.answer == ""
    assert result.sources == []
    assert result.verify["gated"] is True
    assert any("unanswered_queue" in c[0] for c in store["calls"])
    q_params = [c[1] for c in store["calls"] if "INSERT INTO questions" in c[0]][0]
    assert q_params["grounded"] is False
    assert q_params["answer"] is None


def test_run_ask_adapter_error_blocks(monkeypatch):
    store = _store(question_id=44)
    monkeypatch.setattr(graph.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(graph, "retrieve", lambda q, k=4: [_chunk(1)])
    _patch_llm(monkeypatch, text="", error="local_failed[qwen3:8b:timeout]")

    result = graph.run_ask("q", "vi")

    assert result.answer == ""
    assert result.verify["gated"] is True
    q_params = [c[1] for c in store["calls"] if "INSERT INTO questions" in c[0]][0]
    trace = json.loads(q_params["trace"])
    assert trace["route"]["error"] == "local_failed[qwen3:8b:timeout]"


def test_run_ask_survives_db_failure(monkeypatch):
    """qa_logs 기록 실패가 사용자 응답을 막지 않는다."""
    from contextlib import contextmanager

    @contextmanager
    def _boom(slug=None):
        raise RuntimeError("db down")
        yield  # pragma: no cover

    monkeypatch.setattr(graph.tenancy, "connect", _boom)
    monkeypatch.setattr(graph, "retrieve", lambda q, k=4: [_chunk(1)])
    _patch_llm(monkeypatch)

    result = graph.run_ask("q", "vi")

    assert result.answer == "안전덮개를 확인하세요."
    assert result.trace_id


# ── POST /api/v1/ask — §3 응답 스키마 ─────────────────────

def test_ask_endpoint_response_schema(monkeypatch):
    store = _store()
    monkeypatch.setattr(graph.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(graph, "retrieve", lambda q, k=4: [_chunk(1)])
    _patch_llm(monkeypatch)

    r = client.post("/api/v1/ask", json={"question": "프레스 작업 전 확인사항?", "lang": "vi"})

    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"answer", "sources", "verify", "trace_id"}
    assert set(body["verify"]) == {"score", "passed", "gated"}
    assert set(body["sources"][0]) == {"document_id", "chunk_id", "title", "category"}
    assert body["trace_id"]
    assert "mock" not in body and "echo" not in body  # mock 제거 확인


def test_ask_endpoint_gated_response(monkeypatch):
    store = _store()
    monkeypatch.setattr(graph.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(graph, "retrieve", lambda q, k=4: [])

    r = client.post("/api/v1/ask", json={"question": "근거 없는 질문", "lang": "vi"})

    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == ""
    assert body["sources"] == []
    assert body["verify"]["gated"] is True


def test_ask_endpoint_rejects_empty_question():
    r = client.post("/api/v1/ask", json={"question": "", "lang": "vi"})
    assert r.status_code == 422


def test_ask_endpoint_lang_defaults_to_vi(monkeypatch):
    store = _store()
    monkeypatch.setattr(graph.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(graph, "retrieve", lambda q, k=4: [_chunk(1)])
    _patch_llm(monkeypatch)

    r = client.post("/api/v1/ask", json={"question": "q"})

    assert r.status_code == 200
    params = [c[1] for c in store["calls"] if "INSERT INTO questions" in c[0]][0]
    assert params["lang"] == "vi"
