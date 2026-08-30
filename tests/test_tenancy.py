"""tenancy.connect 의 search_path 설정 단정 (M-04·M-04b·M-04c). [새봄]

기존 테스트는 전부 tenancy.connect 자체를 monkeypatch 해 대체했기 때문에 connect() 본문이
한 번도 실행되지 않았다 — M-04b(DDL)만 고치고 런타임을 놓친 결함(EC2 retrieve 전건 실패,
::vector 미해석)이 스위트를 통과한 이유다. 여기서는 psycopg 를 sys.modules 에 주입해
connect() 본문을 실제로 돌리고, 실행되는 SET 문을 캡처해 단정한다.

핵심 계약(M-04c):
- 순서 = tenant_{slug} 먼저, public 이 후순위. public 은 확장 타입(vector 등) 해석 전용.
- 두 식별자는 각각 quote — 스키마명을 문자열 연결로 끼워 넣지 않는다(인젝션 여지 금지).
"""

import sys
import types

import pytest

from app.services import tenancy

DSN = "postgresql://test:test@127.0.0.1:1/test"


# ── psycopg 스텁 (psycopg.sql 의미를 그대로 흉내낸다) ────────

class _Ident:
    """psycopg.sql.Identifier — 렌더링 시 큰따옴표로 quote 된다."""

    def __init__(self, name):
        self.name = name

    def render(self):
        return '"%s"' % self.name.replace('"', '""')


class _SQL:
    """psycopg.sql.SQL — 템플릿의 {} 를 위치 인자로 치환한다."""

    def __init__(self, template):
        self.template = template
        self.args = ()

    def format(self, *args):
        self.args = args
        return self

    def render(self):
        out = self.template
        for a in self.args:
            out = out.replace("{}", a.render() if isinstance(a, _Ident) else str(a), 1)
        return out


class _Cursor:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, query, params=None):
        self.log.append(query)


class _Conn:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return _Cursor(self.log)


@pytest.fixture
def executed(monkeypatch):
    """connect() 가 실행한 SQL 객체 목록. connect() 본문을 실제로 돌린다."""
    log: list = []
    sql_mod = types.SimpleNamespace(SQL=_SQL, Identifier=_Ident)
    fake = types.ModuleType("psycopg")
    fake.sql = sql_mod
    fake.connect = lambda dsn: _Conn(log)
    monkeypatch.setitem(sys.modules, "psycopg", fake)
    monkeypatch.setitem(sys.modules, "psycopg.sql", sql_mod)
    monkeypatch.setenv("DATABASE_URL", DSN)
    monkeypatch.delenv("TENANT_SLUG", raising=False)
    return log


# ── M-04c 회귀 단정 ───────────────────────────────────────

def test_connect_sets_search_path_with_public_second(executed):
    """SET 문이 `{schema}, public` 순 — M-04b DDL 과 동일 순서(M-04c)."""
    with tenancy.connect():
        pass

    assert len(executed) == 1, executed
    stmt = executed[0].render()
    assert stmt == 'SET search_path TO "tenant_axis_demo", "public"', stmt


def test_public_is_second_not_first(executed):
    """순서 뒤집힘 회귀 방지 — 테넌트 스키마가 첫 번째, public 이 그 뒤."""
    with tenancy.connect("axis_demo"):
        pass

    stmt = executed[0].render()
    path = stmt.split("SET search_path TO ", 1)[1]
    first, second = [p.strip() for p in path.split(",")]
    assert first == '"tenant_axis_demo"'
    assert second == '"public"'
    assert path.index('"tenant_axis_demo"') < path.index('"public"'), stmt


def test_identifiers_are_quoted_separately_not_concatenated(executed):
    """스키마명은 Identifier 로만 전달 — 템플릿에 직접 끼워 넣지 않는다(인젝션 여지 금지)."""
    with tenancy.connect("axis_demo"):
        pass

    composed = executed[0]
    assert composed.template == "SET search_path TO {}, {}"
    assert "axis_demo" not in composed.template
    assert [type(a).__name__ for a in composed.args] == ["_Ident", "_Ident"]
    assert [a.name for a in composed.args] == ["tenant_axis_demo", "public"]


def test_slug_argument_and_env_both_reach_search_path(executed, monkeypatch):
    """명시 slug·TENANT_SLUG env 어느 쪽이든 tenant_{slug} 로 전개되고 public 은 유지."""
    with tenancy.connect("other_site"):
        pass
    assert executed[-1].render() == 'SET search_path TO "tenant_other_site", "public"'

    monkeypatch.setenv("TENANT_SLUG", "env_site")
    with tenancy.connect():
        pass
    assert executed[-1].render() == 'SET search_path TO "tenant_env_site", "public"'


def test_invalid_slug_still_rejected_before_connect(executed):
    """M-04 슬러그 형식 검증은 그대로 — public 추가가 검증을 우회시키지 않는다."""
    with pytest.raises(ValueError):
        with tenancy.connect("bad-slug; DROP SCHEMA public"):
            pass
    assert executed == []


def test_missing_database_url_raises(executed, monkeypatch):
    """DSN 부재 시 기존 RuntimeError 유지 — M-04c 가 기동 검증을 흐리지 않는다."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        with tenancy.connect():
            pass
    assert executed == []


# ── 실 psycopg 대조 (CI 에는 psycopg 존재, 로컬 미설치면 skip) ──

def test_real_psycopg_renders_same_statement(monkeypatch):
    """스텁이 psycopg.sql 의미와 어긋나지 않는지 실 라이브러리로 교차 확인."""
    psycopg = pytest.importorskip("psycopg")
    from psycopg import sql

    composed = sql.SQL("SET search_path TO {}, {}").format(
        sql.Identifier("tenant_axis_demo"), sql.Identifier("public")
    )
    try:
        rendered = composed.as_string(None)
    except TypeError:  # psycopg < 3.2 는 context 를 요구한다 — 그 경우 대조는 생략
        pytest.skip("psycopg %s: as_string(None) 미지원" % psycopg.__version__)
    assert rendered == 'SET search_path TO "tenant_axis_demo", "public"', rendered
