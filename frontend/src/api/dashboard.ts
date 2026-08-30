import type { DashboardSummary } from "./types";
import { buildDashboardMock } from "./fixtures/dashboard.fixtures";

// Mock 경계 (skeleton-v3 §7). GET /admin/dashboard 실API #45 머지 완료(0830).
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

export async function getDashboard(): Promise<DashboardSummary> {
  if (USE_MOCK) {
    await delay(150);
    return buildDashboardMock();
  }
  const res = await fetch("/api/v1/admin/dashboard");
  if (!res.ok) throw new Error(`dashboard failed: ${res.status}`);
  return (await res.json()) as DashboardSummary;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
