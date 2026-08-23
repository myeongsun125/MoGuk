"""/auth — 초대 토큰 → PIN → JWT+리프레시 (M-15). [새봄]"""

from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/activate")
def activate(body: dict) -> dict:
    # {token, pin} → {jwt, refresh}
    raise NotImplementedError("[새봄] POST /auth/activate")


@router.post("/login")
def login(body: dict) -> dict:
    # {emp_no, pin} → {jwt, refresh}
    raise NotImplementedError("[새봄] POST /auth/login")


@router.post("/admin/login")
def admin_login(body: dict) -> dict:
    # {email, pw}
    raise NotImplementedError("[새봄] POST /auth/admin/login")
