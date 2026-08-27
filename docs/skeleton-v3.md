# MoGuk SKELETON v3 (초안) — 팀 비준 후 docs/skeleton-v3로 동결

작성 2026-08-21 | 지위: 비준 시 skeleton-v2를 대체하는 단일 계약 문서(SSOT) | 예선 제출 문서(2026 예선심사과제_AXIs.pdf)를 상위 계약으로 함

## 0. 개정 규칙 (기존 5원칙 유지 + R6)
- R1 보안 결함은 즉시 수정 / R2 성립 불가 계약은 폐기 / R3 충돌은 외부 의존성 결합된 쪽 우선 / R4 개념당 단일 출처 / R5 미결은 M-xx 채번(하드코딩 금지)
- R6 예선 제출 문서와 다른 모든 결정은 M-xx에 변경 사유를 필수 기재한다. (2026-08-25 신설, M-24 · 추적표 = docs/TRACEABILITY.md)
- 착수한 구현 범위에 대응하는 스켈레톤 절은 동결. 변경은 워크로그 근거로만.

## 1. 디렉토리 트리 (모노레포 axis-platform)

```
axis-platform/
├── docker-compose.yml            # dev: core_net + edge_net 2네트워크
├── docker-compose.prod.yml
├── .env.example
├── frontend/                     # [정현]
│   └── src/
│       ├── apps/worker/          # 근로자 모바일 웹: learn, quiz, chat, report, inbox, speaking
│       ├── apps/admin/           # 대시보드, 승인큐, 위험보고, 안전일지, 문서업로드
│       └── i18n/{ko,vi,in}/
├── backend/                      # [새봄]
│   └── app/
│       ├── main.py
│       ├── routers/{auth,learn,ask,reports,chat,notifications,admin,health}.py
│       ├── agents/{classify,retrieve,translate,verify,graph}.py   # ≤3홉 그래프
│       ├── services/{llm_adapter,crypto,stt_client,notify,tenancy}.py
│       ├── modules/
│       │   ├── learning/         # 학습카드·퀴즈 (generate_quiz 포함)
│       │   ├── safety/           # 법정 코스 매핑·교육일지 (render_edu_ledger)
│       │   ├── speaking/         # 따라 말하기
│       │   └── settlement/       # 정착지원 상담챗
│       ├── models/               # SQLAlchemy (스키마=테넌트 동적 바인딩)
│       └── workers/job_runner.py # PG SKIP LOCKED 폴러
├── pipeline/                     # [명선] Dagster
│   ├── assets/{documents_raw,chunks_index,glossary_candidates,quiz_bank,manager_report}.py
│   └── definitions.py
├── experiments/                  # [명선+새봄]
│   ├── testset/sentences_30.json           # {ko, answer_vi, terms[]}
│   ├── testset/corrupted_30.json           # 유형: term_swap|negation|number ×10
│   ├── mistranslation_eval.py              # 측정 #1
│   └── gate_eval.py                        # 측정 #3 → τ 확정
├── data/seed/{manuals,kosha,glossary,phrases,quiz,safety_courses}/
├── infra/                        # [병갑] Caddy, CI, 배포 스크립트, blue-green
└── docs/{SKELETON.md, WORKLOG/, DECISIONS.md}
```

## 2. DB — 테넌트 스키마 템플릿 (PostgreSQL + pgvector)

테넌시: schema-per-tenant. 마이그레이션은 스키마명 파라미터를 받아 `tenant_{slug}`에 적용. 미들웨어가 요청 컨텍스트에서 `SET search_path`.

