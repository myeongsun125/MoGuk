import type { DashboardSummary, PerModuleRow, PerWorkerRow } from "../types";
import { statusCounts } from "./adminReports.fixtures";

// #45 실API shape 그대로(0830). ①② 는 adminReports.fixtures 의 mock 저장소를 집계해서
// A 화면과 항상 같은 숫자가 나오게 한다 — 고정값이 아니다.
// ③④는 unanswered_queue·questions API가 아직 mock 화면이 없어 총괄 지정값 유지.
// 학습 KPI 4키(per_worker/per_module/completion_rate/avg_comprehension)는 M-38로 같은
// 실API 응답에 착륙(dashboard.py PER_WORKER_KEYS 등 코드 대조 확정) — 더 이상 별도
// 상수로 분리하지 않고 이 함수 안에서 실 shape 그대로 만든다(M-41).
function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

const PER_WORKER: PerWorkerRow[] = [
  { worker_id: 1, quiz_set_id: 1, score: 94, label: "green", created_at: "2026-09-01T09:12:00" },
  { worker_id: 2, quiz_set_id: 1, score: 86, label: "yellow", created_at: "2026-09-01T09:20:00" },
  { worker_id: 3, quiz_set_id: 2, score: 71, label: "red", created_at: "2026-09-01T10:03:00" },
  { worker_id: 4, quiz_set_id: 1, score: 90, label: "green", created_at: "2026-09-01T10:15:00" },
  { worker_id: 5, quiz_set_id: 2, score: 83, label: "yellow", created_at: "2026-09-01T11:00:00" },
];

const PER_MODULE: PerModuleRow[] = [
  { module: "learning", n: 12, avg_score: 82.4 },
  { module: "safety", n: 9, avg_score: 76.1 },
];

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
    per_worker: PER_WORKER,
    per_module: PER_MODULE,
    completion_rate: { workers_attempted: 5, workers_activated: 8, rate: 0.625 },
    avg_comprehension: 84.8,
  };
}
