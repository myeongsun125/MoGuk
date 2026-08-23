# MoGuk (AXIs) — 전체 스켈레톤 · API 계약 · 호출부 설계 v0.2

작성 2026-08-03(v0.1) · 개정 2026-08-04(v0.2).
근거: AXIs 해커톤 기획서(5p) + BP 로드맵 + DL(datalake-redesign) 검증 패턴 + **레포 감사 리포트(2026-08-04, main @ 76c9e25)**.
용도: BP-3 스캐폴딩(8/11~8/20) 착수 기준 문서. 7/25 회의에서 확정한 계약이 있으면 그것이 권위 — 본 문서와 충돌 시 회의 계약 우선, 차이는 이 문서에 반영할 것.
규칙: 이 문서의 모든 코드/구조는 제안이며, 실제 생성·적용은 팀원이 직접 한다.

---

## v0.1 → v0.2 changelog (리뷰 미팅 안건표)

| # | 변경 | 사유 | 관련 |
|---|------|------|------|
| C-1 | §3 트리를 `backend/app/` 패키지 구조로 전면 개편 | 현행 코드·Dockerfile·CI가 `app.main:app` 기준. 코드가 합리적 → 문서를 코드에 맞춤 | 감사 #6 |
| C-2 | `chunks.embedding` 차원 하드코딩(768) 제거 → `EMBEDDING_DIM` 설정값(기본 1024). 임베딩 모델 bge-m3 확정 제안 | README "bge-m3 고정"(1024차원)과 §4 vector(768)의 정면 모순. 이대로 DDL 생성 시 인덱싱 즉사 | 감사 #2, 구 §10-2 |
| C-3 | `/health`(및 `/`)를 `/api/v1` 밖 **루트 운영 엔드포인트**로 명문화 | compose 헬스체크·CI 게이트·README가 전부 루트 `/health`에 물려 있음. 인프라 표준 | 감사 #7 |
| C-4 | 구 `agents/pipeline/` → **`ingestion/`으로 명칭·위치 확정, 담당 명선** | 레포에 ingestion/이 이미 존재(명선 구획 착수 정황). 문서를 현실에 맞춤. 단 §6.4 LLM 호출 규율은 폴더와 무관하게 적용 | 감사 #8 |
| C-5 | `POST /verify/backtranslation` 요청 계약 수정: 원문(reference) 필드 추가 | 되번역 점수는 "되번역 vs 원문" 유사도 — 원문 없이는 계약 자체가 성립 불가 | 리뷰 |
| C-6 | 상태 enum 이중화 해소: job enum과 document enum을 §2에 **별도 등재·혼용 금지** 명시 | "거의 같은데 조금 다른" enum 두 벌 = 혼란 1순위 | 리뷰 |
| C-7 | `glossary_terms`의 `ko, vi, id_lang` 비대칭 컬럼 → `translations JSONB`(lang 키) | 언어 3종 확장 시 ALTER 불필요. id는 SQL 가독성 문제도 해소 | 리뷰 |
| C-8 | **§11 스켈레톤 DoD** 신설 — "비어 있지만 돌아가는" 상태의 완료 기준 | BP-3 종료 판정 기준이 문서에 없었음 | 리뷰 |
| C-9 | §9 로드맵에 learning/quiz/dashboard 구현 시점(BP-4 후반) 명시 + BP-2 동결 예외(`experiments/` 예선 실험) 추가 | 시연 시나리오 마지막이 대시보드인데 일정에서 증발 / 동결 선언과 예선 정량 실험(~8/6)의 모순 | 리뷰 |
| C-10 | §10 미결 항목 갱신: Dagster·Whisper 컨테이너 배치, audio 저장 위치, worker_token 수명 추가. M-번호 채번 | 감사·리뷰에서 발견된 인프라 미정 사항 | 감사 #10 |
| C-11 | §3에 누락 파일 보강: `workplace_schemas.py`, `dashboard_schemas.py`, `tests/test_llm_router.py` | §8 테스트 목록과 §3 트리 불일치 등 | 리뷰 |
| C-12 | `/ask` 요청 검증 규칙 명시: `text`/`audio_id` 정확히 하나만 (둘 다 or 둘 다 없음 = 422) | 계약 모호성 제거 | 리뷰 |
| C-13 | 루트 `docker-compose.yml`(dev) 공식화, `infra/`는 prod compose·caddy·scripts 전용 | 현행 배치가 DX상 합리적 — 문서를 현실에 맞춤 | 감사 [1] |
| C-14 | 담당 경계 §3.5 신설: 폴더 단위 4인 전용 구역 + `constants.py` 공유 규칙 | 구 문서는 파이썬 코드 8할이 새봄 단독 — 기획서 역할표와 불일치 | 리뷰 |
| C-15 | compose `POSTGRES_PASSWORD` 기본 폴백 제거(`:?` 필수화) 규칙 명시 | prod 복제 시 기본 비번 사고 차단 | 감사 #3 |
| C-16 | 입력 배타 규칙(`text?`/`audio_id?` 정확히 하나)을 §2 공통 명명 규칙으로 승격, error_code `input_exactly_one` 통일, /ask·/reports 적용 | v0.2 재검토(2026-08-04)에서 발견 | 재검토 잔여 이슈 #1 |
| C-17 | `app/services/system_service.py` 신설 — main.py "로직 0" 선언과 /health 컴포넌트 체크 로직의 거처 충돌 해소 | v0.2 재검토(2026-08-04)에서 발견 | 재검토 잔여 이슈 #2 |
| C-18 | §6.2 콜 그래프 말미 status 전이를 job/document enum 별로 분리 표기 | v0.2 재검토(2026-08-04)에서 발견 | 재검토 잔여 이슈 #3 |
| C-19 | `backend/Dockerfile`을 폴더 경계의 명시적 예외로 §3.5 공유 파일 규칙에 등재 | v0.2 재검토(2026-08-04)에서 발견 | 재검토 잔여 이슈 #4 |
| C-20 | DoD-2 재작성 — /health 200/503 판정 기준(components.db)과 llm degraded 표면화 방식 명문화 | v0.2 재검토(2026-08-04)에서 발견 | 재검토 잔여 이슈 #5 |

