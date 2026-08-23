"""/ask — 질의 (agents/graph 엔트리). 현재 fixture mock 응답 (§7 Mock 경계). [새봄]

mock 응답에는 "mock": true 가 포함된다 — 실연동 교체 시 제거하고 grep으로 잔여 확인.
"""

import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/ask", tags=["ask"])

_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "ask.json"


@router.post("")
def ask(body: dict) -> dict:
    # {question, lang} → {answer, sources[], verify:{score,passed,gated}, trace_id}
    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    fixture["echo"] = {"question": body.get("question"), "lang": body.get("lang")}
    return fixture


@router.post("/voice")
def ask_voice() -> dict:
    # multipart(audio≤60s, lang) → /ask 와 동일 | STT 15s timeout 시 폴백 안내 응답 (§5)
    raise NotImplementedError("[새봄] POST /ask/voice")
