-- 001_tenant_template.sql — 테넌트 스키마 템플릿 (docs/skeleton-v3.md §2 DDL, 원문 그대로) [명선]
--
-- 적용: scripts/apply_tenant.sh <slug>  ({slug} 치환 후 psql 실행)
-- 테넌시: schema-per-tenant (M-04). 미들웨어가 요청 컨텍스트에서 SET search_path.
-- 사전 조건: pgvector 확장 (hnsw 인덱스는 0.5.0+). 확장은 DB 레벨 1회 — 아래 한 줄만 템플릿 외 추가분.
CREATE EXTENSION IF NOT EXISTS vector;

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

-- tenant_settings 시드 (§2 주석의 seed 값) — 템플릿 외 추가분
INSERT INTO tenant_settings(key, value) VALUES
  ('threshold_pass', '90'),
  ('threshold_warn', '80'),
  ('modules', '["learning","safety","speaking","settlement"]')
ON CONFLICT (key) DO NOTHING;
