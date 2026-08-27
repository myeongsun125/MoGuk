"""/ask — 질의 (agents/graph 엔트리). V2-2 실구현. [새봄]

skeleton-v3 §3: POST /ask {question, lang} → {answer, sources[], verify:{score,passed,gated}, trace_id}
mock 은 제거됨 — backend/app/fixtures/ask.json 은 프론트 fixture 동기화 기준으로 남겨둔다(JH 소유 cutover).
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.agents.graph import run_ask

router = APIRouter(prefix="/ask", tags=["ask"])


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    lang: str = Field(default="vi")


@router.post("")
def ask(body: AskRequest) -> dict:
    # 인증(V3-2) 전이라 worker_id 는 미상 — questions.worker_id NULL 로 기록된다.
    result = run_ask(body.question, body.lang, worker_id=None)
    return {
        "answer": result.answer,
        "sources": result.sources,
        "verify": result.verify,
        "trace_id": result.trace_id,
    }


@router.post("/voice")
def ask_voice() -> dict:
    # multipart(audio≤60s, lang) → /ask 와 동일 | STT 15s timeout 시 폴백 안내 응답 (§5)
    raise NotImplementedError("[새봄] POST /ask/voice")
