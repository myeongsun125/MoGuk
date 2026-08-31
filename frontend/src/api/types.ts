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

// 워커 위험보고 제출/확인 — skeleton-v3 §3, backend/app/routers/reports.py. PR-3(워커 플로우).
export interface ReportSubmitRequest {
  original_text: string;
  lang: string;
  source: "voice" | "text";
}

export interface ReportSubmitResponse {
  id: number;
  status: ReportStatus;
  created_at: string;
}

export type ConfirmResult = "confirmed" | "corrected";

export interface ConfirmRequest {
  result: ConfirmResult;
  corrected_text?: string;
}

// 실API 응답은 result 분기별로 형태가 다르다(services/risk_reports.py:410-465 confirm()) —
// confirmed=reporter_confirmed만, corrected=requeued_job_id만, local_failed=원문+안내만.
export interface ConfirmResponse {
  id: number;
  result: ConfirmResult | "local_failed";
  reporter_confirmed?: boolean;
  requeued_job_id?: number;
  original_text?: string;
  message?: string;
}

// 대시보드 — skeleton-v3 §3 GET /admin/dashboard (B). #45 실API 계약 그대로(0830 머지).
// per_worker/per_module 은 이 API 응답에 없음(§3 "V5" 명시) — 별도 상수 mock(아래)로 분리.
export type ComprehensionLabel = "red" | "yellow" | "green";

export interface ReportStatusCounts {
  submitted: number;
  acknowledged: number;
  resolved: number;
}

export interface CitationRate {
  answered: number;
  with_sources: number;
  rate: number | null; // 0~1 소수 — 화면 표기 시 ×100. answered=0 이면 null.
}

export interface HourlyTrendPoint {
  hour: string; // 풀 ISO — "2026-08-30T09:00:00" (Asia/Seoul 버킷)
  count: number;
}

export interface DashboardSummary {
  open_reports: number; // KPI① 미확인 위험보고 수 — A 화면과 동일 소스(risk_reports)
  reports_by_status: ReportStatusCounts; // KPI② 상태별 3칸 (건수, % 없음)
  unanswered_open: number; // KPI③ 무근거 질의 대기 수 (unanswered_queue)
  citation_rate: CitationRate; // KPI④ 근거 인용률
  reports_today_hourly: HourlyTrendPoint[]; // 오늘 시간대별 보고 건수, 00시~현재 zero-fill
  generated_at: string;
  timezone: string;
  // 학습 KPI(V5) — 실API 미반환(admin.py:76 이월). 응답에 없으면 화면이 보조 섹션을 숨긴다(P8 결손 수정).
  per_worker?: PerWorkerRow[];
  per_module?: PerModuleRow[];
}

// 보조 영역 — 학습 KPI(V5), /admin/dashboard 응답에 없어 상수 mock으로 별도 관리.
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

// 감사 로그 — M-08d(검토 중), GET /admin/events (읽기 전용). 실API 계약 표 확정 전까지
// 이 필드 목록이 mock 정본(총괄 0830 지정): actor·target_type·target_id·action·
// from_state·to_state·detail·created_at.
export interface AdminEvent {
  id: number;
  actor: string | null;
  target_type: string;
  target_id: number;
  action: string;
  from_state: string | null;
  to_state: string | null;
  detail: string | null;
  created_at: string;
}
