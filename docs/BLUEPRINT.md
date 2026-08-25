# MoGuk(이음) BLUEPRINT v1 — 개발 청사진 (설계 SSOT)

> 8/25 발행 · 상위 계약: 예선 제출 문서 · 세부 계약: docs/skeleton-v3.md(DDL·API·시그니처 원문) · 실행 규칙: PROTOCOL.md·GOVERNANCE.md·WORKORDER.md
> 이 문서는 "무엇을 어떻게 만드는가"의 단일 길잡이다. 모든 결정은 M-xx로 잠겨 있고, 변경은 총괄 Master 채번으로만.

## 문서 위계 (M-24)
- 목표(상위 계약): docs/PRELIM_PROPOSAL.md — 모든 문서·구현은 이를 이행한다. 원문 수정 금지.
- 결정 대장: skeleton-v3 §8 M-xx — 목표·설계·계약의 모든 변경은 여기로만 들어온다(R5).
  예선 문서와 다른 모든 결정은 변경 사유 필수(R6) — 심사·발표 방어의 근거가 된다.
- 개념별 원문 소유(R4): DDL→db/migrations/001 · API·시그니처·M-xx 대장→skeleton-v3
  · 설계 서사·근거→BLUEPRINT · 게이트·일정·컷라인→WORKFLOW · 운영 사이클→PROTOCOL
  · 거버넌스→GOVERNANCE · 작업 배분→WORKORDER · 게이트 검증→GATE_CHECK · 발표 논거→APPEAL_POINTS
- 충돌 시: 해당 개념의 소유 문서가 우선. 목표와 계약이 어긋나면 산문을 고치지 말고 M-xx로 계약을 고친다.
- 읽기 진입점: 최초 1회 PRELIM_PROPOSAL 필독 → 이후 세션은 BLUEPRINT → WORKFLOW → skeleton-v3 → PROTOCOL → 최신 HANDOFF

## 1. 한 줄 정의
50인 미만 제조 사업장의 외국인 근로자(vi·in)가 모국어로 배우고(학습카드·퀴즈), 묻고(RAG 질의응답), 보고하며(위험 보고), 관리자는 이해도를 데이터로 확인하는 플랫폼. 핵심 주장 = "번역이 아니라 이해의 증명" + 민감 데이터 온프렘 격리.

## 2. 시스템 아키텍처

### 2-1. 존 구조 (M-19·22 확정)
```
[core_net — internal:true, 외부 라우트 0]          [edge_net]
postgres(스키마=테넌트) · ollama(qwen3:8b/4b)       caddy(80/443, HTTPS)
stt(faster-whisper small int8) · core-api           edge-api · frontend
dagster · (jobs 워커: core-api 내장)                (edge-db: profile full, M-23 미정)
        └── core→edge outbound 단방향만 (하트비트 POST /internal/core-heartbeat)
불변 조건: core-api는 edge_net에서 리슨하지 않는다 / edge-api는 core를 호출하지 않는다
edge는 내부 DB 자격증명·호스트명을 보유하지 않는다 (차단 = 방향이 아니라 능력)
```

### 2-2. LLM 티어 라우팅 (M-03·17 확정)
- `complete(prompt, tier)` 단일 어댑터. tier="local"=ollama qwen3:8b(폴백 4b), tier="external"=openai gpt-4o-mini(timeout 8s → 로컬 자동 폴백, tier_used 기록)
- 티어 정책: 사업장 지식·상담·위험보고·PII = **로컬 고정**. 외부는 비민감 일반 번역 전용(용어사전 프롬프트 주입).
- 임베딩 = bge-m3/1024 전역 고정 (M-02, 비가역 — 변경 시 chunks 전체 재적재)

### 2-3. 실시간 vs 비동기 (예선 문서 첨부 9 이행)
- 실시간(≤3홉): classify → [retrieve ∥ translate] → verify → 응답. 라우터가 검증 겸임.
- 비동기: Dagster 에셋 그래프 `documents_raw → chunks_index → glossary_candidates → quiz_bank → manager_report` (에셋명=테이블명, UI 그래프=lineage 시연. M-16: Airflow→Dagster, 발표 한 줄 선제 처리)
- 준실시간 잡: PG `jobs` 테이블 + FOR UPDATE SKIP LOCKED 폴러(Redis 없음) — 위험보고 STT·요약, 관리자 답변 편입

