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
