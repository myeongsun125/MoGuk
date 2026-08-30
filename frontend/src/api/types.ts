// 계약 타입 — skeleton-v3 §3 (JSON 키 snake_case, TS 변수 camelCase)

export type Lang = "ko" | "vi" | "in";

export interface AskSource {
  document_id: number;
  chunk_id: number;
  title: string;
  category: string;
}

export interface AskVerify {
  score: number;
  passed: boolean;
  gated: boolean;
}

export interface AskRequest {
  question: string;
  lang: Lang;
}

export interface AskResponse {
  answer: string;
  sources: AskSource[];
  verify: AskVerify;
  trace_id: string;
}

export interface ActivateResponse {
  jwt: string;
  refresh: string;
}

// 위험보고 — skeleton-v3 §3 관리자/근로자 블록, M-08·M-08a·M-15b
export type ReportStatus = "submitted" | "acknowledged" | "resolved";
export type ProcessingState = "queued" | "running" | "done" | "failed";
export type Severity = "high" | "medium" | "low";

export interface AdminReportListItem {
  id: number;
  ko_summary: string | null;
  severity: Severity | null;
  status: ReportStatus;
  processing_state: ProcessingState;
  reporter_confirmed: boolean;
  created_at: string;
}

export interface ReportEvent {
  id: number;
  actor: string | null;
  action: string;
  from_state: string | null;
  to_state: string | null;
  detail: string | null;
  created_at: string;
}

export interface AdminReportDetail {
  id: number;
  source: "voice" | "text";
  original_text: string | null;
  lang: string | null;
  ko_summary: string | null;
  severity: Severity | null;
  status: ReportStatus;
  processing_state: ProcessingState;
  reporter_confirmed: boolean;
  acked_by: number | null;
  acked_at: string | null;
  resolved_by: number | null;
  resolved_at: string | null;
  resolution_note: string | null;
  created_at: string;
  processed_at: string | null;
  events: ReportEvent[];
}

export interface TransitionResult {
  id: number;
  status: ReportStatus;
}

// 대시보드 — skeleton-v3 §3 GET /admin/dashboard (B). KPI 4종 확정판(총괄 0830 정정,
// SB 계약 표 확정 전까지 이 shape이 mock 정본 — 실API 배선 시 이 타입이 실계약).
export type ComprehensionLabel = "red" | "yellow" | "green";

export interface ReportStatusCounts {
  submitted: number;
  acknowledged: number;
  resolved: number;
}

export interface HourlyTrendPoint {
  hour: string; // "09" 등 — 오늘 시간대
  count: number;
}

export interface PerWorkerRow {
  worker_id: number;
  name: string;
  comprehension: number;
  label: ComprehensionLabel;
}

export interface PerModuleRow {
  module: string;
  completion_rate: number;
}

export interface DashboardSummary {
  open_reports: number; // KPI① 미확인 위험보고 수 — A 화면과 동일 소스
  status_counts: ReportStatusCounts; // KPI② 상태별 3칸 (건수, % 없음)
  ungrounded_pending: number; // KPI③ 무근거 질의 대기 수 (unanswered_queue, mock)
  grounded_rate: number; // KPI④ 근거 인용률 % (mock)
  hourly_trend: HourlyTrendPoint[]; // 오늘 시간대별 보고 건수
  per_worker: PerWorkerRow[]; // 보조 영역 — 퀴즈 실데이터 전, mock 명시
  per_module: PerModuleRow[]; // 보조 영역 — mock 명시
}

// 승인큐 — skeleton-v3 §3 GET /admin/glossary?status= / approve|reject (C). DB(001) 컬럼 그대로.
export type GlossaryStatus = "draft" | "approved" | "rejected";

export interface GlossaryTerm {
  id: number;
  term_ko: string;
  term_vi: string | null;
  term_in: string | null;
  note: string | null;
  status: GlossaryStatus;
  source_question_id: number | null;
  approved_by: number | null;
  approved_at: string | null;
}
