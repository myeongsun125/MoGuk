"""pgvector 검색 (chunks.embedding hnsw cosine, meta 필터). [새봄]"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Chunk:
    id: int
    document_id: int
    content: str
    meta: dict = field(default_factory=dict)  # {"category","machine","doc_version"}
    score: float | None = None


def retrieve(query: str, k: int = 4, meta_filter: dict | None = None) -> list[Chunk]:
    raise NotImplementedError("[새봄] agents.retrieve.retrieve")
