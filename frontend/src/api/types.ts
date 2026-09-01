// 계약 타입 — skeleton-v3 §3 (JSON 키 snake_case, TS 변수 camelCase)

export type Lang = "ko" | "vi" | "in";

export interface AskSource {
  document_id: number;
  chunk_id: number;
  title: string;
  category: string;
}

export interface AskVerify {
  // 되번역 미수행·실패 시 null(grounded=false 전 경로·타임아웃·예산 0·LLM 오류·임베딩 실패·빈 입력).
  score: number | null;
  passed: boolean;
  gated: boolean;
  gate_reason: "grounding" | "threshold" | null; // M-10b·M-34, §3:222
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
  // §3 계약 밖 — 현재 services/auth.py activate()는 lang을 반환하지 않는다(workers.lang
  // 컬럼은 001에 있지만 issue_token_pair가 아직 안 담음). 향후 추가될 때를 대비한 optional
  // 필드 — 없으면 화면은 기존 기본 vi로 폴백한다.
  lang?: Lang;
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

// approve/reject 실응답 — 전체 GlossaryTerm이 아니라 {id,status}뿐(approval.py:152 _transition
// 반환값, §3:238). 목록 갱신은 별도 GET으로 하므로 화면은 이 값을 쓰지 않는다.
export interface GlossaryTransitionResult {
  id: number;
  status: GlossaryStatus;
}

// 무근거 질의 큐(M-05·M-05a) — GET /admin/unanswered?status= (기본 open). 필드는
// approval.py UNANSWERED_KEYS(001 unanswered_queue + questions 조인) 전사, JH #74 확인.
export type UnansweredStatus = "open" | "answered";

export interface UnansweredItem {
  id: number;
  question_id: number;
  status: UnansweredStatus | string;
  question: string | null;
  lang: string | null;
  question_created_at: string;
  admin_answer: string | null;
  answered_at: string | null;
}

// POST /admin/unanswered/{question_id}/answer 응답 — #74 착륙(approval.py:205-268 answer_unanswered,
// admin.py:203-220) 코드로 대조 확정. id는 unanswered_queue.id(=목록 item.id와 동축, 경로파라미터인
// question_id와는 다른 축). ingest_job_id는 jobs.id(001:126 `id serial` → number).
export interface AnswerResult {
  id: number;
  status: "answered";
  answered_at: string;
  ingest_job_id: number;
}
// 에러: text 누락/공백 422(InvalidAnswer)·open 아님 422(TransitionError)·대상 없음 404
// (UnansweredNotFound) — 셋 다 detail 있는 HTTPException, adminUnanswered.ts가 status를
// Error에 실어 던진다(reports.ts confirm 401 관례와 동일).

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
