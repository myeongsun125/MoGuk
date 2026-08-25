# MoGuk PROTOCOL v1 — 운영 체계 (Final_ 프로토콜 이식판)

> 레포 커밋 위치: docs/PROTOCOL.md · M-xx 결정에 종속되는 운영 규칙 · 수정은 M-xx 근거로만

## 문서 위계 (M-24)
- 목표(상위 계약): docs/PRELIM_PROPOSAL.md — 모든 문서·구현은 이를 이행한다. 원문 수정 금지.
- 결정 대장: skeleton-v3 §8 M-xx — 목표·설계·계약의 모든 변경은 여기로만 들어온다(R5).
  예선 문서와 다른 모든 결정은 변경 사유 필수(R6) — 심사·발표 방어의 근거가 된다.
- 개념별 원문 소유(R4): DDL→db/migrations/001 · API·시그니처·M-xx 대장→skeleton-v3
  · 설계 서사·근거→BLUEPRINT · 게이트·일정·컷라인→WORKFLOW · 운영 사이클→PROTOCOL
  · 거버넌스→GOVERNANCE · 작업 배분→WORKORDER · 게이트 검증→GATE_CHECK · 발표 논거→APPEAL_POINTS
- 충돌 시: 해당 개념의 소유 문서가 우선. 목표와 계약이 어긋나면 산문을 고치지 말고 M-xx로 계약을 고친다.
- 읽기 진입점: 최초 1회 PRELIM_PROPOSAL 필독 → 이후 세션은 BLUEPRINT → WORKFLOW → skeleton-v3 → PROTOCOL → 최신 HANDOFF

## 0. 역할
- **Master = claude.ai (명선 세션)** — 설계·게이트 판정·핸드오프 저작·M-xx 채번. 코드 검증 시 핵심부 인용 요구.
- **Executor = 로컬 Claude Code** — 구현·자체 테스트·보고. 게이트 판정 권한 없음(보고 후 Master 승인 대기).
- **트랙 오너 4인** — 명선(pipeline/experiments/data), 새봄(backend), 정현(frontend), 병갑(infra/compose/CI). 디렉토리 소유권 = Git 규칙 §7.

## 1. 일일 사이클 (Final_ 직렬 사이클의 4인 병렬 변형)
1. Master가 트랙별 작업지시서/일일 목표 확인 (작업지시서 = 07 문서)
2. 각 트랙 실행 — 작업 시작 시 Draft PR 오픈, granular 커밋, 하루 최소 1회 push, CI green 단위로 수시 머지
3. 밤 게이트(V표) — 트랙별 HANDOFF 4장 제출 (§4 템플릿)
4. Master 판정: **GATE PASS / FIX** (FIX면 교정 지시 → 익일 오전 재판정)
5. 컨텍스트 무거우면 새 챗 — §6 부트스트랩으로 재개

## 2. 검증 게이트 (요일 교정 확정판)
| 게이트 | 일시 | 통과 기준 요약 |
|---|---|---|
| V1 | 8/26(수) 오전 | 전원 0단계: compose up + /health + docker --version 보고 |
| V2 | 8/26(수) 밤 | 실데이터 /ask E2E (업로드→인제스천→vi 질문→근거 답변, trace) |
| V3 | 8/27(목) 밤 | 알파 풀사이클 (학습→퀴즈→질문→위험보고→대시보드) |
| **V4** | **8/28(금) 밤** | **1차 데모: 코어 6스텝 무중단 1회 + 크리티컬 0 + 배포 URL** |
| V5 | 8/29(토) 18:00 | 기능 동결. 잔여(일지·상담챗·in·crypto) 포함 여부 확정 |
| V6 | 8/30(일) 밤 | 측정 #1–6 수치 확보 + 리허설 1 완주 |
| V7 | 8/31(월) 밤 | 리허설 2 + blue-green 시연 + 발표자료 완성 + v1.0 태깅 |
| 휴 | 9/1(화) | 기본 휴무(배정 0 원칙) — V7 미달 최소분만 전원 합의로 점선 버퍼 사용 |
| 본선 | 9/2(수)–3(목) 확정 | 1일차 멘토링·제출 / 2일차 발표·시연 |
실패 시 처리·컷라인 = WORKFLOW.md 준거. **V3 실패 시점에 즉시 컷라인 적용(범위 방어 = 일정 방어).**

## 3. 머지·롤백 원칙
- CI green 필수 — red 상태 머지 절대 금지. red면 직전 커밋으로 되감고 재시도
- granular 커밋(되감기 지점 촘촘히), main 머지 = 배포(CD 가동 후)
- 계약 변경(API·DB·/health·compose·CI·skeleton-v3)은 Git 규칙 §6 협의 필수
- 마이그레이션 멱등(IF NOT EXISTS), DROP 금지

## 4. HANDOFF 템플릿 (트랙별 · 매 게이트 제출)
```
[HANDOFF] 게이트: V_ / 트랙: (명선|새봄|정현|병갑)
- 완료 커밋/PR: <해시·번호>
- 게이트 증거: <통과 항목 + 테스트·실행 출력 요약>
- 현재 상태: <지금 동작하는 것>
- 변경 파일: <목록>
- 타 트랙 영향: <계약·env·마이그레이션 등 pull 후 조치 필요 사항. 없으면 "없음">
- 이탈/오픈: <예외·미결 — M-xx 후보는 명시>
- 내일 첫 작업: <목표>
```

## 5. 기록 체계 (단일 출처)
- **M-xx 대장 = docs/skeleton-v3.md §8** (유일한 결정 원장, 채번은 Master)
- **docs/DECISIONS.md** = 근거 색인 (결정 본문 중복 금지, 링크·커밋 참조만)
- **docs/WORKLOG/** = 사건 기록 (보안 차단 사례, 선머지 사유, 벤더 선정 근거 등 발표 증거)
- DDL 원문 = db/migrations/001 (문서 §2와 충돌 시 마이그레이션 우선)

## 6. 새 챗 부트스트랩 (복붙)
```
나는 MoGuk(이음) 본선 스프린트의 Master 세션을 재개한다. 팀 AXIs 4인
(명선=파이프라인·총괄/새봄=백엔드/정현=프론트/병갑=인프라),
레포 github.com/myeongsun125/MoGuk, 본선 9/2(수)–3(목) 확정, 9/1 기본 휴무(점선 버퍼).

읽기 순서 (M-24 진입점 · 프로젝트 지식·outputs에서 검색/참조):
0. docs/PRELIM_PROPOSAL.md (상위 계약 — 최초 1회 필독, 이후 세션은 참조만)
1. docs/BLUEPRINT.md (개발 청사진 — 무엇을 왜) 2. docs/WORKFLOW.md (게이트 V1–V7·컷라인)
3. docs/skeleton-v3.md (계약 SSOT·M-xx 대장) 4. docs/PROTOCOL.md (이 체계)
5. 최신 HANDOFF (직전 게이트 결과)

중요 규칙: 개정 R1–R6(R6 = 예선 문서와 다른 결정은 M-xx에 변경 사유 필수) / 착수한 계약 동결, 변경은 M-xx / 민감=로컬 LLM 티어,
외부=gpt-4o-mini 번역 전용(8s 폴백) / 임베딩 bge-m3 고정 / 시크릿 커밋 금지 /
발표 금지 문구(법정시간 대체·E2E 암호화 과장) 유지

현재 상태: [게이트 V_ 까지 판정 완료 / 직전 HANDOFF 요약 붙여넣기]
작업 시작: [오늘 할 것]
```
