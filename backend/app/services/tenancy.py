"""schema-per-tenant — 요청 컨텍스트에서 SET search_path TO tenant_{slug}, public (M-04·M-04c). [새봄]

DDL 원문 = db/migrations/001_tenant_template.sql (R4). 이 모듈은 접속·search_path 만 책임진다.

env:
- DATABASE_URL  core 역할 필수 (system_service.validate_env 가 기동 시 확인)
- TENANT_SLUG   현재 테넌트 슬러그. 기본 `axis_demo` (WORKORDER §4 MS V2-2 의 tenant_axis_demo).
  V3-2 인증 도입 전까지 요청에서 테넌트를 해석할 수단이 없어 프로세스 단위 값으로 둔다.
"""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from typing import Iterator

DEFAULT_TENANT_SLUG = "axis_demo"
_SLUG_RE = re.compile(r"^[a-z0-9_]+$")


def tenant_slug() -> str:
    return os.getenv("TENANT_SLUG") or DEFAULT_TENANT_SLUG


def tenant_schema(slug: str) -> str:
    """`tenant_{slug}` — 식별자로 쓰이므로 소문자/숫자/밑줄만 허용한다."""
    if not slug or not _SLUG_RE.match(slug):
        raise ValueError(f"tenant slug 형식 위반: {slug!r} (허용 = [a-z0-9_]+)")
    return f"tenant_{slug}"


@contextmanager
def connect(slug: str | None = None) -> Iterator["object"]:
    """테넌트 search_path 가 설정된 psycopg 커넥션. 컨텍스트 종료 시 커밋·닫힘."""
    import psycopg
    from psycopg import sql

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("required env DATABASE_URL is not set (see .env.example)")

    schema = tenant_schema(slug or tenant_slug())
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            # M-04c: {schema}, public 순 — public 은 확장 타입(vector 등) 해석 전용 후순위.
            # 001 DDL(M-04b)과 동일 순서. 두 식별자를 각각 quote 한다(문자열 연결 금지).
            cur.execute(
                sql.SQL("SET search_path TO {}, {}").format(
                    sql.Identifier(schema), sql.Identifier("public")
                )
            )
        yield conn
