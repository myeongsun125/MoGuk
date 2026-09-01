"""M-28c — edge 조회 경로 릴레이 경유 단위 테스트. [새봄]

검증 대상 계약:
- M-28c ①: 디스패처 method 축 — GET 조회(§3 공개면 계약분)와 관리자 전이가 릴레이로 처리된다.
- M-28c ②: edge role 라우터 분기 — edge 는 DB 를 직접 만지지 않고 큐로 넘긴다(M-22 정합).
- M-28c ③: M-28a 파라미터·큐 메커니즘·/internal 3종 무접촉.
- M-28b: GET 조회의 identity 전파는 optional — 미인증이면 None.

R6 배경: #27 유입 결함(GET 조회가 edge 에서 500)을 단위 테스트가 못 잡은 이유는
기존 테스트가 전부 API_ROLE=core 고정이었기 때문이다. 여기서는 edge 앱을 띄운다.
"""

import asyncio

import httpx
import pytest

from app.main import build_app
from app.services import relay
from app.workers import relay_poller

PUBLIC_ROW = {
    "id": 1,
    "status": "submitted",
    "processing_state": "queued",
    "reporter_confirmed": False,
    "created_at": "2026-08-30T12:00:00+00:00",
}


@pytest.fixture(autouse=True)
def _base_env(monkeypatch):
    for key in ("RELAY_HOLD_S", "RELAY_BATCH_MAX", "RELAY_EDGE_WAIT_S",
                "RELAY_LEASE_S", "RELAY_REDELIVER_MAX", "API_ROLE", "EDGE_API_URL"):
        monkeypatch.delenv(key, raising=False)
    relay.queue.reset()
    yield
    relay.queue.reset()


# ── M-28c ②: edge role 라우터 분기 (500 이 아니라 릴레이 경유) ──

INVITE_BODY = {"name": "Nguyen", "emp_no": "E-1001", "lang": "vi"}

# (method, url, relay_path, send_body, relay_body, status, payload)
# send_body 는 클라이언트가 보낸 본문, relay_body 는 큐에 실려야 할 본문 —
# resolve 는 라우터가 {note} 로 정규화하므로 둘이 다르다(M-28b 본문 정규화 지점).
# status 축은 M-32b 편입분(201) 때문에 생겼다 — 성공 코드를 200 으로 하드코딩하지 않는다.
EDGE_CASES = [
    ("GET", "/api/v1/reports/1", "/api/v1/reports/1", {}, {}, 200, PUBLIC_ROW),
    ("GET", "/api/v1/admin/reports", "/api/v1/admin/reports", {}, {}, 200, [PUBLIC_ROW]),
    ("GET", "/api/v1/admin/reports?status=submitted",
     "/api/v1/admin/reports?status=submitted", {}, {}, 200, [PUBLIC_ROW]),
    ("GET", "/api/v1/admin/reports/1", "/api/v1/admin/reports/1", {}, {}, 200,
     {"id": 1, "events": []}),
    ("POST", "/api/v1/admin/reports/1/ack", "/api/v1/admin/reports/1/ack", {}, {}, 200,
     {"id": 1, "status": "acknowledged"}),
    ("POST", "/api/v1/admin/reports/1/resolve", "/api/v1/admin/reports/1/resolve",
     {}, {"note": None}, 200, {"id": 1, "status": "resolved"}),
    # M-32b: 초대 발급 — 201 그대로 투과(200 으로 눌리지 않는다), 본문 온전 전달.
    # M-39 파트2: 라우터 model_dump 가 미지정 phone 을 None 으로 실어 보낸다.
    ("POST", "/api/v1/admin/workers/invite", "/api/v1/admin/workers/invite",
     INVITE_BODY, {**INVITE_BODY, "phone": None}, 201,
     {"invite_url": "http://localhost/activate?token=t"}),
    # M-38: 퀴즈 GET — lang 쿼리스트링 온전 전달. submit 은 인증 필수(총괄 판정 0902)라
    # 이 미인증 왕복 하네스에서 빠지고 아래 전용 테스트 2건이 대신한다.
    ("GET", "/api/v1/learn/quiz/3?lang=vi", "/api/v1/learn/quiz/3?lang=vi", {}, {}, 200,
     {"set_id": 3, "module": "learning", "title": "t", "status": "draft", "items": []}),
]


