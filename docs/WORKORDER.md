# WORKORDER v2 — 4트랙 작업지시서 (V1~V7) · 8/25 개정 (G1~G7 반영)

## §0. 역할 3층 구조와 세션 부트스트랩 (G1)

### 0-1. 3층 구조 — 누가 무엇을 결정하는가
| 층 | 실체 | 하는 것 | 못 하는 것 |
|---|---|---|---|
| 총괄 Master | 명선의 claude.ai 세션 (챗 제목 `MS \| …`) | 게이트 PASS/FIX 판정 · M-xx 확정 채번 · 계약(skeleton·BLUEPRINT) 개정 승인 · HANDOFF 취합 | — |
| 트랙 Master | 각 팀원 자신의 claude.ai 세션 (챗 제목 `SB \| …` 등) | 자기 트랙 설계 구체화 · 자기 CC 지시 프롬프트 작성 · CC 보고 검증(코드 인용 확인) · 자기 HANDOFF 저작 · M-xx 후보 제안 | 게이트 판정 · M-xx 확정 · 계약 문서 수정 · 타 트랙 지시 |
| Executor | 각 팀원의 로컬 Claude Code | 구현 · 자체 테스트 · 결과 보고(파일/라인 + 확인 방법 실행 출력) | 설계 판단 · 계약과 다른 임의 구현 · 판정 |

일일 흐름: 총괄이 WORKORDER 발행 → **트랙 Master가 자기 구간을 CC 지시 프롬프트로 구체화** → Executor 구현·보고 → 트랙 Master 검증 → 밤 게이트에 HANDOFF 제출 → 총괄 판정(PASS/FIX).
계약을 바꿔야 할 때: 트랙 Master가 "M-xx 후보: <내용> / 사유: <근거>"로 총괄에 제안만 — 채번·확정은 총괄 전용.

### 0-2. 트랙 Master 부트스트랩 (팀원이 자기 claude.ai 새 챗에 복붙)
```
나는 MoGuk 트랙 Master(코드: SB|JH|BG)다. 담당 = docs/WORKORDER.md §4의 내 트랙.
읽기: WORKORDER §0~§3 + 내 트랙 표 → docs/skeleton-v3.md §2(DDL)·§3(API)·§4(시그니처) → docs/BLUEPRINT.md 내 트랙 관련 §.
내 권한: 트랙 내 설계 구체화·CC 지시 작성·보고 검증·HANDOFF 저작. 게이트 판정·M-xx 확정·계약 수정은 불가.
계약 변경 필요 시 "M-xx 후보: <내용> / 사유: <근거>"로 총괄(명선)에 제안만 한다.
작업: [오늘 구간 V_-_] — 위 계약 기준으로 CC(Executor)에 내릴 지시 프롬프트를 작성해달라.
```

### 0-3. Executor 부트스트랩 (트랙 Master가 CC에 복붙)
```
나는 MoGuk 트랙 Executor(코드: MS|SB|JH|BG)다. 지시자 = 내 트랙 Master이며,
이 WORKORDER의 내 트랙 표와 트랙 Master의 지시 프롬프트만 실행한다.
읽기: ① 이 문서 §0~§3 ② docs/skeleton-v3.md §2(DDL)·§3(API)·§4(시그니처) — 계약, 위반 금지
③ docs/BLUEPRINT.md 내 트랙 관련 §만. 설계 변경·M-xx 판단 권한 없음 — 막히면 보고.
계약과 다른 구현이 필요해 보이면 중단하고 [코드|V_-_] 접두로 트랙 Master에 보고.
완료 보고 = 각 행의 "확인 방법" 실행 결과 원문 첨부.
```

## §1. 공통 규칙
- Git (전문은 docs/GIT_RULES.md — 병갑 원문 커밋 전까지 아래 5줄이 기준):
  main 직push 금지 · 브랜치 `feat/<코드소문자>-<주제>`(예: feat/sb-rag) · 작업 시작 = Draft PR 즉시 오픈
  · 커밋 `타입(범위): 요약` · 머지 = CI green + 리뷰 1인(급하면 승인 후 self-merge) + 충돌 해소는 작성자
