import type { DashboardSummary } from "./types";
import { dashboardMock } from "./fixtures/dashboard.fixtures";

// Mock 경계 (skeleton-v3 §7). GET /admin/dashboard 는 백엔드 스텁(NotImplementedError,
// 0830 확인) — 실API 붙으면 이 파일의 USE_MOCK 분기만 자연 소멸.
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

export async function getDashboard(): Promise<DashboardSummary> {
  if (USE_MOCK) {
    await delay(150);
    return dashboardMock;
  }
  const res = await fetch("/api/v1/admin/dashboard");
  if (!res.ok) throw new Error(`dashboard failed: ${res.status}`);
  return (await res.json()) as DashboardSummary;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
