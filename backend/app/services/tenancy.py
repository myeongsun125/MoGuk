"""schema-per-tenant — 요청 컨텍스트에서 SET search_path TO tenant_{slug} (M-04). [새봄]"""


def tenant_schema(slug: str) -> str:
    # 시그니처는 §4 동결 대상 아님 — 구현 시 확정 (워크로그 근거)
    raise NotImplementedError("[새봄] services.tenancy.tenant_schema")
