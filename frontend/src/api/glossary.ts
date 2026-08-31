import type { GlossaryTerm, GlossaryTransitionResult } from "./types";
import { approveMock, listMock, rejectMock } from "./fixtures/glossary.fixtures";

// Mock 경계 (skeleton-v3 §7). GET/POST /admin/glossary* 는 백엔드 스텁(0830 확인).
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

export async function listGlossary(status = "draft"): Promise<GlossaryTerm[]> {
  if (USE_MOCK) {
    await delay(150);
    return listMock(status);
  }
  const res = await fetch(`/api/v1/admin/glossary?status=${encodeURIComponent(status)}`);
  if (!res.ok) throw new Error(`list_glossary failed: ${res.status}`);
  return (await res.json()) as GlossaryTerm[];
}

export async function approveGlossary(id: number): Promise<GlossaryTransitionResult> {
  if (USE_MOCK) {
    await delay(150);
    const t = approveMock(id);
    if (!t) throw new Error(`term ${id} not found`);
    return t;
  }
  const res = await fetch(`/api/v1/admin/glossary/${id}/approve`, { method: "POST" });
  if (!res.ok) throw new Error(`approve failed: ${res.status}`);
  return (await res.json()) as GlossaryTransitionResult;
}

export async function rejectGlossary(id: number): Promise<GlossaryTransitionResult> {
  if (USE_MOCK) {
    await delay(150);
    const t = rejectMock(id);
    if (!t) throw new Error(`term ${id} not found`);
    return t;
  }
  const res = await fetch(`/api/v1/admin/glossary/${id}/reject`, { method: "POST" });
  if (!res.ok) throw new Error(`reject failed: ${res.status}`);
  return (await res.json()) as GlossaryTransitionResult;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
