# MoGuk — 소규모 제조 사업장 다국어 소통·지식 플랫폼 (팀 AXIs)

온프레미스 LLM·RAG 기반, 외국인 근로자가 모국어로 일을 배우고 이해를 증명하는 플랫폼.

## 퀵스타트 (전 팀원 공통)

```bash
git clone https://github.com/myeongsun125/MoGuk.git && cd MoGuk
cp .env.example .env          # 로컬 비밀번호 등 수정
docker compose up -d --build
curl -s localhost:8000/health  # {"status":"ok", ...} 확인
```

내리기: `docker compose down` (DB 데이터 유지) / 초기화: `docker compose down -v`

## 디렉터리와 소유권

| 경로 | 담당 | 내용 |
|---|---|---|
| `backend/` | 새봄 | FastAPI. 현재는 인프라 스텁(`app/main.py`) — 본 구현으로 대체하되 `/health` 계약 유지 |
| `frontend/` | 정현 | React (예정) |
| `ingestion/` | 명선 | 문서 적재 파이프라인 (예정) — 임베딩 bge-m3 고정 |
| `infra/` | 병갑 | prod compose, Caddy(HTTPS), 배포·복구 스크립트 |
| `.github/workflows/` | 병갑 | CI/CD (예정: build → Trivy 스캔 → GHCR → deploy) |

## /health 계약 (변경 시 병갑과 합의)

- `GET /health` → **200**(정상) / **503**(핵심 컴포넌트 이상)
- 응답: `status`, `version`, `slot`(blue/green), `components{api, db, llm}`
- 이 계약은 blue-green 배포 게이트·자동 재기동 판정 기준이므로 임의 변경 금지.

## 브랜치 전략 (경량)

- `main` = 배포 가능 상태 유지. 기능은 `feat/<이름>-<주제>` 브랜치 → PR → 1인 이상 리뷰 → 머지.
- 머지 시 CI 통과 필수(8/3 CI 구성 후 적용).