@pytest.mark.parametrize("method,url,relay_path,send_body,relay_body,status,payload", EDGE_CASES)
@pytest.mark.asyncio
async def test_edge_query_paths_go_through_relay_not_500(
    monkeypatch, method, url, relay_path, send_body, relay_body, status, payload
):
    """edge 에서 500 이 아니라 릴레이 왕복으로 완결된다 — #27 유입 결함 회귀 방지."""
    monkeypatch.setenv("API_ROLE", "edge")
    monkeypatch.setenv("RELAY_HOLD_S", "3")
    monkeypatch.setenv("RELAY_EDGE_WAIT_S", "5")
    monkeypatch.delenv("DATABASE_URL", raising=False)   # DB 자격 없이도 성립해야 한다
    app = build_app("edge")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://edge"
    ) as client:
        task = asyncio.create_task(
            client.get(url) if method == "GET" else client.post(url, json=send_body)
        )

        pend = await client.get("/internal/relay/pending")
        items = pend.json()["items"]
        assert len(items) == 1, items
        assert items[0]["method"] == method
        assert items[0]["path"] == relay_path        # 경로·쿼리 온전 전달 (M-28c ①)
        assert items[0]["body"] == relay_body        # 본문 온전 전달
        assert items[0]["identity"] is None          # 관리자 인증 부재(M-15b)
        rid = items[0]["request_id"]

        rr = await client.post(
            f"/internal/relay/{rid}/respond", json={"status_code": status, "body": payload}
        )
        assert rr.status_code == 200

        resp = await task

    assert resp.status_code == status, resp.text     # 성공 코드 그대로 투과
    assert resp.json() == payload


@pytest.mark.asyncio
async def test_edge_get_never_touches_db(monkeypatch):
    """edge 는 DATABASE_URL 이 없어도 조회가 500 이 되지 않는다 — 저장소 호출 0."""
    monkeypatch.setenv("API_ROLE", "edge")
    monkeypatch.setenv("RELAY_EDGE_WAIT_S", "0.15")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    from app.services import risk_reports

    def _boom(*a, **k):
        pytest.fail("edge 에서 저장소를 호출했다 (M-22 위반)")

    monkeypatch.setattr(risk_reports.tenancy, "connect", _boom)
    app = build_app("edge")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://edge"
    ) as client:
        r = await client.get("/api/v1/reports/1")

    # 응답자가 없으니 보류 상한 초과 504 — 중요한 건 500(DB 접근 실패)이 아니라는 점
    assert r.status_code == 504, r.text


@pytest.mark.asyncio
async def test_edge_get_propagates_identity_as_none_when_unauthenticated(monkeypatch):
    """M-28b ④ 정합 — 미인증 GET 조회의 identity 는 None."""
    monkeypatch.setenv("API_ROLE", "edge")
    monkeypatch.setenv("RELAY_EDGE_WAIT_S", "0.15")
    app = build_app("edge")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://edge"
    ) as client:
        task = asyncio.create_task(client.get("/api/v1/reports/1"))
        pend = await client.get("/internal/relay/pending")
        items = pend.json()["items"]
        assert "identity" in items[0] and items[0]["identity"] is None
        await task


@pytest.mark.asyncio
async def test_edge_get_propagates_worker_identity_when_authenticated(monkeypatch):
    """인증 토큰이 있으면 wid·tenant 만 전파(M-28b ①) — 원 JWT 는 경계를 넘지 않는다."""
    monkeypatch.setenv("API_ROLE", "edge")
    monkeypatch.setenv("RELAY_EDGE_WAIT_S", "0.15")
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-m28c")
    from app.services import auth as auth_service

    token = auth_service.issue_token_pair(41, "axis_demo")["jwt"]
    app = build_app("edge")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://edge"
    ) as client:
        task = asyncio.create_task(
            client.get("/api/v1/reports/1", headers={"Authorization": f"Bearer {token}"})
        )
        pend = await client.get("/internal/relay/pending")
        items = pend.json()["items"]
        assert items[0]["identity"] == {"wid": 41, "tenant": "axis_demo"}
        assert "Authorization" not in json_keys(items[0])
        assert token not in str(items[0])
        await task


def json_keys(item: dict) -> list:
    return sorted(item)


