"""퀴즈 저장소 — 문항 조회 (M-38). [새봄]

GET /learn/quiz/{set_id} 계약(§3:221):
- 응답 {set_id, module, title, status, items[{id, q, choices[], term_hints[{term_ko, term_lang}]}]}
- lang 해석: vi→q_vi·choices_vi / in→q_in·choices_in / 해당 값 부재(키 없음·null·빈 값) 시 ko 폴백.
  lang 쿼리 미지정이면 Bearer 근로자의 workers.lang, 그것도 없으면 ko. vi·in 외 값은 ko.
- ★answer_idx 미노출 — 응답 조립이 화이트리스트 방식이라 새 키가 새지 않는다.
- term_hints = q_ko 에 포함된 용어집 항목(NFC+casefold 부분 문자열 — verify._norm 동형).
  term_lang 은 해석 언어의 용어(vi→term_vi, in→term_in, ko→term_ko), 대상어 NULL 이면 term_ko.
- status 는 그대로 반환(draft 포함) — 화면 라벨 문구는 JH 몫.

컬럼·값 집합은 db/migrations/001_tenant_template.sql 이 정본(R4).
"""

from __future__ import annotations

import json
import logging
import unicodedata

from app.services import glossary_terms, tenancy

log = logging.getLogger(__name__)

LANGS = ("vi", "in")               # 001 workers.lang CHECK 집합

_SELECT_SET = "SELECT id, module, title, status FROM quiz_sets WHERE id = %(id)s"
_SELECT_ITEMS = "SELECT id, body FROM quiz_items WHERE quiz_set_id = %(id)s ORDER BY id"
_SELECT_WORKER_LANG = "SELECT lang FROM workers WHERE id = %(id)s"


class QuizSetNotFound(Exception):
    """대상 세트 없음 — 라우터가 404 로 변환."""


def _norm(s: str) -> str:
    """NFC + casefold — agents/verify._norm 과 동일 규칙(매칭 축 단일화)."""
    return unicodedata.normalize("NFC", s or "").casefold()


def _resolve_lang(cur, lang: str | None, worker_id: int | None) -> str:
    """해석 언어 결정 — 지정값 우선(vi·in 외는 ko), 미지정은 Bearer 근로자 lang, 둘 다 없으면 ko."""
    if lang is not None:
        return lang if lang in LANGS else "ko"
    if worker_id is not None:
        cur.execute(_SELECT_WORKER_LANG, {"id": worker_id})
        row = cur.fetchone()
        if row is not None and row[0] in LANGS:
            return row[0]
    return "ko"


def _pick(body: dict, lang_key: str, ko_key: str):
    """lang 축 값이 부재(키 없음·null·빈 값)면 ko 폴백."""
    v = body.get(lang_key)
    return v if v not in (None, "", []) else body.get(ko_key)


def _term_hints(q_ko: str, lang: str) -> list[dict]:
    """q_ko 에 포함된 용어집 항목 — 조회 실패는 힌트 생략(fail-open, 주입 하네스 동형)."""
    try:
        terms = glossary_terms.fetch_terms()
    except Exception as exc:  # noqa: BLE001 — 힌트는 보강이라 조회 실패가 조회 본문을 막지 않는다
        log.warning("quiz: 용어집 조회 실패 — term_hints 생략: %s", type(exc).__name__)
        return []
    hay = _norm(q_ko)
    hints = []
    for term_ko, term_vi, term_in in terms:
        if _norm(term_ko) and _norm(term_ko) in hay:
            if lang == "vi":
                target = term_vi or term_ko            # 대상어 NULL → ko 폴백
            elif lang == "in":
                target = term_in or term_ko
            else:
                target = term_ko                       # ko 해석 — term_lang = term_ko 그대로
            hints.append({"term_ko": term_ko, "term_lang": target})
    return hints


def _item_body(raw) -> dict:
    return json.loads(raw) if isinstance(raw, str) else raw


def get_quiz(set_id: int, lang: str | None = None, worker_id: int | None = None) -> dict:
    """문항 조회 — 응답은 계약 키 화이트리스트로만 조립(answer_idx·explain_ko 미노출)."""
    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_SET, {"id": set_id})
            row = cur.fetchone()
            if row is None:
                raise QuizSetNotFound(f"quiz_set_id={set_id}")
            _, module, title, status = row

            eff_lang = _resolve_lang(cur, lang, worker_id)

            cur.execute(_SELECT_ITEMS, {"id": set_id})
            item_rows = cur.fetchall()

    items = []
    for item_id, raw in item_rows:
        body = _item_body(raw)
        if eff_lang == "vi":
            q = _pick(body, "q_vi", "q_ko")
            choices = _pick(body, "choices_vi", "choices")
        elif eff_lang == "in":
            q = _pick(body, "q_in", "q_ko")
            choices = _pick(body, "choices_in", "choices")
        else:
            q, choices = body.get("q_ko"), body.get("choices")
        items.append({
            "id": item_id,
            "q": q,
            "choices": list(choices or []),
            "term_hints": _term_hints(body.get("q_ko") or "", eff_lang),
        })

    return {"set_id": set_id, "module": module, "title": title, "status": status, "items": items}
