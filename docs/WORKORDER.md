# 작업지시서 — 4트랙 (V1~V7) · 8/25 발행

> 공통: 병갑 Git 규칙 v1.0 준수(Draft PR 즉시 오픈·하루 1+ push·CI green 수시 머지) · 로그 접두 `[코드|V게이트-구간|MMDD HH:MM]` · 막힘 2h 공유/4h 에스컬레이션 · 챗 제목 `코드 | V_-_ | 내용` · **일정: V6=8/30, V7=8/31, 9/1(화) 기본 휴무(필요 최소분만 합의 이월), 본선 9/2(수)–3(목)**

## 0단계 (전원, V1 · 26 수 오전 마감)
1. `git checkout main && git pull` → `cp .env.example .env`(값 채움) → `docker compose up -d`
2. core /health 200(db ok) · edge /health 200 · mock /ask 확인 — **Windows에서 한글 body는 `curl --data-binary @file`(UTF-8 파일) 사용, 직접 -d 금지(cp949 400 함정)**
3. 보고: `[코드|V1|MMDD HH:MM] 통과, docker <버전>` — WSL 미설치자는 재부팅 1회 예상, 로컬 웹서버 사용자는 caddy 80/443 충돌 주의

---

## MS 명선 (pipeline/ · experiments/ · data/ · db/migrations/) — 권장: Fable 5 높음(설계·판정) / Sonnet(감수·대조)
| 구간 | 작업 | 산출·DoD |
|---|---|---|
| V2-1 (26오전) | 시드 초안 감수·수정(어젯밤 CC 산출) + KOSHA 발췌 수집 | data/seed 확정, **오전 마감(새봄 선행조건)** |
| V2-2 (26오후) | 인제스천 실행: 분류→마스킹→청킹(500–800/오버랩100)→bge-m3 임베딩→적재. 새봄과 검색 품질 페어 | documents·chunks 적재 건수 보고, glossary 50 적재 |
| V3-1 (27) | glossary_candidates 에셋 + 퀴즈 시드 적재 + generate_quiz 드래프트 1회 실행→승인큐 진입 확인 | Dagster UI에서 자산 그래프 확인 |
| V4-1 (28) | 데모 대본(질문 5+실패 대체) + **V4 검증 주재**(코어 6스텝 체크리스트) | V4 판정 기록(GATE 접두) |
| V5-1 (29) | manager_report 에셋(일/월) + 안전 코스 시드 연결 | 동결 판정 참여 |
| V6-1 (30) | 실험 #1(오역률)·#2(인용률)·#3(게이트 ROC→**τ 확정, M-10a 닫기**) | 수치 3종 + 곡선 1장 |
| V7 (31) | 발표자료 완성(02→슬라이드) + 리허설 2 + V7 판정 | v1.0 태깅 |

## SB 새봄 (backend/) — 권장: Fable 5 높음(에이전트 설계) / CC 기본
| 구간 | 작업 | 산출·DoD |
|---|---|---|
| V2-1 (26) | llm_adapter 실구현: ollama qwen3:8b + openai gpt-4o-mini(timeout 8s, external→local 폴백, tier_used 기록) | FakeLLM 교체 |
| V2-2 (26) | RAG /ask: retrieve(top-k=4, meta_filter)→근거 강제 프롬프트→sources·trace·latency 기록, grounded=false→unanswered_queue insert | V2 E2E 통과 |
| V3-1 (27) | 위험보고: 202+jobs 워커(SKIP LOCKED, 요약+severity 로컬 티어, 3회 실패 시 보존+알림). 수신 구조 = edge 단기 버퍼 → core outbound pull(M-25), TTL 정리 크론 포함 | 알파에서 시연 |
| V3-2 (27) | 인증(초대 토큰→PIN 해시→JWT/리프레시) + 하트비트 스케줄러(core→edge, M-22) | edge /health degraded 해소 |
| V4-1 (28) | 게이트 C+A: verify_backtranslation(bge-m3 코사인, τ 가값 0.80)·is_high_risk(OR 규칙)·안전만 차단+전체 배지 | 오역 차단 데모 |
| V5-1 (29) | 상담챗(학습상태 주입, 로컬 고정) + crypto seal/open + 퀴즈 생성 파이프 연결 | 동결 전 머지 |
| V6~V7 (30–31) | 측정 지원(#2·#4·#5) + 안정화 + 리허설 | — |

## JH 정현 (frontend/) — 권장: Sonnet(마크업) / Fable 5(플로우 설계)
| 구간 | 작업 | 산출·DoD |
|---|---|---|
| V2-1 (26) | 근로자 질문 화면 실연동(vi, 근거 출처 뱃지, trace_id 표시), QR/초대 진입·언어 선택 | V2 E2E의 화면 |
| V3-1 (27) | 학습카드+퀴즈 제출(점수·라벨 3색) + 알림함 | 알파 근로자 측 |
| V3-2 (27) | 관리자: 대시보드 KPI 4종+추이·근로자별/모듈별, 승인큐(approve/reject), 위험보고(ack/resolve, 요약 우선+세부 버튼) | 알파 관리자 측 |
| V4-1 (28) | 통합 폴리싱: 모바일 뷰포트·로딩/에러·게이트 차단 표시("관리자 확인 필요") | V4 무중단 기여 |
| V5-1 (29) | 안전 모듈 화면+일지 출력(HTML 인쇄) + 상담챗 UI + in 리소스 | 동결 전 머지 |
| V6~V7 (30–31) | 시연 UI 다듬기 + 리허설 | — |

## BG 병갑 (infra/ · workflows · compose) — 권장: Fable 5 높음(배포 설계) / CC 기본
| 구간 | 작업 | 산출·DoD |
|---|---|---|
| V2-1 (26, 최우선) | EC2 프로비저닝(t3.xlarge·50GB gp3·80/443·SSH 화이트리스트) + qwen3:8b/4b pull + df -h 캡처 | **V4 배포 URL 선행조건** |
| V2-2 (26) | CD(main→GHCR→EC2 pull&up) + Caddy HTTPS + prod `ports: !reset []` 수정 + .env.example에 EXTERNAL_LLM_PROVIDER/MODEL 키 추가 | 배포 URL 공유 |
| V3-1 (27) | stt 컨테이너 기동 확인(small int8, core_net) + 헬스체크 크론·웹훅 + **V3 직후 첫 pg_dump→일일 크론(S3)** | 백업 게이트 가동 |
| V4-1 (28) | 배포 URL 전 경로 검증·부하 확인·restart:always | V4 판정 참여 |
| V5-1 (29) | 동결 지원 + edge-db 포함 판정(M-23) | — |
| V6~V7 (30–31) | blue-green 승격+전환 시연, 배포 리허설, GPU 최종 판단 | V7 전환 시연 |