# ── M-28c ①: 폴러 GET 디스패치 매핑 ────────────────────────

def test_dispatch_get_report_public(monkeypatch):
    called = {}

    def _get(rid):
        called["id"] = rid
        return PUBLIC_ROW

    monkeypatch.setattr("app.services.risk_reports.get_report_public", _get)
    status, body = relay_poller.dispatch("GET", "/api/v1/reports/7", {})
    assert (status, body) == (200, PUBLIC_ROW)
    assert called["id"] == 7


def test_dispatch_get_report_public_404(monkeypatch):
    from app.services import risk_reports

    def _raise(rid):
        raise risk_reports.ReportNotFound("nope")

    monkeypatch.setattr("app.services.risk_reports.get_report_public", _raise)
    status, body = relay_poller.dispatch("GET", "/api/v1/reports/7", {})
    assert status == 404 and body == {"detail": "report not found"}


@pytest.mark.parametrize(
    "path,expected_status",
    [("/api/v1/admin/reports", None), ("/api/v1/admin/reports?status=submitted", "submitted")],
)
def test_dispatch_admin_list_passes_status_query(monkeypatch, path, expected_status):
    """?status= 가 릴레이 path 를 거쳐 list_reports 인자로 복원된다 (M-28c ①)."""
    seen = {}

    def _list(status=None):
        seen["status"] = status
        return []

    monkeypatch.setattr("app.services.risk_reports.list_reports", _list)
    status, body = relay_poller.dispatch("GET", path, {})
    assert status == 200 and body == []
    assert seen["status"] == expected_status


def test_dispatch_admin_detail(monkeypatch):
    seen = {}

    def _detail(rid):
        seen["id"] = rid
        return {"id": rid, "events": []}

    monkeypatch.setattr("app.services.risk_reports.get_report_detail", _detail)
    status, body = relay_poller.dispatch("GET", "/api/v1/admin/reports/9", {})
    assert status == 200 and body["id"] == 9 and seen["id"] == 9


def test_dispatch_admin_transitions(monkeypatch):
    monkeypatch.setattr(
        "app.services.risk_reports.acknowledge", lambda rid: {"id": rid, "status": "acknowledged"}
    )
    monkeypatch.setattr(
        "app.services.risk_reports.resolve", lambda rid, note=None: {"id": rid, "note": note}
    )
    assert relay_poller.dispatch("POST", "/api/v1/admin/reports/3/ack", {}) == (
        200, {"id": 3, "status": "acknowledged"}
    )
    assert relay_poller.dispatch("POST", "/api/v1/admin/reports/3/resolve", {"note": "done"}) == (
        200, {"id": 3, "note": "done"}
    )


def test_dispatch_admin_transition_errors(monkeypatch):
    from app.services import risk_reports

    def _skip(rid):
        raise risk_reports.TransitionError("resolved → acknowledged 불가")

    monkeypatch.setattr("app.services.risk_reports.acknowledge", _skip)
    status, body = relay_poller.dispatch("POST", "/api/v1/admin/reports/3/ack", {})
    assert status == 422 and "불가" in body["detail"]


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/reports/abc",              # id 가 정수가 아님
        "/api/v1/reports/1/confirm",        # POST 전용 하위 경로 — GET 으로 오인 금지
        "/api/v1/admin/reports/abc",
        "/api/v1/admin/documents",          # 미등록 GET (glossary 는 승인큐 PR 에서 등록됨)
        "/api/v1/health",
    ],
)
def test_dispatch_unregistered_get_returns_404(path):
    status, body = relay_poller.dispatch("GET", path, {})
    assert status == 404, (path, status, body)


def test_dispatch_post_branches_unchanged(monkeypatch):
    """기존 POST 분기 무변경 — 미등록 POST 는 종전대로 404."""
    status, body = relay_poller.dispatch("POST", "/api/v1/nope", {})
    assert status == 404 and "디스패치 대상 아님" in body["detail"]


# ── M-32b: invite 디스패치 (edge 왕복은 EDGE_CASES 로 흡수) ──


