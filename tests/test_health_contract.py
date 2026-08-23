"""스켈레톤 더미 테스트 — /health 응답 계약 + /ask mock 표식. [새봄]

- /health: 200/503, 필드 status/version/slot/components{api,db,llm} (DB 없는 CI 에선 503 이 정상)
- /api/v1/ask: mock 응답은 "mock": true 를 반드시 포함 (실연동 교체 시 이 테스트가 RED → 제거)
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_contract():
    r = client.get("/health")
    assert r.status_code in (200, 503)
    body = r.json()
    assert set(body) >= {"status", "version", "slot", "components"}
    assert set(body["components"]) == {"api", "db", "llm"}
    assert (r.status_code == 200) == (body["components"]["db"]["status"] == "ok")


def test_ask_mock_contract():
    r = client.post("/api/v1/ask", json={"question": "프레스 작업 전 확인사항?", "lang": "vi"})
    assert r.status_code == 200
    body = r.json()
    assert body["mock"] is True
    assert set(body) >= {"answer", "sources", "verify", "trace_id"}
    assert set(body["verify"]) == {"score", "passed", "gated"}
