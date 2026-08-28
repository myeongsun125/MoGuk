"""스켈레톤 더미 테스트 — /health 응답 계약(역할별) + /ask mock 표식. [새봄]

- 공통: 필드 status/version/slot/components
- core: components{api,db,llm}, 200/503 = components.db (DB 없는 CI 에선 503 이 정상)
- edge: components{api,core_relay}, DB 체크 없음, 하트비트 전=degraded(200) / 후=ok
- /api/v1/ask 계약 테스트는 실연동 교체(V2-2)로 tests/test_rag_ask.py 로 이관
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_core_contract(monkeypatch):
    monkeypatch.setenv("API_ROLE", "core")
    r = client.get("/health")
    assert r.status_code in (200, 503)
    body = r.json()
    assert set(body) >= {"status", "version", "slot", "components"}
    assert set(body["components"]) == {"api", "db", "llm"}
    assert (r.status_code == 200) == (body["components"]["db"]["status"] == "ok")


def test_health_edge_contract_no_db(monkeypatch):
    monkeypatch.setenv("API_ROLE", "edge")
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert set(body["components"]) == {"api", "core_relay"}
    assert "db" not in body["components"]
    assert body["status"] == "degraded"  # 하트비트 수신 전

    assert client.post("/internal/core-heartbeat").status_code == 204
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["components"]["core_relay"]["status"] == "ok"
