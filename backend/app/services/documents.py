"""문서 업로드 저장소 — 접수·자동 적재 잡 (M-41). [새봄]

POST /admin/documents 계약(총괄 확정 0902):
- 요청 JSON {title, category, text, filename?} — multipart 아님, 신규 의존성 없음.
- category 는 001:32 CHECK 집합('process','instruction','safety','equipment') 4종만 — 그 외 422.
- documents INSERT: origin='upload', source='upload:'+filename.
  filename 부재 시 source='upload:direct' (계약 외 — 자결, 보고 등재).
- jobs INSERT: kind='ingest_document', payload={document_id, text(원문 무변형)}.
- 응답 202 {id, job_id}. text 빈 값·category 이탈은 422 — 저장소 호출 전에 거절.

적재(청킹·임베딩·chunks INSERT)는 workers/job_runner._handle_ingest_document 가 비동기 수행.
컬럼·값 집합은 db/migrations/001_tenant_template.sql 이 정본(R4).
"""

from __future__ import annotations

import json
import logging

from app.services import tenancy

log = logging.getLogger(__name__)

CATEGORY_VALUES = ("process", "instruction", "safety", "equipment")   # 001:32 CHECK 동일
JOB_KIND_INGEST_DOCUMENT = "ingest_document"
DEFAULT_SOURCE = "upload:direct"   # filename 부재 시 — 본문 직접 입력 표기(자결)


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


# ── 청킹 (M-41 ②) ─────────────────────────────────────────
# 기존 청킹은 scripts/ingest_seed.py(_split_800·make_chunks)에만 있고 앱 이미지는
# backend/ 단독이라 임포트 불가 — 줄 경계 분할 규칙 동형으로 재작성(자결, 보고 등재).

CHUNK_MAX_CHARS = 800


def _split_oversize(block: str) -> list[str]:
    """800자 초과 블록 — 줄 경계 누적 분할(_split_800 동형·오버랩 없음),
    줄바꿈 없는 초장문은 800자 고정 절단(자결)."""
    parts: list[str] = []
    buf = ""
    for line in block.splitlines():
        while len(line) > CHUNK_MAX_CHARS:
            if buf:
                parts.append(buf)
                buf = ""
            parts.append(line[:CHUNK_MAX_CHARS])
            line = line[CHUNK_MAX_CHARS:]
        if buf and len(buf) + len(line) + 1 > CHUNK_MAX_CHARS:
            parts.append(buf)
            buf = line
        else:
            buf = (buf + "\n" + line) if buf else line
    if buf:
        parts.append(buf)
    return parts


def split_document(text: str) -> list[str]:
    """빈 줄·마크다운 제목(#…)을 경계로 800자 이하 청크. 비어 있지 않으면 최소 1개.

    경계마다 청크를 끊는다(블록 병합 없음 — 계약 문면 그대로). 제목 줄은 다음 블록의
    머리로 붙인다. 800자 초과 블록은 _split_oversize 로 나눈다.
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
