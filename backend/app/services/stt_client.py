"""STT 클라이언트 — faster-whisper 컨테이너 POST /v1/transcribe (M-18). 동기 15s 폴백. [새봄]"""

from dataclasses import dataclass


@dataclass(frozen=True)
class STT:
    text: str
    language: str
    confidence: float
    duration_ms: int


def transcribe(audio: bytes, lang_hint: str | None = None) -> STT:
    raise NotImplementedError("[새봄] services.stt_client.transcribe")
