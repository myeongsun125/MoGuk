"""V2-2 RAG /ask 단위 테스트 — 네트워크·DB 없음(전부 mock/스텁). [새봄]

검증 대상 계약:
- skeleton-v3 §3: POST /ask {question, lang} → {answer, sources[], verify:{score,passed,gated}, trace_id}
- skeleton-v3 §4 동결: retrieve(query, k=4, meta_filter=None) / embed(texts) -> 1024차원
- M-02a: 임베딩 런타임 = ollama /api/embed 단일, 모델 EMBED_MODEL(기본 bge-m3)
- M-05 / BLUEPRINT §4-1: grounded=false → 답변 차단
- M-05a: unanswered_queue 적재는 검색 0건·NO_ANSWER 2종만 — retrieve 예외·local_failed 제외
- M-09: questions.trace 에 classify → retrieve(hit·score) → route.tier → verify 기록
- M-17·M-30: /ask 는 tier="local", timeout_s=None 으로 어댑터를 호출한다
- 엔드포인트 테스트는 API_ROLE=core 경로 (edge 는 릴레이 경유 — tests/test_relay.py)

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
    # M-05a: local_failed 는 시스템 오류 — unanswered_queue 미적재
    assert not any("unanswered_queue" in c[0] for c in store["calls"])


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
    monkeypatch.setenv("API_ROLE", "core")
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
    monkeypatch.setenv("API_ROLE", "core")
    store = _store()
    monkeypatch.setattr(graph.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(graph, "retrieve", lambda q, k=4: [])

    r = client.post("/api/v1/ask", json={"question": "근거 없는 질문", "lang": "vi"})

    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == ""
    assert body["sources"] == []
    assert body["verify"]["gated"] is True


def test_ask_endpoint_rejects_empty_question(monkeypatch):
    monkeypatch.setenv("API_ROLE", "core")
    r = client.post("/api/v1/ask", json={"question": "", "lang": "vi"})
    assert r.status_code == 422


def test_ask_endpoint_lang_defaults_to_vi(monkeypatch):
    monkeypatch.setenv("API_ROLE", "core")
    store = _store()
    monkeypatch.setattr(graph.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(graph, "retrieve", lambda q, k=4: [_chunk(1)])
    _patch_llm(monkeypatch)

    r = client.post("/api/v1/ask", json={"question": "q"})

    assert r.status_code == 200
    params = [c[1] for c in store["calls"] if "INSERT INTO questions" in c[0]][0]
    assert params["lang"] == "vi"


# ── retrieve/embed 단계 예외 격리 (#14 BG 메모 ②) ─────────

def test_run_ask_embed_failure_is_isolated(monkeypatch):
    """embed(ollama HTTP) 오류 → 500 아님. gated 응답 + unanswered_queue 미적재."""
    store = _store(question_id=51)
    monkeypatch.setattr(graph.tenancy, "connect", fake_connect(store))

    def _boom(q, k=4):
        raise httpx.ConnectError("ollama refused")

    monkeypatch.setattr(graph, "retrieve", _boom)
    monkeypatch.setattr(graph, "complete", lambda *a, **k: pytest.fail("검색 실패인데 LLM 호출됨"))

    result = graph.run_ask("프레스 점검?", "vi")

    assert result.answer == ""
    assert result.sources == []
    assert result.verify == {"score": 0.0, "passed": False, "gated": True}
    assert result.trace_id

    sqls = [c[0] for c in store["calls"]]
    assert any("INSERT INTO questions" in s for s in sqls)
    assert not any("unanswered_queue" in s for s in sqls)  # 시스템 오류 ≠ 무근거

    params = [c[1] for c in store["calls"] if "INSERT INTO questions" in c[0]][0]
    assert params["grounded"] is False
    assert params["answer"] is None
    trace = json.loads(params["trace"])
    assert trace["route"]["error"] == "retrieve_failed[ConnectError]"
    assert trace["retrieve"]["error"] == "retrieve_failed[ConnectError]"
    assert trace["retrieve"]["hits"] == 0


def test_run_ask_db_failure_in_retrieve_is_isolated(monkeypatch):
    """pgvector 조회 DB 오류 → 200 + gated. qa_logs 기록도 실패하면 로그만 남기고 진행."""
    from contextlib import contextmanager

    @contextmanager
    def _boom_conn(slug=None):
        raise RuntimeError("db down")
        yield  # pragma: no cover

    monkeypatch.setattr(graph.tenancy, "connect", _boom_conn)

    def _boom(q, k=4):
        raise RuntimeError("relation \"chunks\" does not exist")

    monkeypatch.setattr(graph, "retrieve", _boom)
    monkeypatch.setattr(graph, "complete", lambda *a, **k: pytest.fail("검색 실패인데 LLM 호출됨"))

    result = graph.run_ask("프레스 점검?", "vi")

    assert result.answer == ""
    assert result.sources == []
    assert result.verify["gated"] is True
    assert result.verify["passed"] is False


def test_ask_endpoint_returns_200_on_retrieve_failure(monkeypatch):
    """라우터 레벨에서도 500 이 아니라 §3 스키마 200 이어야 한다."""
    monkeypatch.setenv("API_ROLE", "core")
    store = _store()
    monkeypatch.setattr(graph.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(
        graph, "retrieve", lambda q, k=4: (_ for _ in ()).throw(httpx.ReadTimeout("embed timeout"))
    )

    r = client.post("/api/v1/ask", json={"question": "프레스 점검?", "lang": "vi"})

    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"answer", "sources", "verify", "trace_id"}
    assert body["answer"] == "" and body["sources"] == []
    assert body["verify"] == {"score": 0.0, "passed": False, "gated": True}
    assert not any("unanswered_queue" in c[0] for c in store["calls"])


# ── trace.relay 계측 (M-28a, 내부 전용) ───────────────────

def test_run_ask_records_relay_timestamps(monkeypatch):
    """릴레이 경유 시 trace.relay 3필드(ISO8601) 기록 — 응답에는 노출하지 않는다."""
    store = _store(question_id=61)
    monkeypatch.setattr(graph.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(graph, "retrieve", lambda q, k=4: [_chunk(1)])
    _patch_llm(monkeypatch)

    result = graph.run_ask(
        "q", "vi", relay_meta={"enqueued_at": 1756000000.0, "leased_at": 1756000000.25}
    )

    params = [c[1] for c in store["calls"] if "INSERT INTO questions" in c[0]][0]
    trace = json.loads(params["trace"])
    assert set(trace["relay"]) == {"enqueued_at", "leased_at", "responded_at"}
    assert trace["relay"]["enqueued_at"].startswith("2025-")
    assert trace["relay"]["enqueued_at"].endswith("+00:00")  # ISO8601 UTC
    assert trace["relay"]["leased_at"] > trace["relay"]["enqueued_at"]
    assert trace["relay"]["responded_at"] is not None

    # Answer(=API 응답 소스)에는 relay 가 없다
    assert not hasattr(result, "relay")
    assert set(result.verify) == {"score", "passed", "gated"}


def test_run_ask_direct_path_omits_relay(monkeypatch):
    """core 직접 경로(비릴레이)는 trace.relay 를 만들지 않는다."""
    store = _store()
    monkeypatch.setattr(graph.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(graph, "retrieve", lambda q, k=4: [_chunk(1)])
    _patch_llm(monkeypatch)

    graph.run_ask("q", "vi")

    params = [c[1] for c in store["calls"] if "INSERT INTO questions" in c[0]][0]
    assert "relay" not in json.loads(params["trace"])


def test_ask_endpoint_body_never_exposes_relay(monkeypatch):
    monkeypatch.setenv("API_ROLE", "core")
    store = _store()
    monkeypatch.setattr(graph.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(graph, "retrieve", lambda q, k=4: [_chunk(1)])
    _patch_llm(monkeypatch)

    body = client.post("/api/v1/ask", json={"question": "q", "lang": "vi"}).json()

    assert set(body) == {"answer", "sources", "verify", "trace_id"}
    assert "relay" not in body and "trace" not in body


# ── M-05a: unanswered_queue 적재 기준 ─────────────────────

def test_run_ask_local_failed_not_enqueued(monkeypatch):
    """M-05a: LLM 생성 실패(local_failed)는 시스템 오류 — gated 응답이되 queue 미적재."""
    store = _store(question_id=71)
    monkeypatch.setattr(graph.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(graph, "retrieve", lambda q, k=4: [_chunk(1)])
    _patch_llm(monkeypatch, text="", error="local_failed[qwen3:8b:timeout,qwen3:4b:timeout]")

    result = graph.run_ask("프레스 점검?", "vi")

    assert result.answer == ""
    assert result.sources == []
    assert result.verify == {"score": 0.0, "passed": False, "gated": True}

    sqls = [c[0] for c in store["calls"]]
    assert any("INSERT INTO questions" in s for s in sqls)
    assert not any("unanswered_queue" in s for s in sqls)

    params = [c[1] for c in store["calls"] if "INSERT INTO questions" in c[0]][0]
    assert params["grounded"] is False
    assert params["answer"] is None
    trace = json.loads(params["trace"])
    assert trace["route"]["error"].startswith("local_failed[")


def test_run_ask_enqueue_only_for_two_reasons(monkeypatch):
    """적재 대상 2종(검색 0건·NO_ANSWER)만 적재, 나머지 3종은 미적재."""
    cases = [
        ("no_chunks", lambda q, k=4: [], None, None, True),
        ("no_answer", lambda q, k=4: [_chunk(1)], "NO_ANSWER", None, True),
        ("local_failed", lambda q, k=4: [_chunk(1)], "", "local_failed[x]", False),
        ("retrieve_error", None, None, None, False),
    ]
    for name, retr, text, err, expect_enqueue in cases:
        store = _store()
        monkeypatch.setattr(graph.tenancy, "connect", fake_connect(store))
        if retr is None:
            monkeypatch.setattr(
                graph, "retrieve", lambda q, k=4: (_ for _ in ()).throw(httpx.ConnectError("x"))
            )
            monkeypatch.setattr(graph, "complete", lambda *a, **k: pytest.fail("호출되면 안 됨"))
        else:
            monkeypatch.setattr(graph, "retrieve", retr)
            if text is not None:
                _patch_llm(monkeypatch, text=text, error=err)

        graph.run_ask("q", "vi")

        enqueued = any("unanswered_queue" in c[0] for c in store["calls"])
        assert enqueued is expect_enqueue, f"{name}: 적재={enqueued}, 기대={expect_enqueue}"


# ── M-29a: role='case' 원천 제외 ───────────────────────────

CASE_FILTER_SQL = "COALESCE(c.meta->>'role', '') <> 'case'"


def _pg_role_filter(meta: dict | None) -> bool:
    """SQL `COALESCE(c.meta->>'role','') <> 'case'` 의 Postgres 의미를 그대로 옮긴 판정.

    meta->>'role' 는 키 부재 시 NULL → COALESCE 로 '' → 'case' 와 불일치 → 통과.
    """
    role = (meta or {}).get("role")
    return (role if role is not None else "") != "case"


def test_retrieve_sql_excludes_case_role_at_db_layer(monkeypatch):
    """M-29a: 배제는 SELECT WHERE 절에서 일어난다 — 파이썬 후처리가 아니라 원천 배제."""
    store = _store(rows=[])
    monkeypatch.setattr(retrieve_mod.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(retrieve_mod, "embed", lambda texts: [_vec()])

    retrieve("프레스 점검", k=4)

    sql, _ = store["calls"][0]
    assert CASE_FILTER_SQL in sql, sql
    # 배제는 WHERE 절에서만 — ORDER BY/LIMIT 앞에 위치해야 top-k 이전에 걸러진다
    assert sql.index(CASE_FILTER_SQL) < sql.index("ORDER BY")
    assert sql.index(CASE_FILTER_SQL) < sql.index("LIMIT")


@pytest.mark.parametrize(
    "meta,passes,label",
    [
        ({"role": "case"}, False, "role='case' — 배제"),
        ({"category": "safety"}, True, "role 키 부재(기존 적재 42청크) — 통과"),
        ({}, True, "meta 빈 dict — 통과"),
        (None, True, "meta NULL — 통과"),
        ({"role": "guide"}, True, "타 role — 통과"),
        ({"role": "law"}, True, "타 role — 통과"),
        ({"role": "Case"}, True, "대소문자 다름 — 통과(정확 일치만 배제)"),
        ({"role": ""}, True, "빈 문자열 role — 통과"),
    ],
)
def test_case_filter_semantics(meta, passes, label):
    """WHERE 조건의 판정 결과 — NULL 안전성·기존 청크 회귀 방지."""
    assert _pg_role_filter(meta) is passes, label


def test_case_filter_is_negation_not_selection():
    """조건이 뒤집히면(='case') 기존 청크가 전멸한다 — 반전 회귀 방지."""
    assert CASE_FILTER_SQL.count("<>") == 1 and "=" not in CASE_FILTER_SQL.replace("<>", "")
    assert not _pg_role_filter({"role": "case"})
    assert _pg_role_filter({"category": "safety"})


def test_retrieve_returns_rows_db_gave_without_extra_filtering(monkeypatch):
    """DB 가 걸러 보낸 행은 파이썬이 다시 손대지 않는다 — 이중 필터 없음."""
    store = _store(
        rows=[
            (11, 1, "본문 1", {"category": "safety"}, "선반 매뉴얼", "safety", 0.93),
            (12, 2, "본문 2", {"category": "process", "role": "guide"}, "프레스 매뉴얼", "process", 0.81),
        ]
    )
    monkeypatch.setattr(retrieve_mod.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(retrieve_mod, "embed", lambda texts: [_vec()])

    chunks = retrieve("q", k=4)

    assert [c.id for c in chunks] == [11, 12]
    assert chunks[1].meta["role"] == "guide"


def test_case_filter_coexists_with_meta_filter_and_topk(monkeypatch):
    """기존 meta @> 필터·top-k·유사도 정렬 무변경 (M-29a 는 조건 1개 추가일 뿐)."""
    store = _store(rows=[])
    monkeypatch.setattr(retrieve_mod.tenancy, "connect", fake_connect(store))
    monkeypatch.setattr(retrieve_mod, "embed", lambda texts: [_vec()])

    retrieve("q", k=4, meta_filter={"category": "safety"})

    sql, params = store["calls"][0]
    assert "c.meta @> %(meta)s::jsonb" in sql          # 기존 필터 유지
    assert CASE_FILTER_SQL in sql                       # M-29a 추가분
    assert "ORDER BY c.embedding <=> %(vec)s::vector" in sql
    assert "LIMIT %(k)s" in sql
    assert json.loads(params["meta"]) == {"category": "safety"}
    assert params["k"] == 4


def test_ask_never_surfaces_case_sources(monkeypatch):
    """M-29a 의 효과 — case 청크가 검색되지 않으므로 답변·sources 어디에도 나타나지 않는다."""
    seen_sql = {}

    def _retrieve(query, k=4, meta_filter=None):
        # 실제 SQL 은 위 테스트가 단정한다. 여기서는 검색 결과에 case 가 없다는 전제의 귀결을 본다.
        seen_sql["k"] = k
        return [_chunk(1)]

    monkeypatch.setattr(graph, "retrieve", _retrieve)
    monkeypatch.setattr(graph, "complete", lambda *a, **k: llm_adapter.LLMResult(text="답변", tier_used="local", model="m", latency_ms=10))
    monkeypatch.setattr(graph.tenancy, "connect", fake_connect(_store()))

    out = graph.run_ask("프레스 점검", "vi")

    assert out.sources and all("case" not in str(s) for s in out.sources)
    assert seen_sql["k"] == 4


# ── 응답 언어 = 질의 lang (총괄 재판정 0830) ───────────────

@pytest.mark.parametrize(
    "lang,name,native",
    [("vi", "베트남어", "Tiếng Việt"), ("in", "인도네시아어", "Bahasa Indonesia"), ("ko", "한국어", None)],
)
def test_prompt_states_output_language_per_lang(lang, name, native):
    """lang 별 언어 지시가 프롬프트에 실린다 — 언어명 + 원어 표기(ko 는 동일해 생략)."""
    p = graph.build_prompt("q?", lang, [_chunk(1)])

    head = [l for l in p.splitlines() if l.startswith("[출력 언어]")]
    assert len(head) == 1, p
    assert name in head[0]
    if native:
        assert native in head[0], head[0]
    else:
        assert head[0] == "[출력 언어] 한국어"          # "한국어(한국어)" 중복 금지
    assert f"답변 전체를 {name}로 작성" in p


@pytest.mark.parametrize("lang,name", [("vi", "베트남어"), ("in", "인도네시아어"), ("ko", "한국어")])
def test_prompt_repeats_language_at_answer_header(lang, name):
    """지시를 [답변] 헤더에도 중복 배치 — 규칙 목록 말미 1회로는 무시되는 사례 실측(EC2 0830)."""
    p = graph.build_prompt("q?", lang, [_chunk(1)])
    last = p.splitlines()[-1]
    assert last.startswith("[답변 — ") and name in last, last


def test_prompt_language_block_precedes_rules_and_context():
    """언어 지시 위치 — 규칙 목록·근거 자료보다 앞(모델이 무시하기 어려운 상단)."""
    p = graph.build_prompt("q?", "vi", [_chunk(1)])
    assert p.index("[출력 언어]") < p.index("규칙(반드시 지킬 것):")
    assert p.index("[출력 언어]") < p.index("[근거 자료]")


def test_prompt_unknown_lang_falls_back_to_vi():
    """미지 lang 은 기존과 동일하게 vi 로 폴백(동작 무변경)."""
    p = graph.build_prompt("q?", "xx", [_chunk(1)])
    assert "베트남어" in p


def test_prompt_no_answer_marker_is_exempt_from_translation():
    """NO_ANSWER 는 번역 금지 — is_no_answer 검출이 언어에 따라 깨지지 않게 한다."""
    p = graph.build_prompt("q?", "vi", [_chunk(1)])
    assert f"{graph.NO_ANSWER} 는 번역하지 말고 그대로 출력" in p
    assert graph.is_no_answer(graph.NO_ANSWER)


def test_prompt_keeps_existing_grounding_rules():
    """기존 프롬프트 요소 무변경 — 근거 강제·NO_ANSWER 규약·3문장·블록 구조."""
    chunks = [_chunk(1), _chunk(2)]
    p = graph.build_prompt("프레스 점검 절차는?", "vi", chunks)

    assert "아래 [근거 자료]에 있는 내용만으로 답하십시오" in p
    assert "자료 밖의 일반 지식·추측을 절대 쓰지 마십시오" in p
    assert f"정확히 {graph.NO_ANSWER} 한 단어만 출력하십시오" in p
    assert "3문장 이내로 간결하게" in p
    for block in ("[근거 자료]", "[질문]"):
        assert block in p
    for c in chunks:
        assert c.content in p
    assert "프레스 점검 절차는?" in p


def test_run_ask_passes_request_lang_into_prompt(monkeypatch):
    """배선 — 라우터가 준 lang 이 프롬프트까지 그대로 도달한다."""
    seen = {}

    def _complete(prompt, tier, timeout_s=None):
        seen["prompt"] = prompt
        return llm_adapter.LLMResult(text="Trả lời", tier_used="local", model="m", latency_ms=5)

    monkeypatch.setattr(graph, "retrieve", lambda q, k=4, meta_filter=None: [_chunk(1)])
    monkeypatch.setattr(graph, "complete", _complete)
    monkeypatch.setattr(graph.tenancy, "connect", fake_connect(_store()))

    graph.run_ask("Khi vận hành máy tiện?", "vi")
    assert "[출력 언어] 베트남어(Tiếng Việt)" in seen["prompt"]

    graph.run_ask("q", "in")
    assert "[출력 언어] 인도네시아어(Bahasa Indonesia)" in seen["prompt"]


def test_ask_endpoint_lang_reaches_prompt(monkeypatch):
    """§3 계약 무변경 — 요청 {question, lang} 의 lang 이 생성 프롬프트에 반영된다."""
    monkeypatch.setenv("API_ROLE", "core")   # edge 는 릴레이 경유(tests/test_relay.py 소관)
    seen = {}

    def _complete(prompt, tier, timeout_s=None):
        seen["prompt"] = prompt
        return llm_adapter.LLMResult(text="Trả lời", tier_used="local", model="m", latency_ms=5)

    monkeypatch.setattr(graph, "retrieve", lambda q, k=4, meta_filter=None: [_chunk(1)])
    monkeypatch.setattr(graph, "complete", _complete)
    monkeypatch.setattr(graph.tenancy, "connect", fake_connect(_store()))

    r = client.post("/api/v1/ask", json={"question": "Khi nào?", "lang": "vi"})

    assert r.status_code == 200
    assert set(r.json()) == {"answer", "sources", "verify", "trace_id"}   # §3 4필드 무변경
    assert "베트남어" in seen["prompt"]
