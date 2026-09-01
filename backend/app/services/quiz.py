"""퀴즈 저장소 — 문항 조회·채점 (M-38). [새봄]

GET /learn/quiz/{set_id} 계약(§3:221):
- 응답 {set_id, module, title, status, items[{id, q, choices[], term_hints[{term_ko, term_lang}]}]}
- lang 해석: vi→q_vi·choices_vi / in→q_in·choices_in / 해당 값 부재(키 없음·null·빈 값) 시 ko 폴백.
  lang 쿼리 미지정이면 Bearer 근로자의 workers.lang, 그것도 없으면 ko. vi·in 외 값은 ko.
- ★answer_idx 미노출 — 응답 조립이 화이트리스트 방식이라 새 키가 새지 않는다.
- term_hints = q_ko 에 포함된 용어집 항목(NFC+casefold 부분 문자열 — verify._norm 동형).
  term_lang 은 해석 언어의 용어(vi→term_vi, in→term_in, ko→term_ko), 대상어 NULL 이면 term_ko.
- status 는 그대로 반환(draft 포함) — 화면 라벨 문구는 JH 몫.

POST /learn/quiz/{set_id}/submit 계약(§3:222):
- {answers[]} → {score(0~100 정수), passed(score ≥ threshold_pass), label}
- ★threshold_pass 는 tenant_settings key='threshold_pass' 에서 읽는다 — 행 부재·파싱 실패 시 90
  폴백(상수 하드코딩 금지, 총괄 명시). label 경계는 red<80 / yellow<90 / green 계약 고정 —
  v_comprehension(001:69) 경계와 동일하며 threshold 와 무관.
- quiz_attempts INSERT: detail = {"answers": [...], "correct": [정오 bool ...]}
- answers 길이 불일치·인덱스 범위 밖·비정수는 422 거절(계약 외 — 자결, 보고 등재)

컬럼·값 집합은 db/migrations/001_tenant_template.sql 이 정본(R4).
"""

from __future__ import annotations

import json
import logging
import unicodedata

from app.services import glossary_terms, tenancy

log = logging.getLogger(__name__)

LANGS = ("vi", "in")               # 001 workers.lang CHECK 집합

THRESHOLD_KEY = "threshold_pass"   # tenant_settings.key (M-01)
THRESHOLD_FALLBACK = 90            # 행 부재 시 폴백 — 총괄 명시(§3:222 괄호값)
LABEL_RED_BELOW = 80               # 계약 고정 경계 — v_comprehension(001:69)과 동일
LABEL_YELLOW_BELOW = 90

_SELECT_SET = "SELECT id, module, title, status FROM quiz_sets WHERE id = %(id)s"
_SELECT_ITEMS = "SELECT id, body FROM quiz_items WHERE quiz_set_id = %(id)s ORDER BY id"
_SELECT_WORKER_LANG = "SELECT lang FROM workers WHERE id = %(id)s"
_SELECT_THRESHOLD = "SELECT value FROM tenant_settings WHERE key = %(key)s"
_INSERT_ATTEMPT = """
INSERT INTO quiz_attempts (worker_id, quiz_set_id, score, passed, detail)
VALUES (%(worker_id)s, %(quiz_set_id)s, %(score)s, %(passed)s, %(detail)s::jsonb)
"""


class QuizSetNotFound(Exception):
    """대상 세트 없음 — 라우터가 404 로 변환."""


class InvalidAnswers(Exception):
    """answers 형식 위반(길이·범위·타입) — 라우터가 422 로 변환."""


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


# ── 채점 (§3:222) ─────────────────────────────────────────

def label_for(score: int) -> str:
    """red<80 / yellow<90 / green — 계약 고정, threshold 와 무관."""
    if score < LABEL_RED_BELOW:
        return "red"
    if score < LABEL_YELLOW_BELOW:
        return "yellow"
    return "green"


def _threshold(cur) -> int:
    """tenant_settings key='threshold_pass' — 행 부재·파싱 실패 시 90 폴백(하드코딩 금지)."""
    cur.execute(_SELECT_THRESHOLD, {"key": THRESHOLD_KEY})
    row = cur.fetchone()
    if row is None:
        return THRESHOLD_FALLBACK
    try:
        return int(row[0])
    except (TypeError, ValueError):
        log.warning("quiz: threshold_pass 값 해석 불가(%r) — 폴백 %s", row[0], THRESHOLD_FALLBACK)
        return THRESHOLD_FALLBACK


def submit_quiz(set_id: int, answers, worker_id: int | None = None) -> dict:
    """채점 + quiz_attempts 1행 — {score, passed, label}.

    worker_id 는 인증 컨텍스트에서 서버가 도출(M-28b 소비) — 미인증이면 NULL 기록.
    """
    if not isinstance(answers, list):
        raise InvalidAnswers("answers 는 배열이어야 합니다")

    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_SET, {"id": set_id})
            if cur.fetchone() is None:
                raise QuizSetNotFound(f"quiz_set_id={set_id}")

            cur.execute(_SELECT_ITEMS, {"id": set_id})
            bodies = [_item_body(raw) for _, raw in cur.fetchall()]
            if not bodies:
                raise InvalidAnswers(f"quiz_set_id={set_id} 에 문항이 없습니다")
            if len(answers) != len(bodies):
                raise InvalidAnswers(
                    f"answers 길이 {len(answers)} != 문항 수 {len(bodies)}"
                )
            for i, (a, body) in enumerate(zip(answers, bodies)):
                n = len(body.get("choices") or [])
                if isinstance(a, bool) or not isinstance(a, int) or not 0 <= a < n:
                    raise InvalidAnswers(f"answers[{i}]={a!r} — 0~{n - 1} 정수여야 합니다")

            correct = [a == body.get("answer_idx") for a, body in zip(answers, bodies)]
            score = round(sum(correct) * 100 / len(bodies))     # 0~100 정수 환산
            threshold = _threshold(cur)
            passed = score >= threshold

            cur.execute(
                _INSERT_ATTEMPT,
                {
                    "worker_id": worker_id,
                    "quiz_set_id": set_id,
                    "score": score,
                    "passed": passed,
                    "detail": json.dumps(
                        {"answers": answers, "correct": correct}, ensure_ascii=False
                    ),
                },
            )
        conn.commit()

    log.info("quiz: 채점 set=%s worker=%s score=%s passed=%s", set_id, worker_id, score, passed)
    return {"score": score, "passed": passed, "label": label_for(score)}
