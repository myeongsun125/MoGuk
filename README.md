# MoGuk — 소규모 제조 사업장 다국어 소통·지식 플랫폼 (팀 AXIs)

온프레미스 LLM·RAG 기반, 외국인 근로자가 모국어로 일을 배우고 이해를 증명하는 플랫폼.

## 퀵스타트 (전 팀원 공통)

```bash
git clone https://github.com/myeongsun125/MoGuk.git && cd MoGuk
cp .env.example .env          # 로컬 비밀번호 등 수정
docker compose up -d --build
curl -s localhost:8000/health  # {"status":"ok", ...} 확인 (edge-api)
curl -s -XPOST localhost:8000/api/v1/ask -H 'content-type: application/json' -d '{"question":"...","lang":"vi"}'  # mock 응답
```

내리기: `docker compose down` (DB 데이터 유지) / 초기화: `docker compose down -v`

## 디렉터리와 소유권 (docs/skeleton-v3.md §1 기준 — 그 문서가 SSOT)

| 경로 | 담당 | 내용 |
|---|---|---|
| `backend/` | 새봄 | FastAPI `app/` — routers·agents·services·modules·models·workers. 같은 이미지가 `API_ROLE=edge\|core` 로 2회 기동 |
| `frontend/` | 정현 | React (worker/admin 앱, i18n). 현재 nginx 자리표시자 |
| `pipeline/` | 명선 | Dagster 에셋 5종 (documents_raw → … → manager_report) |
| `db/migrations/`, `scripts/apply_tenant.sh` | 명선 | 테넌트 스키마 템플릿 DDL (schema-per-tenant) |
| `experiments/` | 명선·새봄 | 예선 정량 실험 (testset·mistranslation_eval·gate_eval) |
| `data/seed/` | 명선 | 시드 데이터 (manuals·kosha·glossary·phrases·quiz·safety_courses) |
| `infra/`, `docker-compose*.yml`, `.env.example`, `.github/workflows/` | 병갑 | compose(core_net/edge_net 8서비스), Caddy, CI/CD, blue-green |
| `tests/` | 새봄 | pytest (CI 게이트) — `pytest -q` (pytest.ini 가 backend 를 pythonpath 로 잡음) |
| `docs/` | 전원 | `skeleton-v3.md`(SSOT) · `DECISIONS.md` · `WORKLOG/` · `archive/` |

퀵스타트 참고: `.env` 에 `POSTGRES_PASSWORD` 는 **필수**(미설정 시 compose 가 거부). `stt`·`dagster` 는 `--profile full` 에서만 기동.
테넌트 생성: `scripts/apply_tenant.sh <slug> --compose`.

## /health 계약 (변경 시 병갑과 합의)

- `GET /health` → **200**(정상) / **503**(핵심 컴포넌트 이상)
- 응답: `status`, `version`, `slot`(blue/green), `components{api, db, llm}`
- 이 계약은 blue-green 배포 게이트·자동 재기동 판정 기준이므로 임의 변경 금지.

## 브랜치 전략 (경량)

- `main` = 배포 가능 상태 유지. 기능은 `feat/<이름>-<주제>` 브랜치 → PR → 1인 이상 리뷰 → 머지.
- 머지 시 CI 통과 필수(8/3 CI 구성 후 적용).