## 3. 데이터 계층 (M-04 스키마 분리 — 상세 DDL은 migrations/001이 원문)
- 테넌트 = PG schema-per-tenant, 미들웨어 search_path. 시연 킬샷: `\dn`
- 21테이블 요지: documents(origin: upload|admin_answer|seed) / chunks(vector 1024 + meta JSONB: category·machine) / glossary(term_ko·vi·in, draft→approved) / quiz_sets·items·attempts / **v_comprehension 뷰 = 세트별 최신 점수, 라벨 <80 red·80–89 yellow·≥90 green (M-01: 통과 90, 재시험, 임계값 tenant_settings 보관·UI 미노출)** / questions(=qa_logs: sources·grounded·trace JSONB·latency) / unanswered_queue / conversations(risk_flag) / notifications(범용 쪽지, M-06) / risk_reports / jobs / phrases·speaking_records / safety_courses·records / access_logs / invites·workers·admins
- lineage(M-09) = questions.trace JSONB(classify→retrieve hit·score→route tier→verify score) + chunks.meta, GIN 인덱스. 시연: "이 답이 왜 나왔나"를 쿼리 한 줄로.

## 4. 기능별 설계 (결정 번호 포함)

### 4-1. RAG 질의응답 (V2 빌드)
업로드 문서 → 인제스천(분류 4종 태깅→PII 마스킹→청킹 500–800/오버랩 100→bge-m3→pgvector) → /ask: retrieve(top-k=4, meta_filter) → 근거 강제 프롬프트("자료 근거로 vi 답변, 근거 없으면 모른다") → sources·trace 기록. **grounded=false → 응답 차단 + unanswered_queue 이관(M-05)** → 관리자 답변 → documents(origin='admin_answer') 자동 편입 = 축적 루프 3입구 중 하나(나머지: 용어 후보, 반복질문→퀴즈).

### 4-2. 검증 게이트 (V4 빌드, M-10)
- 이중 검증 축소판(6번 결정 C+A): **안전 카테고리만 차단 게이트** — verify_backtranslation = 되번역↔원질문 bge-m3 코사인, τ 미달 시 "관리자 확인 필요" 폴백. 나머지 응답은 점수 배지만.
- 고위험 판정 주체 = 시스템 자동 OR 조건(질의 classify=safety ∨ 상위 청크 meta.category=safety), 기준 소유 = 관리자(오버라이드는 M-21 이월).
- τ = 가값 0.80 → 8/30(V6) 실측 확정(M-10a): 오염 30건(term_swap·negation·number ×10) ROC, "오탐≤10%에서 검출 최대" 지점. 결과가 기획서 "[측정 후 기입]" 칸.
- 되말하기(M-12): 고위험 문구만 녹음 저장·재생(자동 채점 없음), 일/월 manager_report에 목록 편입.

### 4-3. 학습·퀴즈 (V3 빌드, M-01·11)
학습카드(모국어, ko 병기 토글) → 퀴즈 제출 → 점수·라벨 → 미달 재시험 루프. 퀴즈 = 시드 우선 + generate_quiz(doc_ids)→draft→관리자 승인. 이해도 정의는 §3 뷰가 유일 소스 — 대시보드 평균 = 근로자별 최신 점수 평균, 재시도는 완주율 신호.

### 4-4. 위험 보고 (V3 빌드, M-08)
음성/텍스트 → 202 즉시 접수 → jobs 워커: STT→로컬 LLM 요약+severity(high|medium|low) → 상태머신 **submitted→acknowledged→resolved** (전이마다 acked_by/at·resolution_note = 책임 추적, 어필 ②). STT 3회 실패 시에도 오디오 보존+"직접 청취" 알림 — 안전 정보 무유실 설계. 대시보드 "미확인" = submitted 카운트.
- 미디어 플로우(M-25): 수신 = edge 암호화 → S3 단기 버퍼(TTL) → core pull → 처리 후 S3 삭제 (edge write-only / core read+delete IAM 분리). 텍스트 요청은 M-28 릴레이 큐 경로.

### 4-5. STT (M-18)
전용 컨테이너(core_net, 외부 STT 원천 배제 — 음성=민감). 동기(음성 질문): timeout 15s → 폴백 안내 응답(에러 금지). 비동기(위험보고): 위 워커. 따라말하기는 STT 미적용.

### 4-6. 관리자 화면 (V3 빌드)
공통 UX 패턴 = **요약 우선 노출 + 세부사항 버튼 → 원문**(신생 질문·위험보고·상담 위험신호 동일). 상담 원문 열람 시 access_logs 기록(M-07) — "업무 효율×프라이버시 양립", 어필 ①. KPI: 등록 수·평균 이해도·완주율·미확인 위험보고·주간 추이·근로자별/모듈별.

