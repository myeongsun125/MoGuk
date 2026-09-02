"""문서 업로드 저장소 — 접수·자동 적재 잡 (M-41). [새봄]

POST /admin/documents 계약(총괄 확정 0902):
- 요청 JSON {title, category, text, filename?} — multipart 아님, 신규 의존성 없음.
- category 는 001:32 CHECK 집합('process','instruction','safety','equipment') 4종만 — 그 외 422.
- documents INSERT: origin='upload', source='upload:'+filename.
  filename 부재 시 source='upload:manual' (SB 자체결정 — 총괄 확정 0902).
- jobs INSERT: kind='ingest_document', payload={document_id, text(원문 무변형)}.
- 응답 202 {id, job_id}. text 빈 값·category 이탈은 422 — 저장소 호출 전에 거절.

적재(청킹·임베딩·chunks INSERT)는 workers/job_runner._handle_ingest_document 가 비동기 수행.
컬럼·값 집합은 db/migrations/001_tenant_template.sql 이 정본(R4).
"""

from __future__ import annotations

import json
import logging
import re

from app.services import tenancy

log = logging.getLogger(__name__)

CATEGORY_VALUES = ("process", "instruction", "safety", "equipment")   # 001:32 CHECK 동일
JOB_KIND_INGEST_DOCUMENT = "ingest_document"
DEFAULT_SOURCE = "upload:manual"   # filename 부재 시 (총괄 확정 0902)


class InvalidDocument(Exception):
    """text 빈 값·category 집합 이탈 — 라우터가 422 로 변환."""


_INSERT_DOCUMENT = """
INSERT INTO documents (title, category, origin, source, version, masked)
VALUES (%(title)s, %(category)s, 'upload', %(source)s, 1, false)
RETURNING id
"""

_INSERT_JOB = """
INSERT INTO jobs (kind, payload) VALUES (%(kind)s, %(payload)s::jsonb) RETURNING id
"""


def create_document(
    title: str, category: str, text: str, filename: str | None = None
) -> dict:
    """접수 → {"id", "job_id"}. documents 1행 + ingest_document 잡 1행을 한 트랜잭션으로.

    LLM·임베딩을 호출하지 않는다 — 적재는 잡이 담당(접수는 결정론 경로, M-08b ① 동형).
    """
    if not (text or "").strip():
        raise InvalidDocument("text 는 비어 있을 수 없습니다")
    if category not in CATEGORY_VALUES:
        raise InvalidDocument(f"category 는 {list(CATEGORY_VALUES)} 중 하나여야 합니다")
    source = f"upload:{filename}" if (filename or "").strip() else DEFAULT_SOURCE

    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                _INSERT_DOCUMENT,
                {"title": title, "category": category, "source": source},
            )
            doc_id = cur.fetchone()[0]
            cur.execute(
                _INSERT_JOB,
                {
                    "kind": JOB_KIND_INGEST_DOCUMENT,
                    "payload": json.dumps(
                        {"document_id": doc_id, "text": text}, ensure_ascii=False
                    ),
                },
            )
            job_id = cur.fetchone()[0]
        conn.commit()

    log.info("documents: 업로드 접수 id=%s job=%s source=%s", doc_id, job_id, source)
    return {"id": doc_id, "job_id": job_id}


# ── 목록 (M-41 ③) ─────────────────────────────────────────

LIST_KEYS = (
    "id", "title", "category", "origin", "source", "created_at", "chunk_count", "job_status",
)

# chunk_count·job_status 는 조인(스칼라 서브쿼리)으로 채운다. job_status 는 해당 문서를
# 가리키는 ingest_document 잡의 최신 상태 — 잡이 없는 기존 문서(seed·admin_answer)는
# null (계약 외 — 자결, 보고 등재). 최신순 = id DESC.
_LIST_DOCUMENTS = """
SELECT d.id, d.title, d.category, d.origin, d.source, d.created_at,
       (SELECT count(*) FROM chunks c WHERE c.document_id = d.id) AS chunk_count,
       (SELECT j.status FROM jobs j
         WHERE j.kind = 'ingest_document'
           AND (j.payload ->> 'document_id')::int = d.id
         ORDER BY j.id DESC LIMIT 1) AS job_status
FROM documents d
ORDER BY d.id DESC
"""


def _iso(value):
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def list_documents() -> list[dict]:
    """관리자 문서 목록 — 8필드, 최신순(id DESC). 읽기 전용."""
    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_LIST_DOCUMENTS)
            rows = cur.fetchall()
    out = []
    for r in rows:
        row = dict(zip(LIST_KEYS, r))
        row["created_at"] = _iso(row["created_at"])
        row["chunk_count"] = int(row["chunk_count"] or 0)
        out.append(row)
    return out


# ── 청킹 (M-41 ②) ─────────────────────────────────────────
# 기존 청킹은 scripts/ingest_seed.py(_split_800·make_chunks)에만 있고 앱 이미지는
# backend/ 단독이라 임포트 불가 — 앱 계층에 재작성. 분할 규칙은 총괄 확정 0902.

CHUNK_MAX_CHARS = 800

# 문장 경계 = 마침표·줄바꿈(총괄 확정 0902). 경계 문자를 앞 문장에 붙여 자른다 —
# 이어 붙이면 원문과 동일(내용 소실·변형 없음).
_SENTENCE_RE = re.compile(r"[^.\n]*[.\n]|[^.\n]+$")


def _split_oversize(block: str) -> list[str]:
    """800자 초과 블록 — 문장 경계(마침표·줄바꿈)로 누적 분할, 오버랩 없음(총괄 확정 0902).

    문장 경계가 전혀 없는 초장문은 800자 고정 절단(현행 유지). 문장 중간은 자르지 않는다.
    """
    parts: list[str] = []
    buf = ""
    for seg in _SENTENCE_RE.findall(block):
        while len(seg) > CHUNK_MAX_CHARS:      # 경계 없는 초장문 — 800자 고정 절단
            if buf:
                parts.append(buf)
                buf = ""
            parts.append(seg[:CHUNK_MAX_CHARS])
            seg = seg[CHUNK_MAX_CHARS:]
        if buf and len(buf) + len(seg) > CHUNK_MAX_CHARS:
            parts.append(buf)
            buf = seg
        else:
            buf += seg
    if buf:
        parts.append(buf)
    return parts


def split_document(text: str) -> list[str]:
    """빈 줄·마크다운 제목(#…)을 경계로 800자 이하 청크. 비어 있지 않으면 최소 1개.

    경계마다 청크를 끊는다(블록 병합 없음 — 계약 문면 그대로). 제목 줄은 다음 블록의
    머리로 붙인다. 800자 초과 블록은 문장 경계(마침표·줄바꿈)로 나눈다(총괄 확정 0902).
    """
    blocks: list[str] = []
    cur: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            if cur:
                blocks.append("\n".join(cur))
                cur = []
            if stripped.startswith("#"):
                cur = [line]                      # 제목은 다음 블록의 머리
            continue
        cur.append(line)
    if cur:
        blocks.append("\n".join(cur))

    parts: list[str] = []
    for b in blocks:
        if len(b) <= CHUNK_MAX_CHARS:
            parts.append(b)
        else:
            parts.extend(_split_oversize(b))
    parts = [p for p in parts if p.strip()]
    if not parts and (text or "").strip():        # 안전망 — 접수 검증상 도달하지 않는 경로
        parts = [(text or "").strip()[:CHUNK_MAX_CHARS]]
    return parts
