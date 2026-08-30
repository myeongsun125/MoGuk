"""core→edge outbound 릴레이 폴러 (core 전용). [새봄]

M-22: 이동 방향은 언제나 core → edge. edge 는 core 를 호출하지 않는다.
루프 = GET edge/internal/relay/pending (long-poll) → 로컬 디스패치 → POST .../respond.

디스패치는 라우터를 HTTP 로 다시 부르지 않고(재귀 금지) 처리 함수를 직접 호출한다.
대상: POST /api/v1/ask(run_ask) · POST /api/v1/reports(submit_text_report, M-08b 배선)
     · POST /api/v1/auth/{activate,login}(services.auth, M-15 배선)
     · POST /api/v1/reports/{id}/confirm(risk_reports.confirm, M-08c 배선)
     · GET /api/v1/reports/{id} · GET /api/v1/admin/reports?status= · GET /api/v1/admin/reports/{id}
     · GET /api/v1/admin/dashboard(KPI 4종+추이)
     · POST /api/v1/admin/reports/{id}/ack|resolve  (M-28c ① — method 축 추가).
개별 item 실패는 해당 respond 에 5xx 로 회신하고 루프는 계속된다.

env: EDGE_API_URL(compose 기존 키, 기본 http://edge-api:8000), RELAY_HOLD_S(대기 상한)
※ 외부 HTTP 는 llm_adapter 전용이라는 규칙은 LLM 공급자 호출에 대한 것이며,
   core→edge 릴레이는 이 모듈이 담당한다.
"""

from __future__ import annotations

import asyncio
import logging
import os

from urllib.parse import parse_qs, urlsplit

import httpx

from app.services.relay import hold_s

log = logging.getLogger(__name__)

BACKOFF_MIN_S = 1.0
BACKOFF_MAX_S = 10.0
RESPOND_TIMEOUT_S = 10.0


def edge_api_url() -> str:
    return (os.getenv("EDGE_API_URL") or "http://edge-api:8000").rstrip("/")


def _path_id(route: str, idx: int, segments: int | None = None) -> int | None:
    """경로 세그먼트에서 정수 id 추출. 형식 위반이면 None(호출부가 404).

    segments 를 주면 세그먼트 수까지 일치해야 한다 — `/reports/{id}/confirm` 같은
    하위 경로가 `/reports/{id}` 로 오인되는 것을 막는다.
    """
    parts = route.split("/")
    if segments is not None and len(parts) != segments:
        return None
    try:
        return int(parts[idx])
    except (IndexError, ValueError):
        return None


def _dispatch_get(route: str, query: dict) -> tuple[int, object]:
    """M-28c ①: §3 공개면 GET 조회 디스패치. edge 는 DB 자격이 없어 여기로 넘어온다.

    미등록 경로는 기존과 동일하게 404 로 떨어진다.
    """
    from app.services.risk_reports import (
        ReportNotFound,
        get_report_detail,
        get_report_public,
        list_reports,
    )

    if route.startswith("/api/v1/reports/"):
        report_id = _path_id(route, 4, segments=5)
        if report_id is None:
            return 404, {"detail": f"relay: 잘못된 report_id 경로 {route}"}
        try:
            return 200, get_report_public(report_id)
        except ReportNotFound:
            return 404, {"detail": "report not found"}

    if route == "/api/v1/admin/dashboard":
        from app.services.dashboard import get_dashboard

        return 200, get_dashboard()

    if route == "/api/v1/admin/reports":
        # ?status= 는 쿼리스트링으로 전달된다(M-28c ①). 미지정이면 전체.
        status = (query.get("status") or [None])[0]
        return 200, list_reports(status)

    if route.startswith("/api/v1/admin/reports/"):
        report_id = _path_id(route, 5, segments=6)
        if report_id is None:
            return 404, {"detail": f"relay: 잘못된 report_id 경로 {route}"}
        try:
            return 200, get_report_detail(report_id)
        except ReportNotFound:
            return 404, {"detail": "report not found"}

    return 404, {"detail": f"relay: 디스패치 대상 아님 GET {route}"}