### 4-7. 상담챗 = 정착지원 모듈 실체 (V5 빌드, M-07)
기존 질의응답 챗 재사용 + 시스템 프롬프트에 학습 상태(미완료·마감·최근 점수·라벨) 주입 → 학습 보조 겸 모국어 상담. 로컬 티어 고정, conversations 저장, 위험신호만 요약 상향.

### 4-8. 안전 모듈 (V5 빌드, M-14)
학습모듈과의 차이 = 법정 교육 매핑: safety_courses(4과정: onboarding|regular|job_change|special) + 이수 기록. 최종 산출 = **교육일지 자동 생성**(일시·구분·내용·강사+자격근거·참석자·이해도 첨부, HTML 인쇄→PDF는 여유 시) — "근로감독관 1순위 서류를 버튼 하나로", 어필 C2. 금지 주장: "법정 시간 이수 대체"(강사 요건 있는 실시가 전제, 우리는 전달·검증·증빙 보조).

### 4-9. 인증 (V3 빌드, M-15)
근로자: 일회성 초대 토큰(만료·1회 소진) → PIN 설정(해시만 저장) → JWT+리프레시 쿠키 자동 로그인. 관리자: email+pw+role(owner|manager). "비밀키 미보관" 문구 정합.

### 4-10. 암호화 (V5 빌드, M-19)
seal/open(AES-GCM, TENANT_CRYPTO_KEY). 주장 수위: "HTTPS+저장 시 암호화(유출 시 평문 0)"까지 — 브라우저 E2E는 로드맵. 시연: edge 저장소 암호문 vs 앱 평문 대비. edge-db 포함 여부 = M-23(V5 판정).

### 4-11. 모듈 구조 (M-13)
modules/{learning,safety,speaking,settlement} 물리 디렉토리 + tenant_settings.modules 플래그 장착 — "모듈형 플랫폼" 주장의 코드 증거.

## 5. 검증·측정 계획 (수치가 곧 발표 재료)
#1 오역률(30문장, 파파고/구글/무보정 vs 용어주입) · #2 근거 인용률(qa_logs, 목표 무근거 0) · #3 게이트 검출률·오탐·τ(ROC) · #4 티어별 레이턴시 p50/p95 · #5 폴백 성공률(외부 차단 킬러 데모) · #6 STT 요약 정확도(10건 육안) · #7 리허설 완주율. 실행처: experiments/(오프라인) + qa_logs(운영 집계). 일정 = 08 지시서 V6.

## 6. 게이트별 빌드 요약 (상세 담당 = 08)
V2 = §4-1 (재료: 시드) → V3 = §4-3·4·6·9 → V4 = §4-2 + 통합 → V5 = §4-7·8·10 + 동결 → V6 = §5 측정 → V7 = 리허설·blue-green.

## 7. 잠긴 결정 대장 (원문 = skeleton-v3 §8)
M-01 이해도 / M-02 bge-m3 / M-03 qwen3 / M-04 스키마 테넌시 / M-05 무근거 편입 / M-06 알림함 / M-07 상담 프라이버시 / M-08 위험보고 상태머신 / M-09 lineage JSONB / M-10(+a τ) 게이트 C+A / M-11 퀴즈 / M-12 되말하기 / M-13 모듈 / M-14 안전=법정 매핑 / M-15 인증 / M-16 Dagster / M-17(+a gpt-4o-mini·8s) / M-18 STT / M-19 암호화 수위 / M-20 본선 9/2–3 확정·9/1 기본 휴무(점선 버퍼) / M-21 관리페이지·오버라이드 이월 / M-22 단방향 불변조건 / M-23 edge-db 미정 / M-24 문서 위계(PRELIM 상위 계약·R6) / M-25 미디어 플로우(edge 암호화→S3 단기 버퍼 TTL→core pull→처리 후 S3 삭제, S3=백업+미디어 버퍼 한정) / M-28 실시간 요청 릴레이(edge 큐→core 폴링→회신, M-22 준수) / M-26 시연=전체 플로우·"모듈 1종"=안전교육(상한 아님) / M-27 정량 목표 ⑤ 설문 미확보(보류·조작 금지)
발표 금지 문구: 법정시간 대체 · E2E 암호화 · Airflow 회피(선제 한 줄) · 미측정 수치 단정
