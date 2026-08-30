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

// 대시보드 — skeleton-v3 §3 GET /admin/dashboard (B). 응답 필드 목록만 계약, 항목별
// 내부 shape 은 §3 미정의 — BLUEPRINT §4-6 "등록 수·평균 이해도·완주율·미확인 위험보고·
// 주간 추이·근로자별/모듈별" 기준으로 구성. 백엔드 실API 배선 시 이 타입이 실계약.
export type ComprehensionLabel = "red" | "yellow" | "green";

export interface WeeklyTrendPoint {
  date: string;
  avg_comprehension: number;
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
  workers: number;
  avg_comprehension: number;
  completion_rate: number;
  open_reports: number;
  weekly_trend: WeeklyTrendPoint[];
  per_worker: PerWorkerRow[];
  per_module: PerModuleRow[];
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
