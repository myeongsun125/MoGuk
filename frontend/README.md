# frontend [정현]

- Vite + React + TypeScript. 상태관리 라이브러리 없음(useState/context) · 라우팅 react-router.
- `src/apps/worker/` 근로자 모바일 웹: learn, quiz, chat, report, inbox, speaking
- `src/apps/admin/` 대시보드, 승인큐, 위험보고, 안전일지, 문서업로드
- `src/i18n/{ko,vi,in}/` — 키 규칙 `{app}.{screen}.{element}` (skeleton-v3 §6)
- Mock 경계(§7): `src/api/ask.ts`·`src/api/auth.ts` 에 격리, `VITE_USE_MOCK`(기본 true)로 분기.
  mock 응답은 `backend/app/fixtures/ask.json` 과 동일 형태(`src/api/fixtures/ask.fixtures.ts`).
  실연동(SB V2-2) cutover 시 이 두 파일만 교체.
- 개발: `npm i && npm run dev` (dev 서버가 `/api/v1` → localhost:8000 (compose 노출 포트, prod는 Caddy→edge-api) 프록시)
- 빌드: `npm run build` / 스크린샷: `npm run shot` → `docs/assets/v2-1-ask-390.png`
- V4 리허설: `npm run rehearse` → `docs/assets/v4-*` (mock 로컬 서버 자동 기동).
  배포본 대상 재검증은 `BASE_URL=<url> npm run rehearse` — 실패 예상/탐색 실행이 canonical
  `v4-*` 산출물을 덮어쓰지 않도록 `OUT_SUFFIX=<name>`으로 파일명 분리 가능
  (예: `OUT_SUFFIX=ec2-1st BASE_URL=<url> npm run rehearse` → `v4-rehearsal-ec2-1st.webm`).