def dispatch(
    method: str,
    path: str,
    body: dict,
    relay_meta: dict | None = None,
    identity: dict | None = None,
) -> tuple[int, object]:
    """릴레이 item 을 로컬 처리. (status_code, body). 예외는 호출부가 5xx 로 변환한다.

    relay_meta 는 trace.relay 계측용으로만 쓰이고 응답 body 에는 들어가지 않는다.
    identity(M-28b ②) = edge 가 검증해 넘긴 {wid, tenant} — 서비스 함수의 worker_id 로 소비.
    """
    worker_id = (identity or {}).get("wid")

    # M-28c ①: method 축 — GET 조회(§3 공개면 계약분)도 릴레이로 디스패치한다.
    # 쿼리스트링은 path 에 실려 오므로 여기서 분리한다(relay.py 무접촉 — 시그니처 변경 없음).
    split = urlsplit(path)
    route, query = split.path, parse_qs(split.query)

    if method == "GET":
        return _dispatch_get(route, query)

    if method == "POST" and path == "/api/v1/ask":
        from app.agents.graph import run_ask

        result = run_ask(
            body.get("question", ""), body.get("lang", "vi"),
            worker_id=worker_id, relay_meta=relay_meta
        )
        return 200, {
            "answer": result.answer,
            "sources": result.sources,
            "verify": result.verify,
            "trace_id": result.trace_id,
        }
    if method == "POST" and path == "/api/v1/reports":
        # M-08b ①: LLM 비의존 결정론 접수. 라우터 재호출 없이 저장소 함수를 직접 부른다.
        from app.services.risk_reports import submit_text_report

        return 202, submit_text_report(
            body.get("original_text", ""),
            lang=body.get("lang"),
            source=body.get("source", "text"),
            worker_id=worker_id,
        )
    if method == "POST" and path.startswith("/api/v1/reports/") and path.endswith("/confirm"):
        # M-08c 확인 루프 — actor 는 identity.wid 에서 도출(M-28b ②)
        from app.services.risk_reports import ReportNotFound, confirm

        try:
            report_id = int(path.split("/")[4])
        except (IndexError, ValueError):
            return 404, {"detail": f"relay: 잘못된 report_id 경로 {path}"}
        try:
            return 200, confirm(
                report_id, body.get("result", ""), body.get("corrected_text"), worker_id
            )
        except ReportNotFound:
            return 404, {"detail": "report not found"}
    if method == "POST" and path in ("/api/v1/auth/activate", "/api/v1/auth/login"):
        # M-15: 신원·DB 는 core 소유. 라우터 재호출 없이 서비스 함수를 직접 부른다.
        from app.services import auth as auth_service

        try:
            if path.endswith("/activate"):
                result = auth_service.activate(body.get("token", ""), body.get("pin", ""))
            else:
                result = auth_service.login(body.get("emp_no", ""), body.get("pin", ""))
        except auth_service.AuthError:
            # 사유를 응답으로 구분하지 않는다(계정·토큰 존재 여부 비노출)
            return 401, {"detail": auth_service.AUTH_FAILED_MESSAGE}
        return 200, result
    if method == "POST" and route.startswith("/api/v1/admin/reports/") and route.endswith(
        ("/ack", "/resolve")
    ):
        # M-28c ①: §3 관리자 블록 등재 전이도 공개면 계약분 — 동일 처리.
        # actor 는 core 가 결정한다 — risk_reports.ADMIN_ACTOR_UNAUTHENTICATED 단일 주입 지점(M-15b).
        from app.services.risk_reports import (
            ReportNotFound,
            TransitionError,
            acknowledge,
            resolve,
        )

        report_id = _path_id(route, 5, segments=7)
        if report_id is None:
            return 404, {"detail": f"relay: 잘못된 report_id 경로 {route}"}
        try:
            if route.endswith("/ack"):
                return 200, acknowledge(report_id)
            return 200, resolve(report_id, body.get("note"))
        except ReportNotFound:
            return 404, {"detail": "report not found"}
        except TransitionError as exc:
            return 422, {"detail": str(exc)}
    return 404, {"detail": f"relay: 디스패치 대상 아님 {method} {path}"}


async def handle_item(client: httpx.AsyncClient, item: dict) -> None:
    request_id = item.get("request_id", "")
    try:
        relay_meta = {
            "enqueued_at": item.get("enqueued_at"),
            "leased_at": item.get("leased_at"),
        }
        status_code, body = await asyncio.to_thread(
            dispatch,
            item.get("method", ""),
            item.get("path", ""),
            item.get("body") or {},
            relay_meta,
            item.get("identity"),      # M-28b ②
        )
    except Exception as exc:  # noqa: BLE001 — 개별 실패가 루프를 끊지 않는다
        log.error("relay poller: 디스패치 실패 request_id=%s %s: %s", request_id, type(exc).__name__, exc)
        status_code, body = 500, {"detail": "처리 중 오류가 발생했습니다.", "error": type(exc).__name__}

    try:
        r = await client.post(
            f"{edge_api_url()}/internal/relay/{request_id}/respond",
            json={"status_code": status_code, "body": body},
            timeout=RESPOND_TIMEOUT_S,
        )
        if r.status_code == 404:
            log.warning("relay poller: respond 404 (만료·미지 request_id) %s", request_id)
    except Exception as exc:  # noqa: BLE001
        log.error("relay poller: respond 실패 request_id=%s %s", request_id, type(exc).__name__)


async def poll_once(client: httpx.AsyncClient) -> int:
    """1회 long-poll + 배치 처리. 처리 건수 반환."""
    r = await client.get(
        f"{edge_api_url()}/internal/relay/pending",
        timeout=hold_s() + RESPOND_TIMEOUT_S,
    )
    r.raise_for_status()
    items = r.json().get("items", [])
    for item in items:
        await handle_item(client, item)
    return len(items)


async def run_poller(stop: asyncio.Event) -> None:
    """기동~종료까지 반복. 연결 실패는 1s→10s 백오프 후 재접속."""
    backoff = BACKOFF_MIN_S
    log.info("relay poller: 시작 (edge=%s)", edge_api_url())
    async with httpx.AsyncClient() as client:
        while not stop.is_set():
            try:
                await poll_once(client)
                backoff = BACKOFF_MIN_S
            except Exception as exc:  # noqa: BLE001 — 연결 실패·타임아웃 모두 재시도 대상
                log.warning(
                    "relay poller: 폴링 실패 %s — %ss 후 재접속", type(exc).__name__, backoff
                )
                try:
                    await asyncio.wait_for(stop.wait(), timeout=backoff)
                except asyncio.TimeoutError:
                    pass
                backoff = min(backoff * 2, BACKOFF_MAX_S)
    log.info("relay poller: 정상 종료")
