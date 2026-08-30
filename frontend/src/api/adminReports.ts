import type { AdminReportDetail, AdminReportListItem, TransitionResult } from "./types";
import { ackMock, getMock, listMock, resolveMock } from "./fixtures/adminReports.fixtures";

// Mock 경계 (skeleton-v3 §7) — src/api/ask.ts·auth.ts 와 동일 패턴.
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

export class TransitionConflictError extends Error {
  constructor() {
    super("이미 처리됨");
  }
}

function toListItem(r: AdminReportDetail): AdminReportListItem {
  const { id, ko_summary, severity, status, processing_state, reporter_confirmed, created_at } = r;
  return { id, ko_summary, severity, status, processing_state, reporter_confirmed, created_at };
}

export async function listReports(status?: string): Promise<AdminReportListItem[]> {
  if (USE_MOCK) {
    await delay(150);
    return listMock(status).map(toListItem);
  }
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  const res = await fetch(`/api/v1/admin/reports${qs}`);
  if (!res.ok) throw new Error(`list_reports failed: ${res.status}`);
  return (await res.json()) as AdminReportListItem[];
}

// 세부 버튼 클릭 시에만 호출한다 — 원문 열람 감사(original_viewed)가 실제 열람과
// 일치해야 하므로, 목록 로드 시 미리 호출(prefetch)하거나 캐시로 대체하지 않는다.
export async function getReportDetail(id: number): Promise<AdminReportDetail> {
  if (USE_MOCK) {
    await delay(150);
    const r = getMock(id);
    if (!r) throw new Error(`report ${id} not found`);
    return r;
  }
  const res = await fetch(`/api/v1/admin/reports/${id}`);
  if (!res.ok) throw new Error(`report_detail failed: ${res.status}`);
  return (await res.json()) as AdminReportDetail;
}

export async function ackReport(id: number): Promise<TransitionResult> {
  if (USE_MOCK) {
    await delay(150);
    const r = ackMock(id);
    if (r === "not_found") throw new Error(`report ${id} not found`);
    if (r === "conflict") throw new TransitionConflictError();
    return r as TransitionResult;
  }
  const res = await fetch(`/api/v1/admin/reports/${id}/ack`, { method: "POST" });
  if (res.status === 422) throw new TransitionConflictError();
  if (!res.ok) throw new Error(`ack failed: ${res.status}`);
  return (await res.json()) as TransitionResult;
}

export async function resolveReport(id: number, note?: string): Promise<TransitionResult> {
  if (USE_MOCK) {
    await delay(150);
    const r = resolveMock(id, note);
    if (r === "not_found") throw new Error(`report ${id} not found`);
    if (r === "conflict") throw new TransitionConflictError();
    return r as TransitionResult;
  }
  const res = await fetch(`/api/v1/admin/reports/${id}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note: note ?? null }),
  });
  if (res.status === 422) throw new TransitionConflictError();
  if (!res.ok) throw new Error(`resolve failed: ${res.status}`);
  return (await res.json()) as TransitionResult;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
