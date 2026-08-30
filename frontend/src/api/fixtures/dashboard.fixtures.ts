import type { DashboardSummary } from "../types";
import { statusCounts } from "./adminReports.fixtures";

// KPI 4종 확정판(총괄 0830 정정). ①② 는 adminReports.fixtures 의 실제 mock 저장소를
// 집계해서 A 화면과 항상 같은 숫자가 나오게 한다 — 고정값을 맞춰두는 방식이 아니다.
// ③④(무근거 대기 수·근거 인용률)는 대응 화면·API가 아직 없어 총괄 지정 mock값 사용.
export function buildDashboardMock(): DashboardSummary {
  const counts = statusCounts();
  return {
    open_reports: counts.submitted,
    status_counts: counts,
    ungrounded_pending: 9, // 총괄 권장 mock값 — unanswered_queue 실API 전
    grounded_rate: 100, // 총괄 권장 mock값
    hourly_trend: [
      { hour: "09", count: 1 },
      { hour: "10", count: 2 },
      { hour: "11", count: 0 },
      { hour: "12", count: 1 },
      { hour: "13", count: 3 },
      { hour: "14", count: 2 },
      { hour: "15", count: 1 },
      { hour: "16", count: 4 },
      { hour: "17", count: 2 },
    ],
    // 보조 영역 — 퀴즈 실데이터 전이라 mock. "근로자별 이해도" 접점 유지용.
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
}
