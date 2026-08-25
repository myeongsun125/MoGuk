# 게이트 크로스체크 프롬프트 (범용 · 매 게이트 머지 전 전원 수행)

> 각자 자기 CC(또는 수동)에 붙여넣어 실행. 권장: CC 기본 effort. 소요 ~10분.

```
[게이트 V__ 크로스체크 — 트랙: (MS|SB|JH|BG)]

1. 동기화: git fetch --all && git checkout main && git pull
2. 게이트 대상 PR들의 Files changed에서 다음을 확인:
   a. 내 소유 경로를 타인이 수정했는가 → 있으면 diff 검토
   b. 계약 파일 변경 여부: docs/skeleton-v3.md, db/migrations/*, .env.example,
      docker-compose*.yml, backend/app/routers/* (API 스키마)
3. 계약 3종 대조 (변경이 있을 때만):
   - API: 내 코드가 부르는 엔드포인트·필드가 skeleton-v3 §3과 일치하는가
   - DDL: 내 코드가 읽는 테이블·컬럼이 migrations 원문과 일치하는가
   - env: 새 키가 생겼으면 내 .env에 반영했는가
4. changelog에서 "영향: <내 트랙 코드>" 검색 → 전 항목에 대해 조치 수행
5. pull 후 재기동 필요 판정: Dockerfile/requirements/compose 변경 시
   docker compose up -d --build, 새 마이그레이션 시 apply_tenant.sh
6. 보고 (채널, 한 줄):
   [코드|V__|MMDD HH:MM] 크로스체크 이상무
   또는 [코드|V__|MMDD HH:MM] 충돌: <내용> — 머지 보류 요청
7. 서명: 내 트랙이 "영향" 대상인 changelog 항목에 [코드✓] 코멘트.
   ★ 서명 없는 영향 항목이 하나라도 있으면 해당 PR 머지 금지 (강제 규칙)
```

## 판정 규칙 (총괄 Master)
- 4인 "이상무" + 영향 항목 전서명 → 머지 진행 + GATE 판정 기록
- "충돌" 1건이라도 → 머지 보류, 충돌 당사자 2인 + 총괄 3자 확인 후 재체크
- 크로스체크 미수행자 있으면 게이트 판정 보류 (V4·V5는 예외 없음)
