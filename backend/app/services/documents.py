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
