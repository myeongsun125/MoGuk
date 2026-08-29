"""/ask — 질의. edge 는 릴레이 큐로 넘기고, core 는 그래프를 직접 실행한다. [새봄]

skeleton-v3 §3: POST /ask {question, lang} → {answer, sources[], verify:{score,passed,gated}, trace_id}
- API_ROLE=edge: enqueue(내부 함수) → respond 대기 → 원 응답 완결 (M-28·M-28a). 응답 스키마 무변경.
- API_ROLE=core: run_ask 직접 호출 — core 폴러도 같은 함수를 쓰며 HTTP 재귀는 없다.
mock 은 V2-2 에서 제거됨 — backend/app/fixtures/ask.json 은 프론트 fixture 동기화 기준으로 남겨둔다.
"""

import asyncio

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.agents.graph import run_ask
from app.routers.auth import optional_identity
from app.services.relay import queue
from app.services.system_service import role

router = APIRouter(prefix="/ask", tags=["ask"])

PATH = "/api/v1/ask"


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    lang: str = Field(default="vi")


def _payload(result) -> dict:
    return {
        "answer": result.answer,
        "sources": result.sources,
        "verify": result.verify,
        "trace_id": result.trace_id,
    }


@router.post("")
async def ask(
    body: AskRequest, identity: dict | None = Depends(optional_identity)
) -> JSONResponse:
    if role() == "edge":
        item = queue.enqueue("POST", PATH, body.model_dump(), identity)
        relayed = await queue.wait_for_response(item)
        return JSONResponse(status_code=relayed["status_code"], content=relayed["body"])

    # M-28b ②: identity 가 있으면 worker_id 로 소비, 없으면 None(미인증 경로 ④)
    result = await asyncio.to_thread(
        run_ask, body.question, body.lang, (identity or {}).get("wid")
    )
    return JSONResponse(status_code=200, content=_payload(result))


@router.post("/voice")
def ask_voice() -> dict:
    # multipart(audio≤60s, lang) → /ask 와 동일 | STT 15s timeout 시 폴백 안내 응답 (§5)
    raise NotImplementedError("[새봄] POST /ask/voice")
