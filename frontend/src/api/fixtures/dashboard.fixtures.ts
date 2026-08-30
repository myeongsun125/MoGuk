import type { DashboardSummary } from "../types";

// KPI 4종(BLUEPRINT §4-6): 등록 수·평균 이해도·완주율·미확인 위험보고.
// open_reports 는 adminReports.fixtures 의 초기 submitted 건수(4)와 일부러 맞췄다 —
// 실API 연결 시 둘 다 같은 risk_reports 테이블을 읽으므로 자연히 일치한다(WORKORDER V3-2 DoD).
export const dashboardMock: DashboardSummary = {
  workers: 24,
  avg_comprehension: 82,
  completion_rate: 71,
  open_reports: 4,
  weekly_trend: [
    { date: "08-24", avg_comprehension: 76 },
    { date: "08-25", avg_comprehension: 78 },
    { date: "08-26", avg_comprehension: 79 },
    { date: "08-27", avg_comprehension: 81 },
    { date: "08-28", avg_comprehension: 80 },
    { date: "08-29", avg_comprehension: 83 },
    { date: "08-30", avg_comprehension: 82 },
  ],
  per_worker: [
    { worker_id: 1, name: "응우옌 반 A", comprehension: 94, label: "green" },
    { worker_id: 2, name: "쩐 티 B", comprehension: 86, label: "yellow" },
    { worker_id: 3, name: "Budi C", comprehension: 71, label: "red" },
    { worker_id: 4, name: "레 반 D", comprehension: 90, label: "green" },
    { worker_id: 5, name: "Sari E", comprehension: 83, label: "yellow" },
  ],
  per_module: [
    { module: "learning", completion_rate: 78 },
    { module: "safety", completion_rate: 65 },
    { module: "speaking", completion_rate: 52 },
    { module: "settlement", completion_rate: 40 },
  ],
};
