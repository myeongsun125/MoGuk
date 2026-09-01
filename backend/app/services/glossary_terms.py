"""glossary_terms.py — 용어집 로더 (주입 하네스 공용, 총괄 확정 0901). [새봄]

DB glossary(테넌트 스키마, tenancy 경유)에서 term_ko·term_vi·term_in 을 읽는다.

- status 필터 = env GLOSSARY_STATUS 집합(쉼표 구분, 기본 "approved,draft").
- 요청당 1회 조회 + 프로세스 캐시 60s(만료 기반). 모듈 전역 dict 갱신은
  이 레포의 다른 모듈 전역 패턴과 동일하게 락 없이 둔다(GIL 하 원자적 교체,
  최악의 경합도 중복 조회 1회뿐).
- 순서 = ORDER BY id — 시드 적재(ingest_seed)가 glossary_50.json 파일 순서로
  넣으므로 실험 사본의 "용어집 순서"와 일치한다.
- 조회 실패는 예외를 그대로 올린다 — fail-open(주입 생략) 판단은 호출부 몫.
"""

from __future__ import annotations

import logging
import os
import time

from app.services import tenancy

log = logging.getLogger(__name__)

STATUS_ENV = "GLOSSARY_STATUS"
DEFAULT_STATUSES = ("approved", "draft")
CACHE_TTL_S = 60.0

_SQL = """
SELECT term_ko, term_vi, term_in
FROM glossary
WHERE status = ANY(%(statuses)s)
ORDER BY id
"""

_cache: dict = {"at": 0.0, "key": None, "terms": ()}


def statuses() -> tuple[str, ...]:
    """GLOSSARY_STATUS 파싱 — 빈 값·공백뿐이면 기본 집합."""
    raw = os.getenv(STATUS_ENV)
    if not raw:
        return DEFAULT_STATUSES
    tokens = tuple(t.strip() for t in raw.split(",") if t.strip())
    return tokens or DEFAULT_STATUSES


def invalidate() -> None:
    """캐시 강제 만료 — 테스트·수동 갱신용."""
    _cache.update(at=0.0, key=None, terms=())


def fetch_terms() -> tuple[tuple[str, str | None, str | None], ...]:
    """(term_ko, term_vi, term_in) 튜플 나열 — status 집합 필터, 60s 캐시."""
    key = statuses()
    now = time.monotonic()
    if _cache["key"] == key and now - _cache["at"] < CACHE_TTL_S:
        return _cache["terms"]
    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_SQL, {"statuses": list(key)})
            rows = cur.fetchall()
    terms = tuple((r[0], r[1], r[2]) for r in rows)
    _cache.update(at=now, key=key, terms=terms)
    return terms
