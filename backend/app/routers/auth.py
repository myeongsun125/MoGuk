"""/auth — 초대 토큰 → PIN → JWT+리프레시 (M-15). [새봄]

skeleton §3:
  POST /auth/activate {token, pin}  → {jwt, refresh}
  POST /auth/login    {emp_no, pin} → {jwt, refresh}
  POST /auth/admin/login {email, pw}            — 관리자, V3-2 범위 밖(스텁 유지)

역할 분기 (M-22): 신원·DB 는 core 소유 —
- API_ROLE=edge: activate/login 을 릴레이 큐로 넘긴다(edge 는 DB 자격이 없다).
- API_ROLE=core: services/auth 직접 호출. core 폴러도 같은 함수를 쓴다(HTTP 재귀 없음).
JWT 검증은 서명만으로 되므로 /auth/me·/auth/refresh 는 양쪽에서 로컬 처리한다.

실패 응답: 계정·토큰 존재 여부가 드러나지 않도록 **전부 동일한 401 + 동일 메시지**.

§3 미등재 엔드포인트 2종(아래) — 계약 확장이므로 M-xx 후보로 보고했다:
  POST /auth/refresh (리프레시 회전) · GET /auth/me (보호 엔드포인트 대표)
"""

import asyncio

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.services import auth as auth_service
from app.services.relay import queue
from app.services.system_service import role

router = APIRouter(prefix="/auth", tags=["auth"])

ACTIVATE_PATH = "/api/v1/auth/activate"
LOGIN_PATH = "/api/v1/auth/login"

_UNAUTHORIZED = HTTPException(
    status_code=401,
    detail=auth_service.AUTH_FAILED_MESSAGE,
    headers={"WWW-Authenticate": "Bearer"},
)


class ActivateRequest(BaseModel):
    token: str = Field(min_length=1)
    pin: str = Field(min_length=4, max_length=64)


class LoginRequest(BaseModel):
    emp_no: str = Field(min_length=1)
    pin: str = Field(min_length=1, max_length=64)


class RefreshRequest(BaseModel):
    refresh: str = Field(min_length=1)


async def _relay_or_local(path: str, body: dict, fn, *args):
    """edge 는 릴레이 큐로, core 는 로컬 호출. 실패는 동일 401 로 수렴."""
    if role() == "edge":
        item = queue.enqueue("POST", path, body)
        relayed = await queue.wait_for_response(item)
        return JSONResponse(status_code=relayed["status_code"], content=relayed["body"])
    try:
        result = await asyncio.to_thread(fn, *args)
    except auth_service.AuthError:
        raise _UNAUTHORIZED from None
    return JSONResponse(status_code=200, content=result)


@router.post("/activate")
async def activate(body: ActivateRequest) -> JSONResponse:
    return await _relay_or_local(
        ACTIVATE_PATH, body.model_dump(), auth_service.activate, body.token, body.pin
    )


@router.post("/login")
async def login(body: LoginRequest) -> JSONResponse:
    return await _relay_or_local(
        LOGIN_PATH, body.model_dump(), auth_service.login, body.emp_no, body.pin
    )


@router.post("/refresh")
def refresh(body: RefreshRequest) -> dict:
    """리프레시 회전 — 새 {jwt, refresh} 쌍. §3 미등재(계약 확장 후보)."""
    try:
        return auth_service.rotate(body.refresh)
    except auth_service.AuthError:
        raise _UNAUTHORIZED from None


def require_worker(authorization: str | None = Header(default=None)) -> dict:
    """보호 엔드포인트 의존성 — Bearer access 토큰 검증. 부재·위조·만료 전부 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _UNAUTHORIZED
    try:
        return auth_service.decode_token(authorization.split(" ", 1)[1].strip())
    except auth_service.AuthError:
        raise _UNAUTHORIZED from None


@router.get("/me")
def me(claims: dict = Depends(require_worker)) -> dict:
    """보호 엔드포인트 대표 — 토큰 클레임만 반환(DB 미접근이라 edge 에서도 동작).

    §3 미등재(계약 확장 후보). 전면 보호 전환은 이번 구간 범위 밖.
    """
    return {"worker_id": claims["wid"], "tenant": claims.get("tenant"), "typ": claims["typ"]}


@router.post("/admin/login")
def admin_login(body: dict) -> dict:
    # {email, pw} — 관리자 인증은 V3-2 범위 밖
    raise NotImplementedError("[새봄] POST /auth/admin/login")
