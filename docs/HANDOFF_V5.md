# V5 HANDOFF 기록

> 레포 커밋 위치: docs/HANDOFF_V5.md · 트랙별 HANDOFF(PROTOCOL.md §4 절차)의 실물 기록.
> 확인(2026-08-30): SB·JH·BG 3장은 파일로 미등재 — 채팅(claude.ai 세션) 보고로만 존재. 본 파일은 MS 1장부터 신규 등재하며, 3장 실물 확보 시 동일 파일에 이어 붙인다.

---
[MS|V5 HANDOFF|0830]
■ 완료 증빙
- 데이터 체인: KOSHA·NCS·EPS raw 19건 수집·라이선스 판정(유지+
  트리거 기록) → #6(raw·manifest·시드, head 1d41d12 — 06 폐기·
  negation 사양 포함) → #33(07 재생성) → EC2 인제스천 완료
  (0830 01:52, ingest_seed.py — #36으로 scripts/ 정본화)
- 인프라 운영: SSH 체인 확립(키·SG·deploy key) / psql 1차 적용
  (tenant_axis_demo 22→23테이블) / H1·H2 판별 SELECT·로그 실행
- 총괄 판정·채번: M-04b·M-04c·M-05a·M-08a·M-08b·M-08c·M-15a·
  M-15b·M-28b·M-28c + 경로(가)·마스킹 범위·라이선스·TTL core·
  admin 노출 완화(Caddy IP) 등
- 머지 게이트: #6·#20~#29·#31~#36 처리
- 어필 문서: APPEAL_POINTS ②③ 보강(#30 — 서명 취합 중)
■ 측정 수치
- 인제스천: documents 2·chunks 42·glossary 50 / bge-m3 1024d
  단일(42/42) / 역대조 42/42 / retrieve 스모크 0.768 / 12s
- 판별: 적재 전 0/0/0 → H1 해소, H2 로그 확정("type vector does
  not exist") → M-04c로 해소
■ 미결
- 코퍼스 확장(판정 A): text/ 13파일 적재 — 집행 중, 8/31 대본
  입력 조건 → 0831 갱신: 완료(아래)
- #30 머지 잔여 / phrases·quiz_sets·safety_courses 0건(V3-1·
  V5-1 몫) / N10 계열 τ 실측 시 최종 검증
■ 다음 게이트 착수점
- V6: JH V3-2·V3-1 화면 / V7: τ·측정#4·#5 실측 — 입력 준비 완료

---
[MS|V5 HANDOFF 갱신|0831 — 로컬 노트 누적분 정리, main 9f3b032 기준]
■ 등재 완료(미결 해제)
- M-32·M-33·M-34 §8 등재(#54) + M-32b(초대 발급 edge 릴레이 #53)
  / §3:222 verify.score null 조건 정밀화(#54 b3f12a6, #55 실물)
  / #53 추인 문구 정밀화 — 위 0830 미결 중 "#30 머지 잔여"는
  #30 머지(a252d60)로 해제
- 코퍼스 확장(판정 A) 완료: EC2 `--sources text` 0830 17:39 —
  documents 15(시드 2+text 13)·chunks 572(seed 42 보존+text 530,
  1024d 단일)·glossary 50 무접촉 / category safety 157·
  instruction 373 / draft:false 530 / #38·#41(glossary 가드)
- admin_events EC2 재적용(#46 e92cceb, 001 L158–166 원문: 컬럼 9·
  인덱스 1본 admin_events_target_idx) 0830 19:12 — 23테이블,
  public 없음, 멱등 재실행 무해
■ 기록
- CI: main #138~#141 실패 = test_admin_approval.py:378 동적 가드
  필터 불일치(오탐), #48(A안)로 종결·초록 복귀(run #143). 001
  변경 감지 기능 유지 (#49 폐기분 이관)
- M-29a 유지 재확인: CASE-1 = 4유형·role='case', 검색 원천 배제
  (retrieve.py). 3·4유형 원칙(2유형 발췌·재구성 / 4유형 무변형
  발췌 / 미표시 2건 출처 표시) 변동 없음
- 4유형 role='case' 청크 수(0831 16:28 KST, 조건 = M-29a 문면
  role='case' 그대로): documents 12 "[중대재해] 유압프레스 금형
  수정작업 중 끼임" 3청크. 참고: license '4유형' 적재분 = doc 7
  KOSHA-PRESS 6·doc 9 KOSHA-COMMON-1 8·doc 12 CASE-1 3
- 프리즈 예외 2·3호 / 머지 창 종료 = #55, 리허설 후 PR 재개
- 0831 머지 체인 #51→#50→#53→#52→#56→#54→#55, main 9f3b032,
  컷오프 16:17 KST. 순서 #51→#50 역전 사유 = .env.example 충돌
  / #50 게이트 8·9 수동 판정(스크립트 보정 이월)
- P4: 가 강등, 나 JH 담당 / 테스트 행(리허설 접수·초대·questions)
  유지 방침 — 삭제·truncate 금지
- SSH 22 개방 예외(9/4 원복) / τ·timeout env 가값 → 실측 조정
  (M-34 워밍업 ①② SELECT 결과로 총괄 판정)
■ 이월 목록(갱신)
- EDGE_CASES 통합 · GATE_SRC 경고 로그 · gate_reason error 검토 ·
  types.ts 갱신 · glossary 타입 · original_text 에코 · M-32a ·
  P4 나 · 오프라인 τ 측정 · CADDY_DOMAIN 잔존 · KOSHA-LATHE-2/4
  재수집(raw 내용 불일치 HOLD, 9/1 판정 — 시연 질의 ② 참조 여부)
- 기존 이월: 인증 강제 · unanswered answer · CD · 백업 크론 ·
  법령 검색 개선 · glossary 반환 타입
- MS 잔여: gate_eval·mistranslation_eval 스텁(τ CSV 분석 → 덱
  v0.2) / Dagster 5에셋 스텁 / 본선용 테넌트 초기화 안 A/B(9/1
  상신, 실행 금지)
■ 리허설 결과(결함 판정·측정치) — 리허설 후 추가
## 0901 새벽 큐 경과·이월 추가
- 머지: #59(d0c15e7, M-35·M-36 채번·REHEARSAL·APPEAL) → #60(4680c3b, M-35 activate lang — 영향 줄 누락 1회 보류 후 본문 수정·동일 head 머지) → #61(Q4 — 진행 중, head 8098eff: 판정 B 언어 토글 노출 + ★판정 A localStorage 영속 moguk_lang, 구 f362a16·3700aa4 폐기)
- Q7 브랜치(aa79afb): D-8 clock_timestamp·D-4 confirm 401(M-37, 릴레이 경로 포함)·총괄 docs 커밋·채번 정정. test:760 실물 위치 = test_confirm_endpoint_requires_authentication(원장 무변경 판정 — 결정 시점 기록 유지, PR 본문 기재)
- 레지스터 브랜치 c3ac467 동결(원문 보존 append 1~5, M-35 이월 1구는 판정 B로 제거). PR은 Q12 후 슬롯
- D-4 원인 종결: #3 요청 Bearer 부재(브라우저 컨텍스트 분리 추정, 인앱 후보) + optional 허용 중첩 — (b) 단독 불성립(#2 worker:5). Q4+Q7+QA 8항으로 봉합
- D-8 정정: psql latency(#1 1.31s 등) = 잡 픽업 대기, 요약 LLM은 +1.06s 별도 — 덱 수치 정정 필요(clock_timestamp 반영 후 재측정)
- 이월 추가(#61 리뷰, SB 발견 비차단 6): ① WorkerLayout:21 aria-label 영문 ② LANG_CODES 중복 정의(WorkerLayout:7↔Invite:9) ③ 401 무구분 안내(Invite:34 — 보안 의도 A 판정의 흔적) ④ types.ts:32-34 주석 stale ⑤ confirm 401 안내 부재(reports.ts:39-41 — Q7 머지 후 후속) ⑥ localStorage try/catch 부재(AuthContext 동형, 신규 아님)
- 이월 추가(리허설·QA 준비 중 발견): 근로자 화면 trace_id 노출 여부 판정 / 근거 칩 문서 단위 묶음·말줄임 / 상세 요약→원문 순서 / 영어 등 언어 확장은 본선 후 검토(개인 메모 아님·공식 이월 아님 — 총괄 보류)
- #63 언어 회부 최종 = A(B' 분리 구현 사후 수용 — AdminLangContext·기본 ko·격리 확인, ko 단일 지시 회수). 경위 A→B→B'→ko단일→A, 이월: 관리자 i18n화·번역·토글 실효화 일괄(본선 후)
## 0901 총괄-5 추가분
- [τ 판정 확정 0901] 온라인 GATE_TAU 0.45 유지, 후보 0.66/0.70 기각(0.70 정상 오탐 8/30). 코사인 단독은 국소 오염(부정·수치·용어) 분리 불가 — 실측 서사로 덱 반영(r2 확정본, 수치 SSOT scores_20260901_0432_judged.csv). 로드맵 C(결정적 표적 검사)→B(LLM 판정기) 순 명기. 0.56 워밍업 건 = 정상 답변·되번역 용어 오역(오염 아님).
- [이월] 릴레이 경유 401 응답 WWW-Authenticate 헤더 부재 — 프론트 무영향 (SB 0901 05:27)
- [기록] compose 92행 GATE_TAU 기본값 0.80 = M-34 ③ 가값, 운영값은 .env 0.45(env만 조정 원칙) — 변경 시 M-34 ③ 개정 필요, 현재 결정 없음
- [해소] EC2 .env OLLAMA_KEEP_ALIVE 중복 정의 — Q2-②로 10m 행 제거 완료(BG 0901)
- [확인 완료] EC2 ADMIN_ALLOW_IPS 5건 전부 팀원 IP(BG 회신 0901) — 유지
- [기록] 예비 스윕 NUMBER_CHANGED 라벨 오작동 — 재스윕 코드는 type 필드 무변형 복사(gate_eval.py:94)라 구조적 재현 불가, 예비 스윕 코드는 레포 이력 부재로 실물 대조 불가
- [기록] Q12 오염 60 구성비(30/20/10)와 예비(10/10/10) 상이 — 전체 검출률 단순 비교 금지, 유형별만 (README:20)
- [해소] #66 confirm 401 안내(#61 이월 ⑤) / #67 GATE_SRC 경고 / #68 EDGE_CASES 통합 / #69 gate_eval 확장 — 각 PR로 해소
- [기록] 레지스터 rebase(0901) 검증 전 push 1건 — 내용 불변 실증, fce4d60 커밋 메시지에 절차 기록, 선례 인용 불가 (#70 머지 899d9e7)
- [기록] #70 SB Approve 06:13은 노트북 CC 대행분 — SB 자진 무효, 06:31 본인 재서명 정본. 노트북 CC 규칙 재고지 완료
- [기록] 로컬 .gitignore 이상 원인 = 워킹트리 CRLF(autocrlf=true), 22행 CR 단독 줄이 check-ignore 가짜 매치 — 실효 무시 안 됨, 인덱스 LF 정상. 본선 후 로컬 재체크아웃
- [이월] M-10a :334 "M-34 ③" 인용 정밀화(가값 출처 / 전건 차단 관측 분리) — 본선 후 docs PR
- [이월] 타우 측정 스크립트 3건(judge_backtrans·measure_gate_scores·postprocess_gate_scores) 레포 커밋 — 본선 후. 백업 3_본선관련\본선발표관련\gate_eval_src_0901\
- [기록] 재스윕 도구 = SB gate_eval.py + MS measure v3 양측 측정 확정 — 측정 경로 동일성 실물 확인 항목을 재스윕 지시서에 포함
- [이월] JH F 디자인 완성도/토큰 — 견적 목업 1~1.5일 / 토큰+핵심 3~4화면 반나절~1일, 순서 토큰→공통 컴포넌트→화면별, 390px admin-header 오버플로 흡수 — 본선 후 첫 슬롯
- [이월] PWA/standalone(manifest·아이콘·meta) — 본선 후
- [기록] 관리자 403 = Caddy ADMIN_ALLOW_IPS 거부(JH 리허설 셀룰러) — 본선장 IP·아이패드 망 등록은 BG 런북 범위, D 문구 매핑 생략
- [예정] 런북 docs/RUNBOOK.md — 재배포·테넌트 전환 실행 후 총괄 docs PR(BG 골격·서명)
- [확정 0901 17:4x] A′ 채택 — M-05a 답변·재적재 완성 본선 전 구현(SB 3.5~5h·JH 3~3.5h). 퀴즈 A는 미구현 확정(정직 재구성 B) — 근거: A는 A′ 1.4~1.6배·§3 개정 2~3건·원어민 검수 전 vi/in 문항 노출. restyle 이월.
- [판정 0901] A′ 세부 3건: §3:240 응답 {id,status:'answered',answered_at,ingest_job_id} / admin_answer chunks.meta category 'general'·draft false(safety 승격 이월, retrieve general 배제 여부 SB 실물 확인) / admin_events 'unanswered_answered'·target_type 'unanswered'·actor null.
- [실물 0901] M-05a 현황 = 무근거→unanswered_queue 적재·GET 목록 구현 / POST answer 스텁·ingest_answer 잡 부재·admin_answer 문서 0(EC2 open 16건). 어필 ④ 문안 "큐 적재→답변→재적재 루프 구현"은 과장이었음 — A′ 스모크 후 정정.
- [실물 0901] 용어집 주입 번역 미구현(translate.py 스텁, 호출 0, 오역률 측정 산출물 전무). 용어집 데이터·승인 루프는 실물. 어필 ③ "승인 용어집으로 정확도 상승" 하향, Q&A "용어집 1차 방어선" 철회. 기획서 정량 목표 "현장 용어 번역 정확도" 미측정 — 정직 표기.
- [실물 0901] 학습·퀴즈·이해도·교육일지 전부 미착수(V5-1/M-14). 기획서 시연 범위 "이해 검증" 미달 — 이행·이월 표로 선제 공개, 설계 자산은 로드맵 근거.
- [이월] restyle(디자인 토큰+핵심 3화면) — JH 준비 완료 상태, 본선 후 첫 슬롯.

## 0901 총괄-5 추가분 2
- [실물 0901] M-05a 원 상태 = 큐 적재·목록만 구현, 답변 API 스텁·ingest_answer 부재·admin_answer 0 → A′로 완성. 어필 ④ 문안은 2차 재배포 스모크 후 "구현"으로 갱신.
- [확정 0901] 덱 v0.2 정정: 음성 삭제 / S21 ⑤ "설계 확정" / C-lite trace 실장 반영 / 상담 감사 삭제 / 저장 암호화 문구는 2판본(스모크 통과 시 구현, 미달 시 로드맵) / 폴백 장면 금지 / blue-green·백업 문구 확인 전 사용 금지 / 수정은 삭제 아닌 정정 append.
- [확정 0901] 어필 ① 재구성: "상담 프라이버시" → "위험 보고 원문 프라이버시"(최소 수집 이름·사번·언어, 이름 비노출, 목록 요약만, 상세 열람 original_viewed 감사, LLM 로컬 고정). 실물: workers.name SELECT 0, _LIST/_PUBLIC_KEYS original_text 제외, record_event EV_ORIGINAL_VIEWED.
- [확정 0901] 보안 분담: 앱 층 M-19 = SB 구현(#76, original_text 1컬럼·enc1 마커·이중 읽기·평문 폴백 쓰기 금지) / PII 마스킹 로드맵 / EBS 암호화 본선 후(리전 기본 암호화만 활성, 덱 미기재) / S3 SSE-S3 실증 병기 허용(캡처 s12-s3-sse.png, 미디어 버퍼 한정) / 백업 크론 승인(2차 재배포 후, IAM core backups/ PutObject 최소 권한, 복원 검증 1회) / 관리자 로그인 M-15b 이월 / 관리자 초대 화면(P4 나) 미구현 이월(초대 API는 M-32 구현).
- [실물 0901] 보안 인벤토리: 원문 컬럼 읽기 코드 5파일 43곳·SQL 8지점 / 관리자 라우터 인증 의존성 0(IP 화이트리스트만) / 백업 크론 0·수동 pg_dump 8/30 1건 / CI = lint·pytest·Trivy(CRITICAL/HIGH), 시크릿 스캔·SAST 없음.
- [기록 0901] #76 검수: 구현 정확. 치명 1건 — EC2 TENANT_CRYPTO_KEY 43자(패딩 없음) → urlsafe_b64decode 실패 시 접수 전건 실패 → 패딩 보정 1커밋 지시(raw += "=" * (-len % 4)) + requirements 한글 주석 영문화. BG 키 32B 검증 요청.
- [기록 0901] 대시보드 인용률 92.5% 원인 = _SQL_CITATION 분모가 grounded만 봐서 threshold 차단(id 56·57·58, 0831 워밍업 τ0.80분)이 분모 잔류. §3:234 정의(gated 제외)는 맞음 → SB 별건 PR(분모·분자 gated 제외 + 테스트). 덱 100%는 정의 기준 정확.
- [실물 0901] D-8 재측정(재배포 후 보고 4~9, 이벤트 created_at, clock_timestamp): 접수→요약 중앙값 1.498s·최대 2.491s·최소 1.056s(n=6). jobs에 픽업 시각 컬럼 없음.
- [실물 0901] 재스윕 1822(정상 30·오염 60 = term_swap 30/negation 20/number 10, n=90): SSOT scores_20260901_1822_judged.csv sha256 9035f117…. 코사인 τ0.45 3.3/0/0 오탐 0 / τ0.70 16.7/55/30 오탐 16.7 / τ0.80 70/80/40 오탐 60. 판정기(≠SAME) 53.3/80/90, 정상 33.3. 결론 불변: τ0.45 유지·0.66/0.70 기각. 도구 교차(measure v3 vs gate_eval.py): 되번역 동일 4/90, |Δscore| 평균 0.039·최대 0.304 — 되번역 비결정성 실측.
- [실물 0901] 규칙 층 n=90: 0/85/100 오탐 10(S12·S26 부정어 소실, S21 숫자 소실 = 되번역 정보 소실, 규칙 결함 아님). 미검출 N01·N15·N16(양측 부정어 수 동일). 규칙∪TERM_CHANGED 43.3/90/100 오탐 30 / 규칙∪≠SAME 53.3/90/100 오탐 40. 예비 n=60 재계산: 0/90/100 오탐 6.7 → ∪TERM 70/90/100 오탐 33.3. 파일 rules_20260901_1822.csv sha 8d3fb83e….
- [확정 0901] S16 판정식 ① 규칙∪TERM_CHANGED — 근거: 층별 역할 분담(코사인은 국소 오염 못 가름+되번역 지터 / 규칙은 숫자·부정 결정적 / 판정기는 용어 축만, 패러프레이즈 오판 33~40%). 개선폭 예비 0→63.3→86.7, 오탐 0→6.7→33.3.
- [실물 0901] 용어집 왕복 검사 오프라인: 정상 오탐 80%(24/30) — 되번역이 용어집 용어(척·선반·바이트·프레스…)를 보존하지 않음 → 주입 번역 선행 없인 왕복 검사 불성립(로드맵 ② 순서 근거). 미주입 되번역 용어 보존율 20%(6/30) = "현장 용어 번역 정확도" 기준선 후보. 파일 rules_gloss_20260901.csv sha 9c9de347…. 주입 되번역 실험(측정 전용) 진행 중.
- [기록 0901] 안드로이드 QA: 카톡 인앱·아이폰 confirm 200 / 삼성 인터넷 confirm 401 — 원인 확정: localStorage 토큰 미보존 → authHeaders() Authorization 생략, 접수는 worker_id NULL로 통과(#7·#8), TTL 무관. 수정 오늘 저녁 JH 별건 PR(AuthContext 메모리 폴백+try/catch, 토큰 부재 시 재인증 안내). 접수 익명 허용 정책은 M-08c 판정 별건. 시연·영상 기기 = 아이폰·카톡 인앱·아이패드 Safari만.
- [기록 0901] 기기 QA: 아이폰 8항·인앱 8항·관리자 7항 PASS, UI 4항목 확인, 아이패드 미보유 스킵(노트북 768px 대체, 후순위). 카페 IP 221.150.44.3 등록(admin_ip_add.sh 실전 검증, 카페 이탈 시 제거). 본선장: 관리자 기기 BG 핫스팟 고정 IP 1회 등록·당일 재확인·종료 즉시 제거(통신사 NAT 공유 리스크).
- [기록 0901] 머지: #70 899d9e7(레지스터) · #71 4739544(Q2 keep_alive·caddy 로그) · #72 3916f7f(UI 4항목) · #73 49357e3(C-lite trace) · #75 14a04cf(admin_ip_add.sh) · #74 eec805f(A′). 1차 재배포 16:52 main 3916f7f(7분, 빌드 25초 캐시). 2차 재배포 대상: #73·#75·#74 + 인용률 + JH 무근거 큐 + JH 저장 폴백 + #76 M-19 — 테넌트 axis_final 전환과 재기동 1회로 합침.
- [기록 0901] 절차: #70 SB Approve 대행분 무효·재서명 / 레지스터 rebase 검증 전 push 1건 / 노트북 CC 규칙 재고지 / JH ready 오류(PR 번호·CI 빈칸) 재통지 요청.
- [이월] 관리자 초대 화면(P4 나) / 관리자 로그인(M-15b) / PII 마스킹 / 재로그인(PIN 기반, 복구=재초대) / EBS 암호화 9/4 이후 / 프로덕션 용어집 주입(A 실험 결과 후 판정) / test docstring 이스케이프 경고 / ingest_answer 실패 로그 문면 / requirements 한글 주석 cp949.

## 0901 저녁 — 머지·2차 재배포·스모크
- [머지] #76 5495686(M-19 저장 암호화, 패딩·트레일러 amend 2회) · #77 401e3c1(관리자 무근거 큐 화면) · #78 0a1276c(인용률 분모 gated 제외) · #79 7427b14(용어집 주입 하네스, BG env 서명). 0901 머지 21건. 열린 PR #58뿐.
- [확정 0901] 트레일러 규칙: Co-Authored-By 제거 필수(#76·#79 amend 선례), SB CC includeCoAuthoredBy=false 등재. 게이트 전용 조건 "커밋 본문 Co-Authored-By 0" 상시. GIT_RULES 명문화 이월.
- [확정 0901] 검수 기준: SQL·산식·인증·계약·타 트랙 파일 접촉 → 읽기 전용 검수 필수 / CSS·문서·1파일 스크립트·테스트만 → 게이트 조건 대체.
- [실물 0901] 용어집 주입 실험(측정 전용, 1913_gloss, n=90): 보존율 20→83%(25/30), 왕복 검사 오탐 80→16.7%, 판정기 정상 오판 33→17%, 코사인 정상 평균 0.788→0.860·τ0.70 오탐 16.7→3.3%, 저점 S26·S17·S09·S02 +0.26~0.34(원인 용어 불일치). 주입 계단 3.3/0/0,0 → 규칙 10/80/100,10 → +용어집 100/85/100,26.7 → +판정기 100/95/100,36.7. SSOT 1913_gloss_judged sha 39d7e581…. 프로덕션 반영 #79(되번역 on, 답변 off, status approved,draft).
- [확정 0901] CI 실적 정정: 예선 Trivy 2(PR #2 starlette HIGH 3·PR #3 Debian util-linux HIGH 36) + 본선 준비 pytest 3(#17·#59·#76) = 5건, 기획서 3건 중 1건 CI 설정 오류 재분류. APPEAL B4 "3+3" 이월.
- [실물 0901] 테넌트 axis_final 생성·적재: 문서 15(매뉴얼 2 + 원문 13: LAW 2·KOSHA 8·NCS 3)·청크 572·용어집 draft 50·1024차원. LATHE-2·4 실물 불일치(크레인 깔림·부정수급 문서) — 재수집 폐기(명선). apply_tenant.sh 모드 664. 수동 pg_dump moguk-0901-1027.sql(8,260,228B).
- [실물 0901] 2차 재배포 20:29 main 7427b14, TENANT_SLUG=axis_final, TENANT_CRYPTO_KEY 43자(32B 검증 OK, 패딩 보정 코드), GLOSSARY 3키 기본값, bge-m3 재워밍업 — embed() keep_alive 전달 여부 SB 확인 대기.
- [실물 0902 00:0x] 스모크 PASS: risk_reports #1 original_text enc1: 봉인·관리자 상세 평문·original_viewed 기록 / A′ 폐루프(unanswered #1 answered → ingest_answer done → documents 16 admin_answer·chunks 1 → 재질의 최상단 인용) / trace inj_n=1(máy tiện→선반·khuôn→금형)·num·neg 기록 / 인용률 3/3=1.0 / 감사 로그 전 이벤트 / 워커 3언어 토글 정상, 관리자 토글 무변화는 B′ 정상(시연 클릭 금지). CryptoKeyError·Traceback 0.
- [확정 0902] 저장 암호화 판본 A. 어필 ④ 구현. 덱 r3 = MoGuk_본선발표_v0.3_r3(23장, 발표 세션 산출, 이후 수정은 명선 전담). 영상은 9/2 리허설 겸 녹화(캡처 13장 확보).
- [확정 0902] 9/2 심야 추가 구현(이월 0): ① 삼성 저장 폴백 ② 근로자 등록 화면 ③ PII 마스킹 ④ QR 생성 ⑤ QR 발송 ⑥ 관리자 i18n 연결분 ⑦ 답변 주입 on ⑧⑨ 퀴즈 백·프론트(용어집 연동) ⑩ §3·시드 ⑪⑫ 로그인 실측·관리자 로그인 판정 ⑬ 백업 크론 ⑭ 게이트 ⑮ 3차 재배포 ⑯ QA(아이폰·카톡·삼성·아이패드·퀴즈). 목표 16, 시간 미달 시 9까지. 17~19(리허설·영상·덱 r4·런북/Q13 머지·본선장 IP) 9/2 낮.
- [기록] 관리자 초대 화면(P4 나) 미구현 → ②로 편입. QA-07·08 axis_final 발급 실기록. 화이트리스트 6개(.191 stale·MS·SB·JH·.182·BG 핫스팟 223.38.111.192), 카페 221.150.44.3 제거 완료, 본선장·핫스팟·.182·.191은 9/2 종료 시 제거, 자택 3개 9/4 판정. RUNBOOK_draft.md v2 수신(3_본선관련\본선발표관련\).
- [이월] SOM 30개소(첨부 11 대조 후 확정) / 브랜치 삭제 일괄 / EBS 9/4 / 교육일지·상담·음성.