- 로그 접두 `[코드|V게이트-구간|MMDD HH:MM]` · 막힘 2h 채널 공유 / 4h 총괄 에스컬레이션
- 챗 제목 `코드 | V_-_ | 내용` · 일정: V6=8/30, V7=8/31, 9/1 기본 휴무(합의 이월만), 본선 9/2(수)–3(목)
- 측정 #번호 정의 = docs/BLUEPRINT.md §5 (G6)

## §2. 0단계 (전원, V1 · 26 수 오전 마감)
1. `git checkout main && git pull` → `cp .env.example .env`
2. .env 채우기 (G7): 비밀번호·시크릿 4종(POSTGRES_PASSWORD, EDGE_DB_PASSWORD, JWT_SECRET, TENANT_CRYPTO_KEY)은
   각각 `python -c "import secrets;print(secrets.token_urlsafe(32))"` 로 생성해 기입.
   EXTERNAL_LLM_API_KEY = 빈 값 유지(배포 env 전용). PROVIDER/MODEL 키는 병갑 V2-2 후 생김 — 없어도 정상.
3. `docker compose up -d` (stt·dagster·edge-db 안 뜨는 게 정상 — profile full)
4. 확인: core `/health` 200+db ok · edge `/health` 200 · mock `/ask`
   — Windows 한글 body는 `curl --data-binary @질문.json` (UTF-8 파일). `-d` 직접 입력 금지(cp949 400)
5. 보고 `[코드|V1|MMDD HH:MM] 통과, docker <버전>` — WSL 신규 설치자 재부팅 1회, 로컬 웹서버 사용자 caddy 80/443 충돌 주의

## §3. 트랙 간 의존 그래프 (G3 — 대기 조건)
```
MS V2-1(시드 확정, 26 오전) ──→ MS V2-2(적재) ──→ SB V2-2(RAG 실구현: 적재 완료 전엔 mock 유지)
SB V2-2(/ask 실응답) ──→ JH V2-1(화면 실연동: 그 전엔 mock 계속)
BG V2-1(EC2)+V2-2(CD·URL) ──→ V4 "배포 URL" 조건 · BG V2-2(.env.example 키) ──→ SB V2-1 외부 API 배포 반영
SB V3-1(위험보고 API) ──→ JH V3-2(위험보고 관리 화면) · MS V3-1(퀴즈 적재) ──→ JH V3-1(퀴즈 화면 실데이터)
```
대기 발생 시: 자기 트랙 다음 구간 선행 착수(mock 기준) — 유휴 금지.

## §4. 트랙별 지시 (DoD 전 행 검증 가능 명령 포함 — G5)

### MS 명선 (pipeline/ · experiments/ · data/ · db/migrations/) — 권장: Fable 5 높음(설계·판정) / Sonnet(감수)
| 구간 | 작업 | 확인 방법 (완료 판정) |
|---|---|---|
| V2-1 (26오전) | 시드 초안 감수·확정 + KOSHA 발췌 수집. draft:true 항목 검수 후 유지(원어민 검수 전) 단 오류 수정 | `ls data/seed/manuals data/seed/glossary experiments/testset` 전 파일 존재 + glossary 50건 `python -c "import json;print(len(json.load(open('data/seed/glossary/glossary_50.json'))))"` = 50 |
| V2-2 (26오후) | 인제스천 실행(분류→마스킹→청킹 500–800/오버랩100→bge-m3→적재) + 새봄 페어 | `docker compose exec postgres psql -U <u> -d <db> -c "SET search_path TO tenant_axis_demo; SELECT count(*) FROM documents; SELECT count(*) FROM chunks; SELECT count(*) FROM glossary;"` → 각각 >0, >0, =50 |
| V3-1 (27) | glossary_candidates 에셋 + 퀴즈 시드 적재 + generate_quiz 1회 실행→draft 상태 확인 | Dagster UI 자산 그래프 스크린샷 + `SELECT count(*) FROM quiz_sets WHERE status='draft'` ≥1, `WHERE status='approved'` ≥2 |
| V4-1 (28) | 데모 대본(질문 5+실패 대체) + V4 검증 주재(코어 6스텝) | docs/WORKLOG/V4_demo_script.md 커밋 + [GATE|V4] 판정 엔트리 기록 |
| V5-1 (29) | manager_report 에셋(일/월) + 안전 코스 시드 연결 | Dagster에서 manager_report materialize 성공 + 산출물(리포트 텍스트) 경로 보고 |
| V6-1 (30) | 실험 #1·#2·#3 실행, τ 확정(M-10a 닫기) (정의 = BLUEPRINT §5) | `experiments/results/` 에 결과 json 3종 + ROC 곡선 이미지 1장 커밋, skeleton §8 M-10a '확정' 갱신 |
| V7 (31) | 발표자료 완성(APPEAL_POINTS→슬라이드) + 리허설 2 + V7 판정 + v1.0 태깅 | 슬라이드 파일 공유 + [GATE|V7] 엔트리 + `git tag v1.0` |

