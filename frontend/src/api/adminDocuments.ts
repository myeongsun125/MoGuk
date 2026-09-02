import type { DocumentListItem, DocumentUploadRequest, DocumentUploadResult } from "./types";
import { listMock, uploadMock } from "./fixtures/adminDocuments.fixtures";

// Mock 경계 (skeleton-v3 §7). glossary.ts 구조 템플릿, 어드민 API 관례대로 Bearer 미부착
// (IP 화이트리스트 보호, adminWorkers.ts/adminUnanswered.ts와 동일). POST/GET 둘 다
// docs/ms-m41(0902 명선 확정, 미머지)로 계약은 확정됐지만 백엔드는 POST가 아직
// NotImplementedError 스텁이고 GET 라우트가 없다(admin.py 대조 확인, types.ts 주석 참고) —
// 그래도 계약이 확정 형태라 실경로를 그대로 배선해둔다(착륙 즉시 동작).
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

export async function uploadDocument(body: DocumentUploadRequest): Promise<DocumentUploadResult> {
  if (USE_MOCK) {
    await delay(150);
    return uploadMock(body);
  }
  const res = await fetch("/api/v1/admin/documents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw Object.assign(new Error(`upload_document failed: ${res.status}`), { status: res.status });
  }
  return (await res.json()) as DocumentUploadResult;
}

export async function listDocuments(): Promise<DocumentListItem[]> {
  if (USE_MOCK) {
    await delay(150);
    return listMock();
  }
  const res = await fetch("/api/v1/admin/documents");
  if (!res.ok) {
    throw Object.assign(new Error(`list_documents failed: ${res.status}`), { status: res.status });
  }
  return (await res.json()) as DocumentListItem[];
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
