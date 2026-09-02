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

// 재로그인 — POST /auth/login {emp_no,pin} (SB 실물, auth.py:106-113·auth_service.login
// 코드 대조 확인). {jwt,refresh}만 — lang 없음(계정 미존재·PIN 불일치 구분 없이 401 단일).
export interface LoginResult {
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
// 학습 KPI 4키(per_worker/per_module/completion_rate/avg_comprehension)는 M-38로 실API
// 착륙(dashboard.py RESPONSE_KEYS·PER_WORKER_KEYS·PER_MODULE_KEYS·COMPLETION_KEYS 코드
// 대조 확정, M-41 시점 기준 더 이상 mock 상수 분리 대상 아님) — 그래도 optional 유지:
// activated 근로자 0명 등 초기 상태에서 응답 자체는 오되 화면이 안전하게 숨길 수 있게.
export type ComprehensionLabel = "red" | "yellow" | "green"; // v_comprehension(001:69) CASE 그대로

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

// completion_rate — dashboard.py COMPLETION_KEYS 그대로. 분자=quiz_attempts DISTINCT
// worker_id(시도), 분모=workers WHERE activated_at IS NOT NULL(활성). 분모 0이면 rate null.
export interface DashboardCompletionRate {
  workers_attempted: number;
  workers_activated: number;
  rate: number | null;
}

export interface DashboardSummary {
  open_reports: number; // KPI① 미확인 위험보고 수 — A 화면과 동일 소스(risk_reports)
  reports_by_status: ReportStatusCounts; // KPI② 상태별 3칸 (건수, % 없음)
  unanswered_open: number; // KPI③ 무근거 질의 대기 수 (unanswered_queue)
  citation_rate: CitationRate; // KPI④ 근거 인용률
  reports_today_hourly: HourlyTrendPoint[]; // 오늘 시간대별 보고 건수, 00시~현재 zero-fill
  generated_at: string;
  timezone: string;
  // 학습 KPI(M-38, dashboard.py RESPONSE_KEYS 실API 착륙) — optional 유지: 초기(활성 근로자
  // 0명 등) 응답이라도 화면이 안전하게 보조 섹션/카드를 숨길 수 있게.
  per_worker?: PerWorkerRow[];
  per_module?: PerModuleRow[];
  completion_rate?: DashboardCompletionRate;
  avg_comprehension?: number | null;
}

// 근로자별 이해도 행 — dashboard.py PER_WORKER_KEYS(v_comprehension SELECT) 코드 대조 확정.
// name 없음(뷰에 없는 필드) — 화면은 worker_id로만 식별한다.
export interface PerWorkerRow {
  worker_id: number;
  quiz_set_id: number;
  score: number;
  label: ComprehensionLabel;
  created_at: string;
}

// 모듈별 집계 — dashboard.py PER_MODULE_KEYS(quiz_sets JOIN v_comprehension GROUP BY module).
export interface PerModuleRow {
  module: string;
  n: number;
  avg_score: number;
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

// 근로자 초대 발급 — POST /admin/workers/invite (M-32), admin.py:93-121·invites.py:38,102-137
// 코드로 대조 확정. 본문은 반드시 이 3필드만(★phone 등 그 외 필드 전송 금지 — InviteRequest가
// 선언 안 한 필드는 파이단틱이 조용히 버리지만, _reject_identity_fields 가드가 별도로 원본
// 본문을 검사해 금지 필드가 섞이면 400을 낸다. phone은 이 계약에 아예 없는 필드라 화면
// 상태로만 들고 있고 절대 본문에 싣지 않는다).
export type WorkerInviteLang = "vi" | "in"; // 001 workers.lang CHECK 집합(ko 제외 — invites.py:38)

export interface WorkerInviteRequest {
  name: string;
  emp_no: string;
  lang: WorkerInviteLang;
}

// invites.py:137 create_invite 반환 그대로 — 201 성공 시 이 한 필드뿐.
// worker_id는 §3 계약 밖(SB #87 파트2 전) — 그 전까지 실백엔드는 안 채운다. mock은
// ⑤ 카톡 발송 버튼 활성화 조건으로 쓰기 위해 지금부터 채운다(optional로 방어적 처리).
export interface WorkerInviteResult {
  invite_url: string;
  worker_id?: number;
}

// 카톡 발송 — POST /admin/workers/{id}/send-invite (SB #87 파트1 확정, {id}=worker_id).
// body {channel:'kakao_link'} → 이 응답. 어드민 API 관례대로 Bearer 미부착.
export interface SendInviteResult {
  share_url: string;
}

// 퀴즈(learn) — §3 M-38 확정 계약. GET /learn/quiz/{set_id}?lang= 응답이 이 shape.
// 서버가 요청 lang 기준으로 q·choices를 이미 localize해 내려주므로 클라는 그대로 렌더한다
// (q_ko/q_vi 선택·in→ko 폴백 로직은 서버 책임으로 이동 — 클라에는 없음).
export interface QuizTermHint {
  term_ko: string;
  term_lang: string;
}

export interface QuizItem {
  id: number;
  q: string;
  choices: string[];
  term_hints: QuizTermHint[];
}

export interface QuizSet {
  set_id: number;
  module: string;
  title: string;
  status: string;
  items: QuizItem[];
}

// POST /learn/quiz/{set_id}/submit body {answers:number[]} → 이 응답(learn.py:13-15 주석,
// M-01 tenant threshold 판정). label 값 enum은 SB 미확정 — mock에서 "red"|"yellow"|"green"
// 3색으로 임시 정의(관리자 Dashboard의 ComprehensionLabel과 동일 색 관례 재사용), 실값 오면
// 화면의 색 매핑 함수 1곳만 교체하면 된다. 타입은 string으로 넓게 둔다(미확정 계약 보수적 처리).
export interface QuizSubmitResult {
  score: number;
  passed: boolean;
  label: string;
}

// 학습카드 — GET /learn/cards?module=&lang= (SB 확정, §3 M-42). safety=phrase(안전문구
// 10건)·learning=term(용어집). text=요청 lang으로 서버가 localize, text_ko는 항상 한국어
// 병기용. high_risk는 phrase만 true 가능(term은 항상 false) — 빨간 강조 매핑. note_ko·src는
// 옵셔널(없을 수 있어 화면에서 방어). 인증 optional(퀴즈 GET 동형, 토큰 있으면 lang 없어도
// 서버가 근로자 lang으로 localize). 실백엔드는 착수중·미착륙(learn.py:27-29 스텁 확인) —
// mock 경계로 동작, 착륙 즉시 실경로 전환.
export type LearnCardKind = "phrase" | "term";

export interface LearnCard {
  id: number;
  kind: LearnCardKind;
  text: string;
  text_ko: string;
  high_risk: boolean;
  note_ko?: string;
  src?: string;
}

export interface LearnCardsResponse {
  module: string;
  quiz_set_id: number | null; // 이 모듈에 연결된 퀴즈 세트 — 없으면 "퀴즈 준비 중"
  cards: LearnCard[];
}

// 문서 등록(관리자 업로드) — POST/GET /admin/documents (M-41). §3 등재 문구는 아직 구
// multipart 그대로지만, docs/ms-m41(0902 명선 확정, 미머지)이 실 계약을 JSON으로 확정:
// {title,category,text,filename?} → 202 {id,job_id}, GET → 목록. 백엔드는 POST가 아직
// NotImplementedError 스텁이고 GET 라우트 자체가 없다(admin.py 대조 확인) — 계약은
// 확정이지만 코드 미착륙이라 mock 경계로 동작한다. category CHECK(001 documents 테이블
// 74-76행) 그대로 — mock 4개 아님, 실 DB 제약값.
export type DocumentCategory = "process" | "instruction" | "safety" | "equipment";
export type JobStatus = "queued" | "running" | "done" | "failed"; // jobs.status CHECK(001) 그대로

export interface DocumentUploadRequest {
  title: string;
  category: DocumentCategory;
  text: string;
  filename: string;
}

// docs/ms-m41: documents(origin:'upload', source:'upload:'+filename) 생성 + ingest_document
// 잡 큐잉 → 202 {id, job_id}. id=documents.id, job_id=jobs.id.
export interface DocumentUploadResult {
  id: number;
  job_id: number;
}

export interface DocumentListItem {
  id: number;
  title: string;
  category: DocumentCategory | string;
  origin: "upload" | "admin_answer" | "seed";
  source: string | null;
  created_at: string;
  chunk_count: number;
  // SB 확정 — 잡 없이 바로 적재된 시드 문서는 job_status가 null(잡 자체가 없음, 상태
  // '없음'과 실패는 다른 의미라 failed로 대신하지 않는다).
  job_status: JobStatus | string | null;
}