def test_dispatch_invite_created(monkeypatch):
    """디스패치 성공 매핑 — 201 + create_invite 인자 전달."""
    from app.services import invites

    seen = {}

    def fake_create(name, emp_no, lang, phone=None):
        seen.update(name=name, emp_no=emp_no, lang=lang, phone=phone)
        return {"invite_url": "http://localhost/activate?token=t"}

    monkeypatch.setattr(invites, "create_invite", fake_create)
    status, body = relay_poller.dispatch("POST", "/api/v1/admin/workers/invite", INVITE_BODY)
    assert status == 201
    assert body == {"invite_url": "http://localhost/activate?token=t"}
    assert seen == {**INVITE_BODY, "phone": None}      # M-39 파트2 — phone 전달(미지정 None)


@pytest.mark.parametrize(
    "exc,expected",
    [
        ("InvalidInviteRequest", 422),
        ("WorkerAlreadyActive", 409),
    ],
)
def test_dispatch_invite_error_mapping(monkeypatch, exc, expected):
    """예외→상태코드 3분기가 core 라우터와 동일하다 (422·409)."""
    from app.services import invites

    def boom(*a, **k):
        raise getattr(invites, exc)("사유")

    monkeypatch.setattr(invites, "create_invite", boom)
    status, body = relay_poller.dispatch("POST", "/api/v1/admin/workers/invite", INVITE_BODY)
    assert status == expected
    assert body == {"detail": "사유"}


# ── M-38: 퀴즈 디스패치 (edge 왕복은 EDGE_CASES 로 흡수) ──

def test_dispatch_quiz_get_passes_lang_and_worker_id(monkeypatch):
    """GET 디스패치 — set_id·lang 쿼리·identity.wid 가 서비스 인자로 전달된다."""
    seen = {}

    def fake_get(set_id, lang=None, worker_id=None):
        seen.update(set_id=set_id, lang=lang, worker_id=worker_id)
        return {"set_id": set_id, "items": []}

    monkeypatch.setattr("app.services.quiz.get_quiz", fake_get)
    status, body = relay_poller.dispatch(
        "GET", "/api/v1/learn/quiz/3?lang=vi", {}, None, {"wid": 9, "tenant": "axis_demo"}
    )
    assert (status, body) == (200, {"set_id": 3, "items": []})
    assert seen == {"set_id": 3, "lang": "vi", "worker_id": 9}


def test_dispatch_quiz_get_unauthenticated_no_lang(monkeypatch):
    """미인증·lang 미지정 — 서비스에 (None, None) 그대로 넘어간다(ko 폴백은 서비스 몫)."""
    seen = {}

    def fake_get(set_id, lang=None, worker_id=None):
        seen.update(lang=lang, worker_id=worker_id)
        return {"set_id": set_id, "items": []}

    monkeypatch.setattr("app.services.quiz.get_quiz", fake_get)
    status, _ = relay_poller.dispatch("GET", "/api/v1/learn/quiz/3", {})
    assert status == 200
    assert seen == {"lang": None, "worker_id": None}


def test_dispatch_quiz_get_404(monkeypatch):
    from app.services import quiz

    def boom(*a, **k):
        raise quiz.QuizSetNotFound("nope")

    monkeypatch.setattr("app.services.quiz.get_quiz", boom)
    status, body = relay_poller.dispatch("GET", "/api/v1/learn/quiz/999", {})
    assert status == 404 and body == {"detail": "quiz set not found"}


def test_dispatch_quiz_submit_passes_answers_and_worker_id(monkeypatch):
    seen = {}

    def fake_submit(set_id, answers, worker_id=None):
        seen.update(set_id=set_id, answers=answers, worker_id=worker_id)
        return {"score": 100, "passed": True, "label": "green"}

    monkeypatch.setattr("app.services.quiz.submit_quiz", fake_submit)
    status, body = relay_poller.dispatch(
        "POST", "/api/v1/learn/quiz/3/submit", {"answers": [2, 0]}, None, {"wid": 9}
    )
    assert (status, body) == (200, {"score": 100, "passed": True, "label": "green"})
    assert seen == {"set_id": 3, "answers": [2, 0], "worker_id": 9}


