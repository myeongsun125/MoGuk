import type { AdminEvent } from "./types";
import { listEvents } from "./fixtures/adminEvents.fixtures";

// Mock 경계 (skeleton-v3 §7). GET /admin/events — M-08d 검토 중, 실API 계약 표는
// SB C 완료 시(22:30선). 계약 표 나오면 이 파일의 USE_MOCK 분기만 소비 전환.
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

export async function getAdminEvents(date?: string): Promise<AdminEvent[]> {
  if (USE_MOCK) {
    await delay(150);
    return listEvents(date);
  }
  const qs = date ? `?date=${encodeURIComponent(date)}` : "";
  const res = await fetch(`/api/v1/admin/events${qs}`);
  if (!res.ok) throw new Error(`admin_events failed: ${res.status}`);
  return (await res.json()) as AdminEvent[];
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