> **v0.2 채택 절차**: 팀 리뷰 → 이 파일을 `docs/MoGuk_SKELETON.md`로 커밋·푸시(감사 #1 해소) → §5를 `docs/API_CONTRACT.md`로 발췌 채택.

---

## 0. 한 줄 정의

사업장 자료 업로드로 만든 전용 지식베이스 위에서, 근로자가 모국어(vi/id)로 배우고 질문하고 보고하며, 시스템이 "이해했다"까지 이중 검증(백트랜슬레이션+되말하기)으로 데이터화하는 온프레미스 LLM·RAG 플랫폼.

핵심 명제(발표 메시지와 코드가 일치해야 함):

1. **번역이 아니라 이해 검증** — 검증 결과가 대시보드·증빙으로 남는다.
2. **LLM은 제안, 규칙이 결정, 사람이 승인** — 환각이 지식베이스·용어사전에 못 들어간다.
3. **내부 데이터는 온프레미스 밖으로 안 나간다** — 데이터 등급별 결정론 라우팅.
4. **전 과정 처리 이력(trace)** — 산업안전보건법 증빙 자동화와 직결.

---

## 1. DL 패턴 → MoGuk 이식 매핑

| DL 패턴 (결정번호) | MoGuk 적용 |
|---|---|
| LLM 제안·규칙 검증·사람 승인 (D-13/D-43) | LLM 분류·추출 결과는 전부 frozenset 화이트리스트로 필터 후 승인 큐 경유 |
| step_key 안정 식별자 (D-38/39) | 승인 큐 `approval_key = "{kind}:{source_id}"` — 순서 무관, 재생성에도 안정 |
| lineage 기록 강제 (D-17/D-128) | `harness/trace.py` — 질의·검증·승인·보고 전 건 trace 기록 (증빙 기능의 실체) |
| LLM 실패 위장 금지 (D-101) | `llm/adapter.py` — `_llm_failed` 마커 + `llm_status/model_used/llm_error` 응답 필드 |
| 세션/요청별 모델 선택 (D-99) | `model` 파라미터 optional — 데모에서 모델 즉석 교체 시연 가능 |
| 결정론 라우터 (D-163) | `llm/llm_router.py` — data_class → on-prem/외부 API 라우팅은 규칙, LLM 판단 0 |
| 검증은 100% 단언 가능한 것만 (D-68) | 백트랜슬레이션 점수 = 결정론 유사도 산식. LLM 채점 금지 |
| anti-silent / fail-loud (D-190/D-200) | 계약 위반 422 + 명확한 error body. silent drop·자동 변형 금지 |
| 폴링 상태머신 (D-51/D-56) | 배치 파이프라인 job: suspend→approve→resume, SSE 없이 폴링 |
| 승인 쓰기 = 동일 트랜잭션 history append (D-179) | glossary/knowledge 쓰기는 approvals 경유 단일 경로 + history 테이블 |
| 스키마 모듈명 전역 고유 (D-19) | `{domain}_schemas.py` 명명 — import 충돌 원천 차단 |
| 백그라운드 학습 + 폴링 (D-147) | 인덱싱·STT 등 무거운 작업은 `asyncio.to_thread` + job 폴링 |

> **v0.2 주**: 위 규율은 폴더 위치와 무관하게 적용된다. `ingestion/`(구 agents/pipeline)의 LLM 개입 단계(doc_classifier, term_extractor, pii_masker 보조)도 constants 화이트리스트·adapter 경유·trace 기록 대상이다. (C-4)

---

## 2. 용어 통일표 (SSOT)

코드·API·DB·문서에서 아래 영문 식별자만 사용. 동의어 혼용 금지.

| 한글(기획서) | 식별자 | 비고 |
|---|---|---|
| 사업장 | `workplace` | site/company/factory 금지 |
| 사업주/관리자 | `admin` | owner/manager 금지 |
| 근로자 | `worker` | user/employee 금지 |
| QR 초대 | `invite` | `invite_code` |
| 지식베이스 | `knowledge` | kb 금지 (약어 금지 원칙) |
| 문서(업로드 자료) | `document` | 분류값은 `doc_type` |
| 문서 분류 4종 | `doc_type ∈ {process, instruction, safety, equipment}` | 공정/지시/안전/장비 |
| 청크/임베딩 | `chunk` | pgvector 저장 단위 |
| 용어 사전 | `glossary` / 항목 `term` | dictionary 금지 |
| 용어 후보 | `term_candidate` | status=candidate |
| 질의(질문하기) | `ask` | chat/query 금지. 엔드포인트 `/ask` |
| 입력 의도 분류 | `intent ∈ {question, report, practice, smalltalk}` | 화이트리스트 |
| 번역 | `translation` | `src_lang`/`tgt_lang` |
| 백트랜슬레이션(기계 검증) | `backtranslation` | verification method 1 |
| 되말하기(사람 검증) | `readback` | verification method 2 |
| 이해 검증(총칭) | `verification` | verify 라우터 |
| 품질 게이트 | `gate` | 형식/권한/근거 3종 |
| 승인 큐 | `approval` | `approval_key` |
| 처리 이력 | `trace` | `trace_id`. lineage와 동일 개념 |
| 상향 보고(위험/이상) | `report` | `ko_summary` 동반 |
| 학습 모듈 | `learning_module` | |
| 퀴즈/응시 | `quiz` / `quiz_attempt` | |
| 이해도/진행률 | `progress` | `comprehension_rate` 포함 |
| 데이터 등급 | `data_class ∈ {public, internal, sensitive}` | 라우팅 키 |
| 개인정보 마스킹 | `pii_masking` | |
| 언어 코드 | `lang ∈ {ko, vi, id}` | ISO 639-1. locale 금지 |

### 명명 규칙

- URL 리소스 = 소문자 복수 명사(`/workers`), 액션 = POST 하위 리소스(`/reports/{id}/ack`).
- JSON 필드 = snake_case. ID 필드 = `{entity}_id`. 시각 = `*_at`(ISO 8601, UTC).
- **상태 enum 2종 — 유사하지만 서로 다른 enum이며 혼용 금지 (C-6)**:
  - 승인류: `{pending, approved, rejected}`
  - **job**: `{queued, running, awaiting_approval, completed, failed}`
  - **document**: `{queued, indexing, awaiting_approval, published, failed}` — job과 별개. document는 산출물의 생애주기(published가 종착), job은 작업의 생애주기(completed가 종착).
- Python 모듈명 전역 고유. Pydantic 스키마 파일 = `{domain}_schemas.py`.
- LLM 끼는 모든 응답에 `llm_status ∈ {ok, failed}` + `model_used` (+실패 시 `llm_error`).
- **엔드포인트 계층 (C-3)**: 비즈니스 API = `/api/v1/*`. 운영 엔드포인트 = 루트(`/health`, `/`). `/models`는 프론트 소비용이므로 `/api/v1/models` (M-07에서 최종 확정).
- **입력 배타 규칙 (C-16)**: `text?`/`audio_id?` 패턴의 모든 엔드포인트는 둘 중 정확히 하나만 허용. 둘 다 있거나 둘 다 없으면 422 `{error_code: "input_exactly_one"}`. (적용: POST /ask, POST /reports)

---

## 3. 레포 디렉터리 스켈레톤 (github.com/myeongsun125/MoGuk) — v0.2

★ = 폴더 전용 담당(§3.5). 현행 코드(`backend/app/` 패키지, 루트 compose, `ingestion/`)를 기준으로 재작성. (C-1, C-4, C-13)

```
MoGuk/
├── docker-compose.yml                # dev 기동 (db·ollama·backend·frontend). 루트가 공식 위치 (C-13)
├── .env.example                      # 필수 환경변수 목록 (POSTGRES_PASSWORD는 :? 필수화 — C-15)
├── backend/                          # ★새봄
│   ├── Dockerfile
│   └── app/                          # 패키지 루트 — uvicorn app.main:app (C-1)
│       ├── main.py                   # FastAPI 엔트리 — 라우터 include + /health·/ 등록만, 로직은 system_service로 위임 (C-17)
│       ├── config.py                 # .env 로드 (DB_URL, OLLAMA_URL, EXTERNAL_LLM_KEY, LANGS, EMBEDDING_DIM)
│       ├── db.py                     # asyncpg 풀 + pgvector 헬퍼
│       ├── deps.py                   # 인증 의존성 (admin_token / worker_token)
│       ├── llm/
│       │   ├── adapter.py            # generate() 단일 진입점 + 실패 표면화 (D-101)
│       │   └── llm_router.py         # data_class → 타깃(on-prem/external) 결정론 라우팅
│       ├── routers/                  # 호출부 — 얇게. 파싱→service 호출→응답만
│       │   ├── auth_router.py        # /auth
│       │   ├── workplace_router.py   # /workplaces /invites /workers
│       │   ├── knowledge_router.py   # /documents /jobs
│       │   ├── approval_router.py    # /approvals
│       │   ├── glossary_router.py    # /glossary (읽기 전용)
│       │   ├── ask_router.py         # /ask /stt
│       │   ├── verify_router.py      # /verify/backtranslation /verify/readback
│       │   ├── learning_router.py    # /learning /quizzes
│       │   ├── report_router.py      # /reports
│       │   ├── dashboard_router.py   # /dashboard /traces
│       │   └── system_router.py      # /models (api/v1 하위)
│       ├── schemas/                  # Pydantic — 파일명 전역 고유 (C-11: workplace·dashboard 보강)
│       │   ├── workplace_schemas.py
│       │   ├── ask_schemas.py
│       │   ├── knowledge_schemas.py
│       │   ├── approval_schemas.py
│       │   ├── verify_schemas.py
│       │   ├── learning_schemas.py
│       │   ├── report_schemas.py
│       │   └── dashboard_schemas.py
│       └── services/                 # 유스케이스 오케스트레이션 (규칙·트랜잭션)
│           ├── ask_service.py        # 질의 에이전틱 플로우 총괄
│           ├── knowledge_service.py  # 배치 job 상태머신
│           ├── approval_service.py   # 승인/반려 + history 트랜잭션
│           ├── verify_service.py
│           ├── learning_service.py
│           ├── report_service.py
│           └── system_service.py     # /health 컴포넌트 체크·/models — main.py와 system_router가 호출 (C-17)
├── agents/                           # ★새봄 — 질의 플로우·검증기 (LLM 판단 단위)
│   ├── constants.py                  # frozenset 화이트리스트 전부 이 한 파일 — 공유 파일 규칙 §3.5
│   ├── qa/
│   │   ├── intent_classifier.py      # LLM 제안 → INTENT_TYPES 필터
│   │   ├── retriever.py              # 용어 보정(glossary) + 지식 검색 (pgvector)
│   │   ├── translator.py             # 번역 (retriever와 병렬)
│   │   └── answerer.py               # 근거 기반 답변 생성
│   └── verifier/
│       ├── response_verifier.py      # 게이트 3종: 형식/권한/근거 — 결정론
│       ├── backtranslation.py        # 되번역 + 유사도 산식(결정론)
│       └── readback.py               # STT 텍스트 vs 원문 대조(결정론)
├── ingestion/                        # ★명선 — 지식 구축 배치 (구 agents/pipeline. C-4)
│   ├── ingestor.py                   # 파일 수신·텍스트 추출
│   ├── doc_classifier.py             # LLM 제안 → DOC_TYPES 필터 (§6.4 규율 적용)
│   ├── term_extractor.py             # LLM 용어 후보 추출 → 승인 큐 적재 (§6.4 규율 적용)
│   ├── pii_masker.py                 # 규칙(정규식) 우선 + LLM 보조 — 결정론 우선
│   └── indexer.py                    # 청킹→임베딩→pgvector (LLM 0)
├── harness/                          # ★새봄 — 이중 검증 하네스 + 추적
│   ├── trace.py                      # record()/query() — 전 과정 이력
│   └── gates.py                      # 게이트 판정 결과 스키마 + 임계값 상수
├── orchestration/                    # ★명선 — Dagster (ingestion/ 호출·스케줄·lineage)
├── frontend/                         # ★정현 — React (관리자 웹 + 근로자 모바일웹)
│   └── (Dockerfile — BP-3)
├── infra/                            # ★병갑 — prod compose·CI/CD·blue-green (C-13)
│   ├── docker-compose.prod.yml       # (8/3 예정분 — 미생성)
│   ├── caddy/
│   └── scripts/
├── .github/workflows/                # ★병갑
│   ├── ci.yml                        # verify → build-scan-push (현행)
│   └── deploy.yml                    # 게이트③ 스테이징 헬스체크 → blue-green (기한 8/4)
├── data/                             # ★명선 — 데모 데이터 (NCS·KOSHA·EPS·가상 매뉴얼)
├── experiments/                      # ★명선·새봄 — 예선 정량 실험 스크립트. BP-2 코드 동결 예외 구역 (C-9)
├── tests/
│   ├── test_contracts.py             # 화이트리스트↔스키마 동기 검증 (DL CI 교훈)
│   ├── test_ask_flow.py              # 질의 e2e (LLM stub)
│   ├── test_gates.py                 # 게이트 결함주입 — 비공허 (mutation RED)
│   ├── test_approval_history.py      # 승인 쓰기=history 동반 불변식
│   └── test_llm_router.py            # sensitive → EXTERNAL 라우팅 시 RED (C-11)
└── docs/
    ├── MoGuk_SKELETON.md             # 본 문서 (커밋 필수 — 감사 #1)
    ├── API_CONTRACT.md               # §5 표가 원본 — openapi.yaml 자동 생성과 대조 (BP-2 산출물)
    ├── DB_SCHEMA.md                  # ★명선 SSOT (BP-2 산출물)
    ├── FRONTEND_MAP.md               # ★정현 — 화면↔API 매핑 표 (BP-2 산출물. §3.5)
    └── decisions.md                  # M-01~ 채번 (DL D-번호 방식)
```

### 3.5 담당 경계 (C-14)

원칙: **경계는 폴더 수준에서 갈린다.** 자기 전용 폴더 밖 수정은 해당 담당의 PR 리뷰 필수.

| 담당 | 전용 폴더 | 기획서 역할 대응 |
|---|---|---|
| 김명선 | `ingestion/` `orchestration/` `data/` `docs/DB_SCHEMA.md` | 데이터 파이프라인·오케스트레이션 설계 및 구현 |
| 이새봄 | `backend/` `agents/` `harness/` `tests/`(backend 관련) | 에이전트 로직·이중 검증 하네스·API |
| 한정현 | `frontend/` `docs/FRONTEND_MAP.md` | UI/UX·시연 데모 |
| 송병갑 | `infra/` `.github/` 루트 `docker-compose.yml`·`.env.example`·Dockerfile류 | 배포·CI/CD·blue-green·격리 보안 |

공유 파일 규칙:
- `agents/constants.py`: 실소유 새봄, 그러나 **변경 시 팀 채널 사전 공지 + 명선 리뷰 필수** (ingestion이 소비하므로).
- `docs/API_CONTRACT.md`: 변경 = 계약 변경. 팀 채널 공지 + 소비자(정현·새봄) 승인 후 머지.
- `experiments/`: 명선·새봄 공동. BP-4에서 검증된 로직만 `agents/qa/`로 이식.
- `backend/Dockerfile`: 폴더 경계의 명시적 예외 — 실소유 병갑(빌드·CI 결합), 변경 시 새봄 리뷰 필수. (대안: 실소유 새봄+병갑 리뷰 — 리뷰 미팅에서 확정, decisions.md 채번) (C-19)

---

## 4. DB 스키마 뼈대 (명선 SSOT — 계약 제안) — v0.2

```sql
-- 조직
workplaces(workplace_id PK, name, created_at)
admins(admin_id PK, workplace_id FK, email, pw_hash)
workers(worker_id PK, workplace_id FK, name, nationality, lang, created_at)  -- 최소 수집
invites(invite_code PK, workplace_id FK, expires_at, used_by)

-- 지식
documents(document_id PK, workplace_id FK, title, doc_type, data_class,
          status,              -- queued|indexing|awaiting_approval|published|failed (§2 document enum)
          uploaded_by, created_at)
chunks(chunk_id PK, document_id FK, seq INT, text,
       embedding vector(EMBEDDING_DIM))   -- C-2: 차원은 .env EMBEDDING_DIM. 기본 1024 (bge-m3).
                                          -- DDL 생성 스크립트가 config에서 읽어 렌더링. 하드코딩 금지.
glossary_terms(term_id PK, workplace_id FK, ko TEXT,
               translations JSONB,        -- C-7: {"vi": "...", "id": "..."} — 언어 확장 시 ALTER 불필요
               note,
               status,                    -- candidate|approved|rejected
               approved_by, created_at)
glossary_history(history_id PK, term_id, action, actor, payload JSONB, at)  -- append-only

-- 실행 이력·검증 (증빙 코어)
traces(trace_id PK, workplace_id, worker_id, kind,   -- ask|report|verify|approval|pipeline
       input JSONB, output JSONB, gates JSONB, model_used, llm_status, created_at)
verifications(verification_id PK, trace_id FK, method,  -- backtranslation|readback
              score REAL, passed BOOL, detail JSONB, created_at)
approvals(approval_key PK,        -- "{kind}:{source_id}" 안정 키
          workplace_id, kind,     -- term|document|content
          payload JSONB, status, decided_by, decided_at, created_at)

-- 학습·보고
learning_modules(module_id PK, workplace_id, title, lang, source_document_id, body JSONB)
quizzes(quiz_id PK, module_id FK, items JSONB)
quiz_attempts(attempt_id PK, quiz_id FK, worker_id FK, answers JSONB, score REAL, passed BOOL, at)
reports(report_id PK, workplace_id, worker_id, lang, original_text, ko_summary,
        severity,               -- info|warning|danger
        status,                 -- open|acked
        acked_by, created_at)

-- 배치 job (인메모리 dict로 시작 → 여유 시 테이블화. DL D-52 패턴)
```

원칙: `CREATE ... IF NOT EXISTS`만, DROP 금지(멱등·비파괴). PostgreSQL 예약어 컬럼명 금지(DL D-171 교훈 — column, order 등).
**순서 규칙 (C-2)**: 임베딩 모델 확정(M-02) → EMBEDDING_DIM 확정 → chunks DDL 작성. 역순 금지.

---

## 5. API 표면 (v1 계약) — v0.2

Base `/api/v1` (비즈니스 API). **운영 엔드포인트 `/health`, `/`는 루트 — Base 밖 (C-3).**
인증: admin=Bearer(admin_token), worker=Bearer(worker_token, QR 발급).
오류 body 공통: `{error_code, message_ko, detail}`. 계약 위반 = 422.

### 5.0 운영 (루트, 인증 없음)

| Method Path | 응답 | 비고 |
|---|---|---|
| GET /health | {status, version, slot, components{api,db,llm}} · 이상 시 503 | compose 헬스체크·CI 게이트·blue-green 판정이 소비 — **경로 변경 금지** |
| GET / | 안내 응답 | 현행 유지 |

### 5.1 온보딩

| Method Path | 요청 → 응답 | 권한 |
|---|---|---|
| POST /auth/admin/login | {email, password} → {admin_token} | - |
| POST /invites | {workplace_id, worker_name?} → {invite_code, qr_url, expires_at} | admin |
| POST /auth/qr | {invite_code, lang, nationality} → {worker_token, worker_id} | - |
| POST /workplaces · GET /workplaces/{workplace_id} | 등록/조회 | admin |
| GET /workers?workplace_id · GET /workers/{worker_id} | 목록/조회 | admin |

### 5.2 지식 파이프라인 (비동기 + 폴링)

| Method Path | 요청 → 응답 | 권한 |
|---|---|---|
| POST /documents | multipart(file, doc_type?, data_class) → 202 {job_id, document_id} | admin |
| GET /jobs/{job_id} | → {status, stages:[{name, status}], pending_approvals:[approval_key], alarms:[]} | admin |
| GET /documents?workplace_id · GET /documents/{document_id} | 목록/상세(chunks 미포함) | admin |

job 상태머신: queued → running → awaiting_approval ⇄(승인) → running → completed | failed.
승인 후 재개 = 백엔드 자동 resume, 클라이언트는 GET /jobs/{job_id} 폴링만 (M-03에서 확정).

### 5.3 승인 큐 (쓰기 단일 경로)

| Method Path | 요청 → 응답 | 권한 |
|---|---|---|
| GET /approvals?workplace_id&status=pending&kind | → [{approval_key, kind, payload, created_at}] | admin |
| POST /approvals/{approval_key}/decision | {action: approve\|reject, reason?} → {approval_key, status} | admin |

불변식: glossary·knowledge 반영은 이 경로로만. 승인 처리 = 동일 트랜잭션에서 본 테이블 반영 + history append. action 화이트리스트 외 값 = 422.

### 5.4 질의·음성 (근로자 코어)

| Method Path | 요청 → 응답 | 권한 |
|---|---|---|
| POST /stt | multipart(audio) → {audio_id, text, lang_detected} | worker |
| POST /ask | {text? \| audio_id?, lang, model?} → 아래 | worker |

**요청 검증 (C-12→C-16)**: §2 입력 배타 규칙 적용 — 위반 시 422 `{error_code: "input_exactly_one"}`.

`/ask` 응답 (계약의 심장 — 프론트와 byte 단위 합의 필요):

```json
{
  "trace_id": "…",
  "intent": "question",
  "answer": "…(근로자 모국어)",
  "ko_text": "…(한국어 병기)",
  "sources": [{"document_id": "…", "chunk_id": "…", "title": "…"}],
  "verification": {"backtranslation": {"score": 0.91, "passed": true}},
  "gates": {"format": true, "permission": true, "grounding": true},
  "llm_status": "ok", "model_used": "…"
}
```

근거 없음(grounding 실패) 시: 답변 대신 "모르겠음 + 관리자에게 질문 전달" 폴백 — 환각 응답 금지.

### 5.5 검증 — v0.2 (C-5)

| Method Path | 요청 → 응답 | 권한 |
|---|---|---|
| POST /verify/backtranslation | **{original_ko, translated_text, lang}** → {score, back_text, passed} | admin/worker |
| POST /verify/readback | {target_text, audio_id, lang} → {score, passed, matched, missed[]} | worker |

- `original_ko` = 비교 기준 원문(한국어). `translated_text` = 검증 대상 번역문(`lang` 언어). 플로우: translated_text를 ko로 되번역 → original_ko와 결정론 유사도.
- v0.1의 `{text, src_lang, tgt_lang}`은 **비교 기준(reference)이 없어 점수 계산이 성립하지 않는 결함 계약** — 폐기.
- 점수 산식 = 결정론(chrF로 시작, 의역 false-RED 시 임베딩 코사인으로 승격 — M-01). 임계값은 `harness/gates.py` 상수 1곳.

### 5.6 학습·퀴즈·보고·대시보드

| Method Path | 요청 → 응답 | 권한 |
|---|---|---|
| GET /learning/modules?lang | 모듈 목록(근로자 lang 기준) | worker |
| GET /learning/modules/{module_id} | 본문 + quiz_id | worker |
| POST /quizzes/{quiz_id}/attempts | {answers[]} → {score, passed, wrong_items[]} | worker |
| GET /learning/progress?worker_id\|workplace_id | 진행률·이해도 | admin/본인 |
| POST /reports | {text? \| audio_id?, lang} → {report_id, ko_summary, severity} — **입력 배타 규칙 적용(§2, C-16)** | worker |
| GET /reports?workplace_id&status · POST /reports/{report_id}/ack | 목록/확인 | admin |
| GET /dashboard?workplace_id | 진행률·이해도·미확인 보고·검증 통과율 집계 | admin |
| GET /traces?workplace_id&kind&worker_id · GET /traces/{trace_id} | 증빙 이력 | admin |
| GET /models | Ollama 모델 목록 | admin/worker (`/api/v1/models` — M-07) |

---

## 6. 호출부 (콜 그래프) — 경로 v0.2 반영

### 6.1 질의 플로우 — POST /api/v1/ask

```
app/routers/ask_router.ask()
 └─ app/services/ask_service.run_ask(worker, req)
     1. agents/qa/intent_classifier.classify(text)   # LLM 제안 → INTENT_TYPES 필터(constants)
     │    └─ intent=report → report_service로 위임 / practice → readback 안내
     2. asyncio.gather(                              # 기획서 "병렬 수행"
     │    agents/qa/retriever.retrieve(text_ko, workplace_id),  # glossary 보정 → pgvector 검색
     │    agents/qa/translator.to_ko(text, lang) )   # (입력이 모국어면 선번역)
     3. agents/qa/answerer.answer(question_ko, chunks, glossary)  # 근거 인용 강제 프롬프트
     4. agents/verifier/response_verifier.check(answer, chunks, worker)  # 게이트 3종 결정론
     │    format: JSON/길이/금칙 · permission: worker의 data_class 접근 · grounding: 근거 인용 존재
     │    → 실패 시 폴백 응답(모름+관리자 전달), 절대 silent 통과 금지
     5. agents/qa/translator.to_worker_lang(answer_ko, lang)
     6. agents/verifier/backtranslation.verify(original_ko=answer_ko,
                                               translated_text=answer_lang, lang)  # C-5 시그니처
     7. harness/trace.record(kind="ask", …)          # 전 건 — 실패도 기록
     8. → AskResponse
```

### 6.2 지식 구축 배치 — POST /api/v1/documents

```
app/routers/knowledge_router.upload()
 └─ app/services/knowledge_service.start_job(file, meta)   # job 등록 → 202 즉시 반환
     └─ asyncio.create_task(_run_pipeline(job_id))         # D-147 패턴 (Dagster 연결 전 임시)
         1. ingestion/ingestor.extract(file)               # 텍스트/표 추출
         2. ingestion/doc_classifier.classify(text)        # LLM 제안 → DOC_TYPES 필터
         3. ingestion/pii_masker.mask(text)                # 규칙 우선, 마스킹 내역 trace
         4. ingestion/term_extractor.extract(text)         # 용어 후보 → approvals 적재(kind=term)
         5. ingestion/indexer.index(chunks)                # 임베딩 → pgvector (LLM 0)
         6. status = awaiting_approval                     # 관리자 승인 게이트에서 suspend
         (approval decision → 승인분 반영 → job.status=completed, document.status=published — enum 2종 각각 전이, §2 C-6)
         * 각 단계 결과 trace.record(kind="pipeline")
         * BP-4: orchestration/(Dagster)이 위 단계를 op 단위로 인수 — 호출 시그니처는 동일 유지
```

### 6.3 상향 보고 — POST /api/v1/reports

```
app/routers/report_router.create()
 └─ app/services/report_service.create(worker, req)
     1. (audio_id면) stt 결과 사용
     2. agents/qa/translator.to_ko(text, lang)
     3. llm adapter로 ko_summary + severity 제안 → SEVERITIES 필터
     4. harness/trace.record(kind="report") + reports INSERT
     5. → 대시보드 미확인 카운트에 반영 (admin ack 전까지 open)
```

### 6.4 LLM 호출 규율 (전 모듈 공통 — ingestion 포함)

```
모든 LLM 호출 = app/llm/adapter.generate() 경유 (직접 httpx 금지)
 └─ llm_router.route(data_class, purpose) → target   # 결정론:
      internal/sensitive → on-prem Ollama 강제
      public + 번역류    → 외부 API 허용 (키 있을 때)
 └─ 실패 시 {"_llm_failed": true, "error", "model_attempted"} — 빈 결과 위장 금지
 └─ 호출부는 try_parse_llm()로 파싱, 실패 시 llm_status="failed" 표면화
```

---

## 7. 핵심 파일 스텁 (시그니처 계약) — import 경로 v0.2

### agents/constants.py — 화이트리스트 단일 소스

```python
DOC_TYPES      = frozenset({"process", "instruction", "safety", "equipment"})
INTENT_TYPES   = frozenset({"question", "report", "practice", "smalltalk"})
LANGS          = frozenset({"ko", "vi", "id"})
DATA_CLASSES   = frozenset({"public", "internal", "sensitive"})
SEVERITIES     = frozenset({"info", "warning", "danger"})
APPROVAL_KINDS = frozenset({"term", "document", "content"})
```

### backend/app/llm/adapter.py

```python
async def generate(prompt: str, *, system: str = "", model: str | None = None,
                   data_class: str = "internal", fmt_json: bool = True) -> dict:
    """단일 LLM 진입점. llm_router로 타깃 결정 → 호출.
    실패 시 {"_llm_failed": True, "error": str, "model_attempted": str} 반환 (raise 아님)."""

def try_parse_llm(raw: dict) -> tuple[dict | None, str | None]:
    """(parsed, error). 코드펜스 제거·첫 {} 추출 보정 포함."""
```

### backend/app/llm/llm_router.py

```python
def route(data_class: str, purpose: str) -> LlmTarget:
    """결정론 규칙만. LLM 판단 0.
    internal/sensitive → ONPREM(Ollama). public → EXTERNAL 허용(설정 시)."""
```

### harness/trace.py

```python
def record(*, kind: str, workplace_id: str, worker_id: str | None,
           input: dict, output: dict, gates: dict | None = None,
           model_used: str | None = None, llm_status: str = "ok") -> str:
    """모든 판단·변환·검증 기록. 실패도 기록(감사 누락 0). returns trace_id."""
```

### harness/gates.py

```python
BACKTRANSLATION_THRESHOLD = 0.85   # BP-3에서 실측 캘리브레이션 (M-01)
READBACK_THRESHOLD = 0.80

@dataclass
class GateResult:
    format: bool; permission: bool; grounding: bool
    @property
    def passed(self) -> bool: ...
    def to_dict(self) -> dict: ...
```

### backend/app/services/ask_service.py

```python
async def run_ask(worker: Worker, req: AskRequest) -> AskResponse:
    """§6.1 플로우 그대로. 게이트 실패 = 폴백 응답(모름+관리자 전달), 예외 은닉 금지."""
```

### agents/verifier/backtranslation.py — v0.2 (C-5)

```python
async def verify(original_ko: str, translated_text: str, lang: str) -> BacktranslationResult:
    """translated_text(lang) → ko 되번역 → original_ko와 결정론 유사도.
    returns score / passed / back_text."""
```

---

## 8. 테스트 뼈대 (게이트 증거 = pytest, DL D-182 방식)

| 테스트 | 단정 |
|---|---|
| test_contracts.py | constants 화이트리스트 ↔ Pydantic Literal ↔ DB enum 3자 일치 (DL guardrails 누락 버그 재발 방지) |
| test_ask_flow.py | LLM stub으로 질의 e2e — 응답 스키마·trace 생성·grounding 폴백 |
| test_gates.py | 결함주입: 근거 없는 답변 → grounding RED / 권한 밖 data_class → permission RED (비공허 증명) |
| test_approval_history.py | approve/reject 시 history 1행 동반 — 불변식. history 없는 쓰기 경로 존재하면 RED |
| test_llm_router.py | sensitive가 EXTERNAL로 라우팅되면 RED — 온프레미스 보안 명제의 자동 증거 |

**CI 연동 (감사 #5)**: BP-3에서 tests/ 생성과 **동시에** ci.yml verify job에 pytest 단계 추가. branch protection(main, Require status checks)은 GitHub Settings에서 실강제 확인 — 담당 병갑.

---

## 9. BP 로드맵 매핑 — v0.2

| 시기 | 본 문서 관련 작업 |
|---|---|
| BP-2 (지금~8/10, 코드 동결) | 본 v0.2 팀 리뷰 → 7/25 계약과 대조·병합 → `docs/` 커밋(SKELETON·API_CONTRACT·DB_SCHEMA·FRONTEND_MAP). **동결 예외: `experiments/` — 예선 정량 실험(용어 오역률 baseline·RAG 보정·백트랜슬레이션 검출률, ~8/6) (C-9)** |
| BP-3 (8/11~8/20, 저강도) | §3 트리 생성 + §7 스텁 + §8 테스트 골격 + **§11 스켈레톤 DoD 달성** (새봄: 승인 큐 데이터 모델·routers/schemas · 병갑: compose ollama/frontend 서비스·CI pytest 게이트 · 정현: FRONTEND_MAP 기반 화면 스텁 · 명선: ingestion 스텁·DDL). 탈락 시 손실 최소 = 문서·스켈레톤까지만 |
| BP-4 (8/21~8/31, 본 구현) | 전반: ask 플로우·검증 하네스·STT 실장, `experiments/` 검증 로직 → `agents/qa/` 이식, 명선 Dagster가 ingestion/ 호출부 연결. **후반: learning/quiz/dashboard 실장 (C-9 — 시연 시나리오 종착점)** |
| BP-5 (본선 D-4~) | 기능 동결 + 시연 시나리오: 업로드→승인→질문→백트랜슬레이션 점수→되말하기→대시보드 |

---

## 10. 미결 (팀 결정 필요 — decisions.md 채번) — v0.2

| # | 항목 | v0.2 제안 (리뷰에서 채택/기각) |
|---|---|---|
| M-01 | 유사도 산식 + 임계값 캘리브레이션 | **chrF로 시작**(sacrebleu, 완전 결정론·D-68 부합). 캘리브레이션에서 의역 케이스 false-RED율 높으면 임베딩 코사인으로 승격 — 승격 조건까지 decisions.md에 명기 |
| M-02 | 임베딩 모델 | **bge-m3 확정 제안**(README 기왕 명시, 1024차원). `EMBEDDING_DIM=1024` 설정값. BP-3 초 vi/id 스모크 테스트로 품질 확인만. **DDL 작성 전 확정 필수 (C-2)** |
| M-03 | job 승인 후 resume | **자동 resume** — 시연에서 승인 버튼 → 진행바 자동 재개가 데모 임팩트·프론트 부담 모두 유리 |
| M-04 | 외부 API 사용 범위 | **public 번역만 외부 허용 유지** — 등급별 라우팅이 발표 보안 명제이므로 라우터가 시연에서 살아 있어야 함(`model_used`로 라이브 증명). 플랜 B = 외부 키 없이 전 기능 온프레미스 동작(adapter 폴백으로 무비용) |
| M-05 | worker_token 수명 | 데모 스코프: 만료 24h·재발급 없음. decisions.md에 "데모 한정" 태그 |
| M-06 | 7/25 회의 계약 diff | 회의록 대조 후 본 문서 갱신 — **리뷰 미팅 안건 1번** |
| M-07 | `/models` 위치 | `/api/v1/models` 제안(프론트 소비용). 운영 루트로 둘 근거 있으면 리뷰에서 반론 |
| M-08 | Dagster 컨테이너 | dev compose 포함 여부 / BP-4 합류 시점의 기동 방식 — 명선·병갑 (감사 #10) |
| M-09 | Whisper 배치 | backend 프로세스 내 faster-whisper vs 별도 컨테이너 / GPU 유무 — 새봄·병갑 |
| M-10 | audio 저장 위치 | `/stt`의 `audio_id`가 가리키는 저장소: 로컬 볼륨 vs S3 — 병갑 |

---

## 11. 스켈레톤 DoD — "비어 있지만 돌아가는" 완료 기준 (신설, C-8)

BP-3 종료는 아래 전 항목 충족으로 판정한다.

1. `docker-compose up` 한 번에 db(pgvector)·ollama·backend·frontend 기동. `.env.example` 복사만으로 충분(추가 수동 설정 0).
2. 루트 GET /health: 200/503 판정 기준은 components.db (현행 코드 계약). llm은 ollama 모델 미탑재 시 components.llm="degraded" + 최상위 status="degraded"로 표면화하되 200 유지. (health 로직의 거처 = app/services/system_service.py — C-17, C-20)
3. §5의 **전 엔드포인트가 존재**하고, 계약 예시와 동일한 형태의 mock JSON을 반환 (LLM·STT는 stub — `llm_status:"ok"`, 고정 응답).
4. mock 판별 가능: mock 응답에 `"mock": true` 필드 포함 — 실제 구현 교체 시 제거 (통합 지점마다 grep으로 잔여 mock 확인).
5. frontend가 mock API만으로 핵심 화면 3종(모국어 질의·학습/퀴즈·관리자 대시보드) 클릭 가능한 상태로 렌더.
6. §8 테스트 5종이 존재하고 전부 통과(스텁 대상), CI에서 pytest 게이트로 실행됨.
7. `agents/constants.py` frozenset 6종 존재, `harness/gates.py` 임계값 상수 존재 — 매직넘버 grep 0건.
8. 본 문서·API_CONTRACT·DB_SCHEMA·FRONTEND_MAP·decisions.md가 레포에 커밋되어 있음.

---

## 부록 A. 감사 리포트(2026-08-04) 반영 현황

| 감사 # | 항목 | v0.2 처리 |
|---|---|---|
| 1 | SKELETON.md 미추적 | 채택 절차에 커밋 명시 (본 문서 헤더) |
| 2 | vector(768) vs bge-m3 모순 | C-2 — EMBEDDING_DIM 설정화 + M-02 |
| 3 | POSTGRES_PASSWORD 폴백 | C-15 — `:?` 필수화 규칙 (수정 자체는 병갑 담당) |
| 4 | deploy.yml 부재 | §3 트리에 명시, 기한 8/4 — 병갑 |
| 5 | CI pytest 게이트 부재 | §8 CI 연동 조항 신설 |
| 6 | backend/app 레이아웃 | C-1 — 문서를 코드에 맞춤 |
| 7 | /health vs /api/v1 | C-3 — §5.0 운영 계층 신설, 경로 변경 금지 명시 |
| 8 | ingestion/ 구획 충돌 | C-4 — ingestion 공식화, 담당 명선, §6.4 규율 유지 |
| 9 | BP-2 docs 산출물 부재 | §9 BP-2 행에 4종 명시 |
| 10 | compose ollama/frontend·Dagster·Whisper | §11 DoD-1 + M-08/M-09 채번 |