def test_dispatch_quiz_submit_unauthenticated_401(monkeypatch):
    """총괄 판정 0902 — 릴레이 경로도 익명 submit 401(confirm M-37 동형), 서비스 미호출."""
    def _boom(*a, **k):
        pytest.fail("익명인데 채점 서비스를 호출했다")

    monkeypatch.setattr("app.services.quiz.submit_quiz", _boom)
    from app.services.auth import AUTH_FAILED_MESSAGE

    status, body = relay_poller.dispatch("POST", "/api/v1/learn/quiz/3/submit", {"answers": [0]})
    assert status == 401
    assert body == {"detail": AUTH_FAILED_MESSAGE}


@pytest.mark.parametrize("exc,expected", [("QuizSetNotFound", 404), ("InvalidAnswers", 422)])
def test_dispatch_quiz_submit_error_mapping(monkeypatch, exc, expected):
    """예외→상태코드 분기가 core 라우터와 동일하다 (404·422) — 인증 identity 동반."""
    from app.services import quiz

    def boom(*a, **k):
        raise getattr(quiz, exc)("사유")

    monkeypatch.setattr("app.services.quiz.submit_quiz", boom)
    status, body = relay_poller.dispatch(
        "POST", "/api/v1/learn/quiz/3/submit", {"answers": []}, None, {"wid": 9}
    )
    assert status == expected
    if expected == 422:
        assert body == {"detail": "사유"}


@pytest.mark.asyncio
async def test_edge_submit_authenticated_goes_through_relay(monkeypatch):
    """인증 submit — identity {wid, tenant} 로 큐 적재·본문 온전 전달·응답 투과."""
    monkeypatch.setenv("API_ROLE", "edge")
    monkeypatch.setenv("RELAY_HOLD_S", "3")
    monkeypatch.setenv("RELAY_EDGE_WAIT_S", "5")
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-m38")
    from app.services import auth as auth_service

    token = auth_service.issue_token_pair(41, "axis_demo")["jwt"]
    app = build_app("edge")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://edge"
    ) as client:
        task = asyncio.create_task(client.post(
            "/api/v1/learn/quiz/3/submit", json={"answers": [1, 0]},
            headers={"Authorization": f"Bearer {token}"},
        ))
        pend = await client.get("/internal/relay/pending")
        items = pend.json()["items"]
        assert len(items) == 1
        assert items[0]["path"] == "/api/v1/learn/quiz/3/submit"
        assert items[0]["body"] == {"answers": [1, 0]}
        assert items[0]["identity"] == {"wid": 41, "tenant": "axis_demo"}
        await client.post(f"/internal/relay/{items[0]['request_id']}/respond",
                          json={"status_code": 200,
                                "body": {"score": 50, "passed": False, "label": "red"}})
        resp = await task

    assert resp.status_code == 200
    assert resp.json() == {"score": 50, "passed": False, "label": "red"}


@pytest.mark.asyncio
async def test_edge_submit_anonymous_401_no_enqueue(monkeypatch):
    """익명 submit 은 edge 라우터에서 401 — 릴레이 큐에 적재조차 되지 않는다."""
    monkeypatch.setenv("API_ROLE", "edge")
    monkeypatch.setenv("RELAY_EDGE_WAIT_S", "0.2")
    app = build_app("edge")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://edge"
    ) as client:
        r = await client.post("/api/v1/learn/quiz/3/submit", json={"answers": [1, 0]})

    assert r.status_code == 401, r.text
    assert relay.queue.snapshot() == []


# ── M-28c ③: 무접촉 단정 ──────────────────────────────────

def test_m28a_parameters_untouched():
    assert relay.hold_s() == 20.0
    assert relay.batch_max() == 10
    assert relay.edge_wait_s() == 30.0
    assert relay.lease_s() == 60.0
    assert relay.redeliver_max() == 1


def test_enqueue_signature_unchanged():
    """relay.py 무접촉 — GET 은 빈 dict body 로 기존 시그니처를 그대로 쓴다."""
    import inspect

    params = list(inspect.signature(relay.RelayQueue.enqueue).parameters)
    assert params == ["self", "method", "path", "body", "identity"]

    q = relay.RelayQueue()
    item = q.enqueue("GET", "/api/v1/reports/1", {}, None)
    assert item.method == "GET" and item.body == {} and item.identity is None
    payload = item.as_payload()
    assert "identity" in payload and payload["method"] == "GET" and payload["body"] == {}
    assert len(payload) == 8   # M-28b 로 확정된 8필드 — M-28c 는 추가하지 않는다
