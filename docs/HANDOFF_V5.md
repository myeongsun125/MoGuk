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
  입력 조건
- #30 머지 잔여 / phrases·quiz_sets·safety_courses 0건(V3-1·
  V5-1 몫) / N10 계열 τ 실측 시 최종 검증
■ 다음 게이트 착수점
- V6: JH V3-2·V3-1 화면 / V7: τ·측정#4·#5 실측 — 입력 준비 완료
