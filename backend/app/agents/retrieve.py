"""pgvector 검색 (chunks.embedding hnsw cosine, meta 필터). [새봄]

M-29a: meta.role='case' 청크는 검색 후보에서 원천 배제 — M-29 "근거 인용 금지"의 검색 계층 이행.

skeleton-v3 §4 동결: retrieve(query, k=4, meta_filter=None) -> list[Chunk]
질의 임베딩 = services.llm_adapter.embed (M-02a: ollama /api/embed 단일 런타임 — 적재와 동일).
반환 Chunk 는 §3 sources 스키마({document_id, chunk_id, title, category})를 채울 수 있어야 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services import tenancy
from app.services.llm_adapter import embed

# meta_filter 는 chunks.meta jsonb 포함(@>) 조건. 유사도 = 코사인 (1 - <=>).
# M-29a: role='case' 청크는 검색 후보에서 원천 배제한다 — 답변 생성·sources 노출 양쪽 차단.
# COALESCE 로 NULL 안전 — role 키가 없는 청크(기존 적재분 전부)는 '' 로 평가돼 통과한다.
_SQL = """
SELECT c.id, c.document_id, c.content, c.meta,
       COALESCE(d.title, '') AS title,
       COALESCE(c.meta->>'category', d.category, '') AS category,
       1 - (c.embedding <=> %(vec)s::vector) AS score
FROM chunks c
LEFT JOIN documents d ON d.id = c.document_id
WHERE (%(meta)s::jsonb IS NULL OR c.meta @> %(meta)s::jsonb)
  AND COALESCE(c.meta->>'role', '') <> 'case'
ORDER BY c.embedding <=> %(vec)s::vector
LIMIT %(k)s
"""


@dataclass(frozen=True)
class Chunk:
    id: int  # chunks.id — §3 sources 의 chunk_id
    document_id: int
    content: str
    meta: dict = field(default_factory=dict)  # {"category","machine","doc_version"}
    score: float | None = None
    title: str = ""
    category: str = ""

    def as_source(self) -> dict:
        """§3 sources[] 항목 (프론트 AskSource 와 1:1)."""
        return {
            "document_id": self.document_id,
            "chunk_id": self.id,
            "title": self.title,
            "category": self.category,
        }


def to_vector_literal(vec: list[float]) -> str:
    """pgvector 입력 리터럴 — '[0.1,0.2,...]'."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def retrieve(query: str, k: int = 4, meta_filter: dict | None = None) -> list[Chunk]:
    import json

    if not query or not query.strip():
        return []
    vec = embed([query])[0]
    params = {
        "vec": to_vector_literal(vec),
        "meta": json.dumps(meta_filter) if meta_filter else None,
        "k": k,
    }
    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_SQL, params)
            rows = cur.fetchall()
    return [
        Chunk(
            id=row[0],
            document_id=row[1],
            content=row[2],
            meta=row[3] or {},
            score=float(row[6]) if row[6] is not None else None,
            title=row[4] or "",
            category=row[5] or "",
        )
        for row in rows
    ]
