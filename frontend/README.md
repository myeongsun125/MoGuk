# frontend [정현]

- `src/apps/worker/` 근로자 모바일 웹: learn, quiz, chat, report, inbox, speaking
- `src/apps/admin/` 대시보드, 승인큐, 위험보고, 안전일지, 문서업로드
- `src/i18n/{ko,vi,in}/` — 키 규칙 `{app}.{screen}.{element}` (skeleton-v3 §6)
- Mock 경계(§7): `/ask` fixture JSON(`backend/app/fixtures/ask.json` 와 동일 형태), 대시보드 더미 KPI → 8/24 실연동 교체
- `Dockerfile`·`public/index.html` 은 compose 기동용 자리표시자 — Vite 도입 시 교체