> **DDL 원문의 단일 출처는 `db/migrations/001_tenant_template.sql`** — 아래 블록과 충돌 시 마이그레이션 우선 (R4, 2026-08-23 PR #3 승인). 마이그레이션은 `CREATE EXTENSION vector`(DB 레벨)·`tenant_settings` 시드·멱등화(`IF NOT EXISTS`/`OR REPLACE`)를 포함한다.

```sql
CREATE SCHEMA IF NOT EXISTS tenant_{slug};
SET search_path TO tenant_{slug};

CREATE TABLE tenant_settings (            -- M-01 임계값, 모듈 플래그
  key text PRIMARY KEY, value jsonb NOT NULL
);-- seed: {"threshold_pass":90,"threshold_warn":80,"modules":["learning","safety","speaking","settlement"]}

CREATE TABLE admins (
  id serial PRIMARY KEY, email text UNIQUE NOT NULL, pw_hash text NOT NULL,
  role text NOT NULL CHECK (role IN ('owner','manager')), created_at timestamptz DEFAULT now());

CREATE TABLE workers (
  id serial PRIMARY KEY, name text NOT NULL, emp_no text UNIQUE,
  lang text NOT NULL CHECK (lang IN ('vi','in')),
  pin_hash text, invited_at timestamptz, activated_at timestamptz);

CREATE TABLE invites (
  token text PRIMARY KEY, worker_id int REFERENCES workers(id),
  expires_at timestamptz NOT NULL, used_at timestamptz);

CREATE TABLE documents (
  id serial PRIMARY KEY, title text NOT NULL,
  category text CHECK (category IN ('process','instruction','safety','equipment')),
  origin text NOT NULL CHECK (origin IN ('upload','admin_answer','seed')),
  source text, version int DEFAULT 1, masked bool DEFAULT false,
  created_at timestamptz DEFAULT now());

CREATE TABLE chunks (
  id serial PRIMARY KEY, document_id int REFERENCES documents(id) ON DELETE CASCADE,
  chunk_idx int NOT NULL, content text NOT NULL,
  embedding vector(1024) NOT NULL,                  -- M-02 bge-m3 고정
  meta jsonb NOT NULL DEFAULT '{}');                -- {"category","machine","doc_version"}
CREATE INDEX chunks_meta_gin ON chunks USING gin(meta);
CREATE INDEX chunks_emb_hnsw ON chunks USING hnsw(embedding vector_cosine_ops);

CREATE TABLE glossary (
  id serial PRIMARY KEY, term_ko text NOT NULL, term_vi text, term_in text, note text,
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','rejected')),
  source_question_id int, approved_by int REFERENCES admins(id), approved_at timestamptz);

CREATE TABLE quiz_sets (
  id serial PRIMARY KEY, module text NOT NULL,      -- 'learning' | 'safety'
  title text NOT NULL, source_doc_id int REFERENCES documents(id),
  origin text NOT NULL CHECK (origin IN ('seed','generated')),
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved')),
  safety_course_id int);
CREATE TABLE quiz_items (
  id serial PRIMARY KEY, quiz_set_id int REFERENCES quiz_sets(id) ON DELETE CASCADE,
  body jsonb NOT NULL);   -- {"q_ko","q_vi","q_in","choices":[..],"answer_idx","explain"}
CREATE TABLE quiz_attempts (
  id serial PRIMARY KEY, worker_id int REFERENCES workers(id),
  quiz_set_id int REFERENCES quiz_sets(id),
  score numeric NOT NULL, passed bool NOT NULL,     -- 통과 판정은 앱에서 threshold_pass로
  detail jsonb, created_at timestamptz DEFAULT now());

-- 이해도(M-01): 세트별 최신 점수. 라벨은 뷰에서 계산.
CREATE VIEW v_comprehension AS
SELECT DISTINCT ON (worker_id, quiz_set_id)
  worker_id, quiz_set_id, score,
  CASE WHEN score < 80 THEN 'red' WHEN score < 90 THEN 'yellow' ELSE 'green' END AS label,
  created_at
FROM quiz_attempts ORDER BY worker_id, quiz_set_id, created_at DESC;

CREATE TABLE questions (                            -- qa_logs 겸용
  id serial PRIMARY KEY, worker_id int REFERENCES workers(id),
  lang text NOT NULL, source text NOT NULL CHECK (source IN ('text','voice')),
  audio_ref text, stt_text text, stt_confidence numeric,
  question text NOT NULL, answer text, grounded bool NOT NULL DEFAULT false,
  sources jsonb NOT NULL DEFAULT '[]',
  trace jsonb NOT NULL DEFAULT '{}',                -- M-09 lineage
  latency_ms int, created_at timestamptz DEFAULT now());
CREATE INDEX questions_trace_gin ON questions USING gin(trace);

CREATE TABLE unanswered_queue (                     -- M-05
  id serial PRIMARY KEY, question_id int UNIQUE REFERENCES questions(id),
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','answered')),
  admin_answer text, answered_by int REFERENCES admins(id), answered_at timestamptz,
  ingested_doc_id int REFERENCES documents(id));

CREATE TABLE conversations (                        -- M-07 정착지원 상담 (로컬 티어 고정)
  id serial PRIMARY KEY, worker_id int REFERENCES workers(id),
  role text NOT NULL CHECK (role IN ('worker','assistant')),
  content text NOT NULL, risk_flag bool NOT NULL DEFAULT false,
  created_at timestamptz DEFAULT now());

CREATE TABLE notifications (                        -- M-06 알림함(쪽지)
  id serial PRIMARY KEY, worker_id int REFERENCES workers(id),
  type text NOT NULL,  -- 'admin_answer'|'report_reply'|'learning_reminder'|'system'
  title text NOT NULL, body text NOT NULL,
  read_at timestamptz, created_at timestamptz DEFAULT now());

CREATE TABLE risk_reports (                         -- M-08
  id serial PRIMARY KEY, worker_id int REFERENCES workers(id),
  source text NOT NULL CHECK (source IN ('voice','text')),
  audio_ref text, original_text text, stt_confidence numeric,
  ko_summary text, severity text CHECK (severity IN ('high','medium','low')),
  status text NOT NULL DEFAULT 'submitted'
    CHECK (status IN ('submitted','acknowledged','resolved')),
  processing_state text NOT NULL DEFAULT 'queued'
    CHECK (processing_state IN ('queued','running','done','failed')),
  acked_by int, acked_at timestamptz,
  resolved_by int, resolved_at timestamptz, resolution_note text,
  created_at timestamptz DEFAULT now(), processed_at timestamptz);

CREATE TABLE jobs (                                 -- M-18 비동기 큐 (Redis 없음)
  id serial PRIMARY KEY, kind text NOT NULL,        -- 'stt_summarize'|'ingest_answer'|...
  payload jsonb NOT NULL,
  status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','done','failed')),
  attempts int NOT NULL DEFAULT 0, run_after timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now());

CREATE TABLE phrases (
  id serial PRIMARY KEY, text_ko text NOT NULL, text_vi text, text_in text,
  high_risk bool NOT NULL DEFAULT false);
CREATE TABLE speaking_records (                     -- M-12 (STT 미적용, 녹음만)
  id serial PRIMARY KEY, worker_id int REFERENCES workers(id),
  phrase_id int REFERENCES phrases(id), audio_ref text NOT NULL,
  created_at timestamptz DEFAULT now());

CREATE TABLE safety_courses (                       -- M-14
  id serial PRIMARY KEY,
  course_type text NOT NULL CHECK (course_type IN ('onboarding','regular','job_change','special')),
  title text NOT NULL, required_minutes int,
  instructor_name text, instructor_qualification_note text,
  content_doc_ids int[] NOT NULL DEFAULT '{}');
CREATE TABLE safety_records (
  id serial PRIMARY KEY, worker_id int REFERENCES workers(id),
  course_id int REFERENCES safety_courses(id),
  minutes_accrued int NOT NULL DEFAULT 0,
  quiz_passed_at timestamptz, completed_at timestamptz);

CREATE TABLE access_logs (                          -- M-07 감사 로그
  id serial PRIMARY KEY, admin_id int REFERENCES admins(id),
  action text NOT NULL,        -- 'view_conversation_full'|'view_report_original'|...
  target_type text NOT NULL, target_id int NOT NULL,
  created_at timestamptz DEFAULT now());
```

## 3. API 계약 (edge, /api/v1, JSON snake_case)

근로자:
```
POST /auth/activate        {token, pin}                    → {jwt, refresh}
POST /auth/login           {emp_no, pin}                   → {jwt, refresh}
GET  /learn/cards?module=
POST /learn/quiz/{set_id}/submit {answers[]}               → {score, passed, label}
POST /ask                  {question, lang}                → {answer, sources[], verify:{score,passed,gated}, trace_id}
POST /ask/voice            multipart(audio≤60s, lang)      → 동일 | 폴백 안내 응답
POST /reports              {text}|multipart(audio)         → 202 {report_id}
GET  /reports/{id}                                          → 상태 조회(접수 확인 화면)
POST /chat                 {message}                        → {reply}          # 로컬 티어 고정
GET  /notifications        / POST /notifications/{id}/read
GET  /speaking/phrases     / POST /speaking/records         multipart(audio)
```
관리자:
```
POST /auth/admin/login     {email, pw}
GET  /admin/dashboard      → {workers, avg_comprehension, completion_rate, open_reports, weekly_trend[], per_worker[], per_module[]}
POST /admin/workers/invite {name, emp_no, lang}            → {invite_url}
POST /admin/documents      multipart                        → 202 (ingest job)
GET  /admin/glossary?status=draft / POST /admin/glossary/{id}/approve|reject
GET  /admin/unanswered     / POST /admin/unanswered/{id}/answer {text}   # → ingest_answer job → M-05 편입
GET  /admin/reports?status= / POST /admin/reports/{id}/ack|resolve {note?}
GET  /admin/conversations/risk                              # 요약만
GET  /admin/conversations/{id}/full                         # 원문 — access_logs 기록
GET  /admin/safety/ledger?course_id&period                  → PDF|HTML
GET  /health
```

## 4. 함수 시그니처 (동결 대상)

```python
# services/llm_adapter.py — M-03, M-17
def complete(prompt: str, tier: Literal["local","external"], timeout_s: float | None = None) -> LLMResult
#   None = 티어별 설정값(M-30)
#   외부 timeout/오류 → 로컬 자동 폴백, LLMResult.tier_used 기록
def embed(texts: list[str]) -> list[list[float]]            # bge-m3/1024 고정
#   런타임 = ollama /api/embed (M-02a)

# agents/ — 실시간 ≤3홉
def classify(text: str) -> Cls(intent, category, lang)
def retrieve(query: str, k: int = 4, meta_filter: dict | None = None) -> list[Chunk]
def translate(text: str, src: str, tgt: str, glossary: list[Term]) -> str
def verify_backtranslation(src: str, out: str) -> Verify(score: float, passed: bool)  # τ = M-10a 실측값
def is_high_risk(cls: Cls, chunks: list[Chunk]) -> bool     # 질의분류 OR 청크 메타
def answer(question: str, lang: str, worker: Worker) -> Answer   # 그래프 엔트리

# services/crypto.py — M-19
def seal(payload: bytes, tenant_key: bytes) -> bytes        # AES-GCM(nonce||ct||tag)
def open_(blob: bytes, tenant_key: bytes) -> bytes

# services/stt_client.py — M-18
def transcribe(audio: bytes, lang_hint: str | None = None) -> STT(text, language, confidence, duration_ms)

# modules/learning
def generate_quiz(doc_ids: list[int]) -> QuizDraft          # status='draft' → 관리자 승인

# workers/job_runner.py
def run_jobs(poll_s: float = 2.0) -> None                    # FOR UPDATE SKIP LOCKED, attempts<3 백오프
def summarize_report(text: str) -> tuple[ko_summary: str, severity: str]   # 로컬 티어

# modules/safety — M-14
def render_edu_ledger(course_id: int, period: str) -> bytes  # 일시·구분·내용·강사(자격근거)·참석자·이해도
```

Dagster 에셋(이름 = 산출 테이블): `documents_raw → chunks_index → glossary_candidates → quiz_bank → manager_report(daily/monthly)`

## 5. 인프라 사양 요약

- compose 서비스: `edge-api`, `core-api`, `stt`, `ollama`, `postgres`, `dagster`, `caddy`, `frontend`
- 네트워크: core_net(postgres, ollama, stt, core-api, dagster — 외부 라우트 없음), edge_net(caddy, edge-api, frontend). core-api → edge-api **outbound 단방향**만.
- stt: faster-whisper `small` int8 (env WHISPER_MODEL), mem 2g / cpu 2, POST /v1/transcribe
- 동기 STT(음성 질문): timeout 15s → 폴백 안내 응답(에러 아님)
- 비동기(위험 보고): 202 즉시 → jobs → 3회 실패 시 processing_state='failed' + 관리자 "직접 청취" 알림 + 오디오 보존
- LLM: ollama qwen3:8b(주력) / qwen3:4b(속도 폴백). 외부 = 저비용 LLM API(용어사전 주입 번역 전용)

## 6. 명명 규칙

- Python·DB: snake_case / TS 변수: camelCase / React 컴포넌트: PascalCase
- DB enum 값: 영문 소문자(코드 안정성 — UI 표기는 i18n에서)
- API 경로: 소문자 명사, JSON 키 snake_case
- 브랜치: feat/*, fix/*, chore/* / 커밋: `type(scope): 요약`
- Dagster 에셋명 = 산출 테이블명 (lineage 가독성)
- i18n 키: `{app}.{screen}.{element}` (예: worker.quiz.submit)

## 7. Mock 경계 (병렬 시작점)

- 프론트: `/ask` fixture JSON, 대시보드 더미 KPI — 8/24 실연동 교체
- 백엔드: FakeLLM(고정 응답) 어댑터로 그래프 먼저 — 8/23 Ollama 교체
- 파이프라인: 로컬 pg에 시드 직적재 스크립트 → 8/24 Dagster 에셋화
- 인프라: Day 1에 compose 완성이 전 트랙의 선행 조건

## 8. M-xx 결정 대장

| ID | 결정 | 상태 |
|---|---|---|
| M-01 | 이해도: 통과 90/재시험, 라벨 <80 red · 80–89 yellow · ≥90 green, 이해도=최신 점수, 임계값은 tenant_settings(UI 미노출) | 확정 |
| M-02 | 임베딩 bge-m3/1024 | 확정·비가역 |
| M-03 | 로컬 LLM qwen3:8b 주력, qwen3:4b 폴백 | 확정 |
| M-04 | 테넌시 = PG schema-per-tenant + search_path | 확정 |
| M-05 | 무근거 질문 → unanswered_queue → 관리자 답변 → documents(origin='admin_answer') 자동 편입 | 확정 |
| M-06 | notifications = 범용 알림함(쪽지) 채널 | 확정 |
| M-07 | 상담 = 정착지원 모듈(기존 챗 + 학습상태 주입), 로컬 티어 고정, 요약 우선 + 원문 열람 시 access_logs | 확정 |
| M-08 | 위험보고 submitted→acknowledged→resolved, STT 3회 실패 시 오디오 보존 + 수동 청취 알림 | 확정 |
| M-09 | lineage = questions.trace + chunks.meta (JSONB, GIN) | 확정 |
| M-10 | 게이트 C+A: 안전 카테고리만 차단, 나머지 점수 배지. 판정 = classify OR chunks.meta. [R6 사유 소급] 이중 검증 전면 적용 → 안전 카테고리 선별 게이트 축소. 사유: PRELIM 한계표의 '고위험 선별' 원칙을 기계 검증에 동일 적용, 일정 대비 검증 실효 최적화 | 확정 |
| M-10a | 게이트 임계값 τ | **미결 → 8/29 gate_eval 실측 확정** |
| M-11 | 퀴즈 = 시드 + generate_quiz 드래프트 + 승인 | 확정 |
| M-12 | 되말하기 = 고위험 문구만, 녹음 저장·재생, 일/월 리포트 편입 | 확정 |
| M-13 | 모듈 물리 디렉토리 분리 + 테넌트 플래그 장착 | 확정 |
| M-14 | 안전 모듈 = 법정 4과정 매핑 + 교육일지 자동 생성. "시간 이수 대체" 주장 금지 | 확정 |
| M-15 | 인증: 일회성 초대 토큰 → PIN(해시) → JWT+리프레시. 관리자 email+pw+role | 확정 |
| M-16 | 오케스트레이터 Dagster (발표에서 Airflow→Dagster 한 줄 선제 처리). [R6 사유 소급] Airflow → Dagster. 사유: 자산 lineage UI 기본 제공(첨부9 lineage 요구 직접 시연) + 경량 로컬 운영 | 확정 |
| M-17 | 외부 = 저비용 LLM API, 용어사전 주입 번역 전용, 실패 시 로컬 폴백 | 확정 |
| M-17a | 외부 API 벤더 = OpenAI gpt-4o-mini, timeout 8s, external→local 폴백 (키는 배포 env로만, 레포 커밋 금지) | 확정 (2026-08-25, PR #4 대조 — 레포 '미결' 상태였음) |
| M-18 | STT = faster-whisper 전용 컨테이너(core_net), 동기 15s 폴백 / 비동기 jobs | 확정 |
| M-19 | 암호화 = AES-GCM 저장 시 암호화 + HTTPS. 브라우저 복호화(E2E)는 로드맵 | 확정 |
| M-20 | 본선 D-day 확정 시 워크플로우 일정 조정 | 미결·외부 |
| M-21 | [본선 후 메모] 근로자별 관리 페이지: 임계값 상향/완화 + LLM 자연어 난이도 조절, 관리자 고위험 오버라이드 | 이월 |
| M-22 | edge-api 는 내부 DB 자격증명·호스트명을 갖지 않고 core_net 에 가입하지 않는다(연결 불가가 정답). edge `/health` = self + core 릴레이 도달성(core-api → edge-api outbound 하트비트 `POST /internal/core-heartbeat` 신선도)만, DB 체크 없음. core_net `internal: true` | 확정 (2026-08-23, PR #3) |
| M-23 | 암호문 시연 저장소 = edge_net 의 경량 edge-db(`published_content` 단일 테이블). 폴백 = 봉인 컬럼 at-rest. compose 에 `edge-db` 자리만(profile full) | **8/26 알파에서 확정** |
| M-24 | 문서 위계: PRELIM=상위 계약 / M-xx=유일 변경 경로(R6 신설) / 개념별 원문 소유(R4) / 진입점=BLUEPRINT(최초 1회 PRELIM) | 확정 |
| M-25 | 미디어(음성) 플로우: edge가 수신 즉시 암호화해 S3 단기 버퍼에 적재(lifecycle TTL 1–2일 자동 삭제) → core가 outbound pull(S3 read) → STT·요약·자동 문서화 → 처리 완료 시 S3 객체 즉시 삭제. S3 용도 = DB 백업 + 미디어 단기 버퍼 2개로 한정. edge는 S3 write-only 자격, core는 read+delete 자격(IAM 분리). [R6 사유: PRELIM "S3" 명시의 이행 — 외부 존 체류는 암호화+단기 TTL로 최소화, M-22 단방향 유지] | 확정 |
| M-26 | 본선 시연=전체 플로우(영상 1–2분+라이브). PRELIM "선택 모듈 1종"=안전교육으로 충족(최소 약속이며 상한 아님), 학습·퀴즈=코어(이해 검증 실체), 상담챗=초과 이행 | 확정 |
| M-27 | PRELIM 정량 목표 ⑤(도입·사용 의향 설문 4.0+): 배포했으나 회수 저조로 수치 미확보 — 추후 보정 예정. 데이터 조작 금지 원칙 명기. 발표에서는 측정 방법·목표로 서술 | 보류(추후 보정) |
| M-28 | 실시간 요청 릴레이(최종형 단일 설계, 임시안 없음): 근로자 앱 요청(/ask·/reports 등)은 edge가 릴레이 큐에 적재 → core가 짧은 주기 outbound 폴링으로 pull → 처리 → 응답을 edge에 회신 → edge가 HTTP 응답 완결. M-22(edge는 core 호출 안 함) 완전 준수. 응답 지연은 V2에서 실측(측정 #4에 릴레이 왕복 포함), 1초 초과 시 개선 항목으로 채번. 구현: 인프라 선행(병갑 — S3·IAM·compose) 후 릴레이 코드(새봄 — backend 소유), 병갑은 M-22 준수 리뷰 | 확정 |
| M-29 | M-29 시드 데이터 근거 기준 (2026-08-26, 명선 확정)<br>결정: 시드·시연·실측용 데이터의 안전수칙·작업절차 서술은 공개 근거 문서(법령 / KOSHA / NCS / EPS)의 source_ref 필수. 근거 없는 안전 서술 금지. 가상 요소는 장비명·사업장명·수치 예시로 한정. 공개 자료 3종은 원문 발췌 적재(생성 금지), 공공누리 유형 확인·출처 표시. 테스트셋은 예선 문서대로 가상 매뉴얼 기반 유지. 감수 판정 = source_ref 존재·일치 대조.<br>R6: 06 시드가 LLM 일반 지식으로 생성 → 근거 없는 프레스 절차(R1 2건), 판정 기준 부재. 예선 문서 §2 데이터 구성과 정합 회복. 영향: MS(06 폐기·07 재생성), V2 실데이터 E2E 27일 이월. | 확정 (2026-08-26, 명선) |
| M-02a | M-02a 임베딩 런타임 (2026-08-27, 명선 확정 / BG 실측)<br>결정: bge-m3/1024 임베딩은 인제스천(Dagster)·질의(어댑터 embed()) 모두 ollama /api/embed 단일 런타임. 다른 런타임 혼용 금지. 시연 전 워밍업 1회(cold 3.1s → warm 0.15s, t3 실측).<br>R6: 런타임 이원 시 적재·질의 벡터 불일치. 스택 내 유일 런타임, core_net internal 정합. 영향: MS(인제스천), SB(embed 구현), BG(모델 pull·keep_alive). | 확정 (2026-08-27, 명선) |
| M-28a | M-28a 릴레이 방식·파라미터 (2026-08-27, 명선 확정 / BG·SB 상신)<br>결정: core→edge 릴레이는 long-poll(hold_s=20). 파라미터: batch ≤10 / request_id UUIDv4 edge 발급·enqueue~respond 멱등 / edge 보류 상한 30s 초과 시 504 / core 리스 60s·재배포 1회. hold 20s는 보류 30s·리스 60s와 독립. 기각 폴백 hold_s=0.5(코드 무변경).<br>R6: 고정 폴링은 주기만큼 지연 하한 발생, long-poll은 실효 지연 ~0. 영향: SB(구현), BG(env). | 확정 (2026-08-27, 명선) |
| M-30 | M-30 LLM timeout 설정 체계 (2026-08-27, 명선 확정 / SB 제안)<br>결정: ① skeleton §4 complete() 시그니처 timeout_s: float = 20 → timeout_s: float \| None = None (None = 티어별 설정값). 동결 시그니처 변경. ② 키: LLM_TIMEOUT_LOCAL_S=25 / LLM_TIMEOUT_EXTERNAL_S=8(구 EXTERNAL_LLM_TIMEOUT_S 개명) / LLM_DEADLINE_S=27(요청당 총 예산, 시도마다 min(티어 timeout, 잔여), 잔여 0이면 재시도 없음) / LLM_NUM_PREDICT=200. LOCAL_FALLBACK_TIMEOUT_S 폐지(LOCAL로 통합). ③ 어댑터는 qwen3 think:false, `<think>` 블록 제거. ④ 값은 초기값 — 재실측(프롬프트 처리 포함) 후 조정 가능, 조정은 env만. ⑤ BLUEPRINT §2-2·WORKORDER의 "8s"는 external 한정으로 명시.<br>R6: 문서 3곳 8s vs 동결 시그니처 20s로 R4 위반, 8b→4b 재시도 합산이 보류 30s 초과하는 결함. 영향: SB(어댑터), BG(env 등재), 전 트랙(§4 계약). | 확정 (2026-08-27, 명선) |
| M-03a | M-03a 로컬 주력 모델 조건부 개정 예약 (2026-08-27, 명선 확정)<br>결정: 로컬 LLM 실행 환경은 g4dn.xlarge(GPU) 전환, M-03(qwen3:8b 주력) 유지. G 쿼터 승인이 8/28 15:00까지 없으면 V4 1차 데모는 t3.xlarge + OLLAMA_MODEL=qwen3:4b + LLM_NUM_PREDICT=100 + t3 unlimited 모드로 운영(env만, 코드·M-03 무변경, 승인 즉시 8b 복귀). V5 프리즈(8/29 18:00) 시점에도 GPU 없으면 M-03a(qwen3:4b 주력) 정식 개정. τ·오류 검출률·발표 수치 측정은 하드웨어 확정 후에만 수행.<br>R6: t3.xlarge CPU 8b 2.4 tok/s(think ON 실측), 25s 예산에 60토큰으로 /ask 불성립. 신규 계정 G 쿼터 0. 영향: BG(전환), MS(실측 일정). | 예약 (2026-08-27, 명선 — 8/29 18:00 조건부 정식 개정) |
