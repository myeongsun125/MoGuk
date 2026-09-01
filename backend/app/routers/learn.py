"""/learn — 학습카드·퀴즈 (modules/learning, M-38). [새봄]

GET  /learn/quiz/{set_id}?lang=        문항 조회 — answer_idx 미노출(§3:221)
POST /learn/quiz/{set_id}/submit       {answers[]} → {score, passed, label} (§3:222)
lang 미지정 → Bearer 근로자 lang(optional_identity — 미인증이면 ko), 지정 → vi·in 외 ko 폴백.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.routers.auth import optional_identity
from app.services import quiz

router = APIRouter(prefix="/learn", tags=["learn"])


@router.get("/cards")
def cards(module: str | None = None) -> dict:
    raise NotImplementedError("[새봄] GET /learn/cards?module=")


@router.get("/quiz/{set_id}")
async def get_quiz(
    set_id: int,
    lang: str | None = None,
    identity: dict | None = Depends(optional_identity),
) -> JSONResponse:
    """{set_id, module, title, status, items[{id, q, choices[], term_hints[]}]} (M-38).

    status 는 그대로 반환(draft 포함) — 화면 라벨 문구는 JH 몫, 서버는 만들지 않는다.
    """
    try:
        result = await asyncio.to_thread(
            quiz.get_quiz, set_id, lang, (identity or {}).get("wid")
        )
    except quiz.QuizSetNotFound:
        raise HTTPException(status_code=404, detail="quiz set not found") from None
    return JSONResponse(status_code=200, content=result)


class SubmitRequest(BaseModel):
    answers: list[int]


@router.post("/quiz/{set_id}/submit")
async def submit_quiz(
    set_id: int,
    body: SubmitRequest,
    identity: dict | None = Depends(optional_identity),
) -> JSONResponse:
    """{answers[]} → {score, passed, label} + quiz_attempts 1행 (M-38).

    통과 판정 = tenant_settings.threshold_pass(행 부재 시 90). worker_id 는 Bearer 에서
    도출(M-28b) — 미인증이면 NULL 기록. 길이·범위 위반은 422.
    """
    try:
        result = await asyncio.to_thread(
            quiz.submit_quiz, set_id, body.answers, (identity or {}).get("wid")
        )
    except quiz.QuizSetNotFound:
        raise HTTPException(status_code=404, detail="quiz set not found") from None
    except quiz.InvalidAnswers as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return JSONResponse(status_code=200, content=result)
