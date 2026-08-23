"""/chat — 정착지원 상담 (M-07). 로컬 티어 고정. [새봄]"""

from fastapi import APIRouter

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("")
def chat(body: dict) -> dict:
    # {message} → {reply}
    raise NotImplementedError("[새봄] POST /chat")
