"""학습 카드 — phrase(안전 문구)·term(용어) 카드 조립 (M-42). [새봄]

GET /learn/cards?module=safety|learning&lang= 계약(총괄 확정 0902):
- module 미지정·safety/learning 외 값 → 422. lang 해석은 퀴즈 동형(quiz._resolve_lang 재사용):
  지정 vi/in 우선 → Bearer 근로자 lang → ko 폴백.
- 응답 {module, quiz_set_id, cards[{id, kind, text, text_ko, high_risk, note_ko?, src?}]}.
- quiz_set_id = 해당 module 의 quiz_sets 최신 id — 세트가 없으면 null(총괄 확정).
- safety = phrases 카드: 소스는 backend/app/data/phrases_10.json (M-42 대안 B —
  core-api 이미지가 backend/app 만 COPY 하므로 패키지 내 사본을 로드, 프로세스 캐시).
  id = 파일 순번 1부터(총괄 확정). DB 테이블·적재기 확장 없음, 001 무접촉.
- learning = glossary term 카드: glossary_terms.fetch_term_cards()(approved ∪ draft — env
  GLOSSARY_STATUS 동일 필터·동일 60s 캐시, 총괄 확정 0902). id = glossary.id,
  high_risk = false 고정, src 는 생략 확정(총괄).
- note_ko·src 는 값이 없는 항목에서 키 생략(계약).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.services import glossary_terms, quiz, tenancy

log = logging.getLogger(__name__)

MODULES = ("safety", "learning")           # quiz_sets.module 값 집합(001:51 주석)과 동일

_PHRASES_PATH = Path(__file__).resolve().parents[1] / "data" / "phrases_10.json"

_SELECT_LATEST_SET = """
SELECT id FROM quiz_sets WHERE module = %(module)s ORDER BY id DESC LIMIT 1
"""


class InvalidModule(Exception):
    """module 미지정·집합 이탈 — 라우터가 422 로 변환."""


# 프로세스 캐시 — 시드 사본은 이미지에 고정이라 만료 축 불필요(재기동 시 갱신).
_cache: dict = {"phrases": None}


def _read_phrases_file() -> list[dict]:
    """파일 실독 — 캐시 미스에서만 호출된다(테스트가 이 함수로 재독 여부를 계수)."""
    return json.loads(_PHRASES_PATH.read_text(encoding="utf-8"))


def phrases() -> list[dict]:
    if _cache["phrases"] is None:
        _cache["phrases"] = _read_phrases_file()
    return _cache["phrases"]


def invalidate_cache() -> None:
    """테스트·수동 갱신용."""
    _cache["phrases"] = None


def _pick_text(item: dict, lang_key: str | None) -> str | None:
    """lang 축 값 부재(키 없음·null·빈 값) 시 ko 폴백 — quiz._pick 규칙 동형(로컬 사본)."""
    if lang_key:
        v = item.get(lang_key)
        if v not in (None, "", []):
            return v
    return item.get("text_ko")


def _phrase_cards(lang: str) -> list[dict]:
    lang_key = {"vi": "text_vi", "in": "text_in"}.get(lang)
    cards = []
    for idx, p in enumerate(phrases(), 1):             # id = 파일 순번, 1부터(총괄 확정)
        text = _pick_text(p, lang_key)
        card = {
            "id": idx,
            "kind": "phrase",
            "text": text,
            "text_ko": p.get("text_ko"),
            "high_risk": bool(p.get("high_risk", False)),
        }
        if p.get("note") not in (None, ""):
            card["note_ko"] = p["note"]
        if p.get("src") not in (None, ""):
            card["src"] = p["src"]
        cards.append(card)
    return cards


def _term_cards(lang: str) -> list[dict]:
    cards = []
    for term_id, term_ko, term_vi, term_in, note in glossary_terms.fetch_term_cards():
        if lang == "vi":
            text = term_vi or term_ko                  # 대상어 부재 시 ko 폴백(퀴즈 동형)
        elif lang == "in":
            text = term_in or term_ko
        else:
            text = term_ko
        card = {
            "id": term_id,
            "kind": "term",
            "text": text,
            "text_ko": term_ko,
            "high_risk": False,                        # 계약 고정
        }
        if note not in (None, ""):
            card["note_ko"] = note
        cards.append(card)                             # src — glossary 에 컬럼 없음 → 생략
    return cards


def get_cards(module: str | None, lang: str | None = None, worker_id: int | None = None) -> dict:
    """카드 목록 조립 — 읽기 전용(쓰기·이벤트 없음)."""
    if module not in MODULES:
        raise InvalidModule(f"module 은 {list(MODULES)} 중 하나여야 합니다")

    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            eff_lang = quiz.resolve_lang(cur, lang, worker_id)   # 퀴즈 공용 위임 재사용(M-42 지시)
            cur.execute(_SELECT_LATEST_SET, {"module": module})
            row = cur.fetchone()
    quiz_set_id = row[0] if row is not None else None   # 세트 없음 → null(총괄 확정)

    cards = _phrase_cards(eff_lang) if module == "safety" else _term_cards(eff_lang)
    return {"module": module, "quiz_set_id": quiz_set_id, "cards": cards}