### SB 새봄 (backend/) — 권장: Fable 5 높음(에이전트 설계) / CC 기본
| 구간 | 작업 | 확인 방법 |
|---|---|---|
| V2-1 (26) | llm_adapter 실구현: local=ollama qwen3:8b, external=openai gpt-4o-mini(external timeout 8s (LLM_TIMEOUT_EXTERNAL_S, M-30), external→local 폴백, tier_used 기록). FakeLLM 교체 | `pytest tests/ -k adapter` green(신규 테스트 포함) + core /health llm=ok + 외부 키 제거 상태에서 호출 시 local 폴백 동작 로그 |
| V2-2 (26) | RAG /ask: retrieve(top-k=4, meta_filter)→근거 강제 프롬프트→sources·trace·latency 기록. grounded=false→unanswered_queue insert | `curl --data-binary @q_vi.json .../api/v1/ask` → sources 길이≥1 + trace_id 존재. 무근거 질문 1건 → `SELECT count(*) FROM unanswered_queue WHERE status='open'` ≥1 |
| V3-1 (27) | 위험보고: POST /reports 202 즉시 + jobs 워커(SKIP LOCKED, STT→요약+severity 로컬 티어, 3회 실패 시 보존+알림). **수신 구조 = S3 단기 버퍼 → core outbound pull(M-25). 텍스트 보고·/ask 등 실시간 요청은 M-28 릴레이 — 파라미터는 §5 합의 후** | 텍스트 보고 → 202 + 5초 내 `SELECT ko_summary, severity, status FROM risk_reports ORDER BY id DESC LIMIT 1` → 요약 not null, status='submitted' |
| V3-2 (27) | 인증(초대 토큰→PIN 해시→JWT/리프레시) + 하트비트 스케줄러(core→edge) | activate→login→JWT로 보호 엔드포인트 200, 무토큰 401. edge /health core_relay=ok(age_s < 60) |
| V4-1 (28) | 게이트 C+A: verify_backtranslation(bge-m3 코사인, τ 가값 0.80)·is_high_risk(OR)·안전만 차단+전체 배지 | corrupted_30 중 negation 1건 질의 → 응답 gated=true("관리자 확인 필요") + 일반 질의 → verify.score 배지 존재 |
| V5-1 (29) | 상담챗(학습상태 주입, 로컬 고정) + crypto seal/open + 퀴즈 생성 파이프 연결 | /chat 응답 + `SELECT count(*) FROM conversations` ≥2 + `pytest -k crypto` 왕복 green + trace route.tier='local' 확인 |
| V6~V7 (30–31) | 측정 지원 #2·#4·#5 (정의 = BLUEPRINT §5) + 안정화 + 리허설 | #2: `SELECT count(*) FROM questions WHERE grounded=false AND answer IS NOT NULL` = 0 쿼리 결과 캡처 · #5: 외부 차단 후 10요청 성공률 로그 |

