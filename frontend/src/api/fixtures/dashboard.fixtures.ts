import type { DashboardSummary, PerModuleRow, PerWorkerRow } from "../types";
import { statusCounts } from "./adminReports.fixtures";

// #45 실API shape 그대로(0830). ①② 는 adminReports.fixtures 의 mock 저장소를 집계해서
// A 화면과 항상 같은 숫자가 나오게 한다 — 고정값이 아니다.
// ③④는 unanswered_queue·questions API가 아직 mock 화면이 없어 총괄 지정값 유지.
function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

export function buildDashboardMock(): DashboardSummary {
  const counts = statusCounts();
  const now = new Date();
  // 로컬 벽시계 그대로 문자열화 — toISOString()은 UTC로 바꿔버려서(KST 표기 의도와 어긋남)
  // 쓰지 않는다. 실API도 타임존 변환 없는 로컬 벽시계 문자열을 낸다(services/dashboard.py).
  const dateStr = `${now.getFullYear()}-${pad2(now.getMonth() + 1)}-${pad2(now.getDate())}`;
  const hours = Array.from({ length: now.getHours() + 1 }, (_, h) => `${dateStr}T${pad2(h)}:00:00`);
  const sample = [1, 2, 0, 1, 3, 2, 1, 4, 2];

  return {
    open_reports: counts.submitted,
    reports_by_status: counts,
    unanswered_open: 9, // 총괄 권장 mock값
    citation_rate: { answered: 12, with_sources: 12, rate: 1.0 }, // 총괄 권장 mock값(100%)
    reports_today_hourly: hours.map((hour, i) => ({ hour, count: sample[i % sample.length] })),
    generated_at: `${dateStr}T${pad2(now.getHours())}:${pad2(now.getMinutes())}:${pad2(now.getSeconds())}`,
    timezone: "Asia/Seoul",
    per_worker: PER_WORKER_MOCK,
    per_module: PER_MODULE_MOCK,
  };
}

// 보조 영역 — 퀴즈 실데이터 전이라 API 무관 상수 mock. §3 "학습 KPI는 V5" 명시분.
export const PER_WORKER_MOCK: PerWorkerRow[] = [
  { worker_id: 1, name: "응우옌 반 A", comprehension: 94, label: "green" },
  { worker_id: 2, name: "쩐 티 B", comprehension: 86, label: "yellow" },
  { worker_id: 3, name: "Budi C", comprehension: 71, label: "red" },
  { worker_id: 4, name: "레 반 D", comprehension: 90, label: "green" },
  { worker_id: 5, name: "Sari E", comprehension: 83, label: "yellow" },
];

export const PER_MODULE_MOCK: PerModuleRow[] = [
  { module: "learning", completion_rate: 78 },
  { module: "safety", completion_rate: 65 },
  { module: "speaking", completion_rate: 52 },
  { module: "settlement", completion_rate: 40 },
];
