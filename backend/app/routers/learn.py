"""/learn — 학습카드·퀴즈 (modules/learning). [새봄]"""

from fastapi import APIRouter

router = APIRouter(prefix="/learn", tags=["learn"])


@router.get("/cards")
def cards(module: str | None = None) -> dict:
    raise NotImplementedError("[새봄] GET /learn/cards?module=")


@router.post("/quiz/{set_id}/submit")
def submit_quiz(set_id: int, body: dict) -> dict:
    # {answers[]} → {score, passed, label}  (통과 판정 = tenant_settings.threshold_pass, M-01)
    raise NotImplementedError("[새봄] POST /learn/quiz/{set_id}/submit")