### JH 정현 (frontend/) — 권장: Sonnet(마크업) / Fable 5(플로우 설계)
| 구간 | 작업 | 확인 방법 |
|---|---|---|
| V2-1 (26) | 근로자 질문 화면 실연동(vi, 근거 출처 뱃지, trace_id), QR/초대 진입·언어 선택. SB V2-2 전엔 mock | 모바일 뷰포트(390px) 스크린샷: 질문→답변+근거 뱃지 렌더. 채널 공유 |
| V3-1 (27) | 학습카드+퀴즈 제출(점수·라벨 3색: red/yellow/green) + 알림함 | 퀴즈 제출→89점 시나리오 yellow 라벨 스크린샷 + 알림함 읽음 처리 동작 |
| V3-2 (27) | 관리자: 대시보드 KPI 4종+추이+근로자/모듈별, 승인큐(approve/reject), 위험보고(ack/resolve, 요약 우선+세부 버튼) | 대시보드에서 미확인 위험보고 카운트가 SB V3-1 데모 보고 건과 일치 + ack 클릭 후 카운트 감소 스크린샷 |
| V4-1 (28) | 통합 폴리싱: 모바일·로딩/에러·게이트 차단 표시("관리자 확인 필요") | V4 리허설에서 코어 6스텝 UI 무중단(명선 판정에 포함) |
| V5-1 (29) | 안전 모듈 화면+교육일지 출력(HTML 인쇄) + 상담챗 UI + in 리소스 | 일지 인쇄 미리보기 스크린샷(일시·구분·강사·참석자·이해도 필드 표시) + in 전환 스크린샷 |
| V6~V7 (30–31) | 시연 UI 다듬기 + 리허설 | 리허설 1·2 UI 이슈 0건 보고 |

### BG 병갑 (infra/ · workflows · compose) — 권장: Fable 5 높음(배포 설계) / CC 기본
| 구간 | 작업 | 확인 방법 |
|---|---|---|
| V2-1 (26, 최우선) | EC2 프로비저닝(t3.xlarge·50GB gp3·80/443·SSH 화이트리스트) + qwen3:8b/4b pull | `ollama list` + `df -h` 캡처 + EC2 IP 채널 공유 |
| V2-2 (26) | CD(main→GHCR→EC2 pull&up) + Caddy HTTPS + prod `ports: !reset []` + .env.example에 EXTERNAL_LLM_PROVIDER/MODEL 키 추가 + docs/GIT_RULES.md 커밋(본인 원문+합의 수정 3건) | main 더미 커밋 → 자동 배포 확인 + `curl -s https://<도메인>/health` 200 + 브라우저 자물쇠 스크린샷 |
| V3-1 (27) | stt 컨테이너 기동(small int8, core_net) + 헬스체크 크론·웹훅 + **V3 통과 직후 첫 pg_dump→일일 크론(S3)** | stt /v1/transcribe 샘플 음성 → text 반환 + S3에 덤프 파일 존재 `aws s3 ls` 캡처 |
| V4-1 (28) | 배포 URL 전 경로 검증·부하 확인·restart:always | 배포 URL에서 V4 코어 6스텝 완주(명선 판정 참여) + `docker inspect` restart 정책 캡처 |
| V5-1 (29) | 동결 지원 + edge-db 포함 판정(M-23) 총괄 보고 | M-23 판정 근거 1줄 보고 → 총괄 확정 |
| V6~V7 (30–31) | blue-green 승격+전환 시연, 배포 리허설, GPU 전환 최종 판단 | V7에서 무중단 전환 시연: 구버전→신버전 전환 중 `/health` 연속 200 로그 |

## §5. 합의 대기 계약 (G2 — 새봄·병갑, 27일 오전까지 합의 → skeleton §3 반영)
릴레이 계약(M-28) 총괄 초안:
```
POST /internal/relay/enqueue    (edge 내부 함수가 큐 적재 — 외부 미노출)
GET  /internal/relay/pending    (core outbound 폴링: 미처리 요청 batch)
POST /internal/relay/{id}/respond (core → edge 응답 회신 → edge가 대기 중 HTTP 응답 완결)
※ 전부 core→edge 방향 또는 edge 내부 — M-22 준수. 폴링 주기·batch 크기·타임아웃은 새봄·병갑 합의로 확정.
미디어(M-25)는 엔드포인트 불요 — edge가 S3 직접 적재(write-only IAM), core가 S3 pull.
```

## §6. 후속 체크박스 (PR #4 본문에 기재)
- [ ] G2: 릴레이 계약(M-28) 파라미터 합의 — 새봄+병갑, 27일 오전까지 → skeleton §3 반영
- [ ] G4: docs/GIT_RULES.md 병갑 원문 커밋 (BG V2-2 행에 포함됨)
- [ ] M-23: edge-db 판정 (V5, 병갑 보고→총괄 확정)
