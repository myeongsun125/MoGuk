# 2026-08-23 — skeleton v3 스캐폴딩 (PR #3) · 보안 차단 사례 2건

PR: https://github.com/myeongsun125/MoGuk/pull/3 · 브랜치 `feat/skeleton-v3` · 기준 main @ 76c9e25

## 보안 차단 사례 (발표 증거용)

### 사례 1 — A-04 (구 C-04): DB 비밀번호 하드코딩 제거 (R1 즉시 수정)
| 항목 | 내용 |
|---|---|
| 발견 | 선행 감사(2026-08-23). `docker-compose.yml` `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-moguk}` 폴백 + `backend/app/main.py` `DATABASE_URL` 기본값 `postgresql://moguk:moguk@db:5432/moguk` |
| 위험 | prod 복제 시 기본 비밀번호로 기동 — 인지 없이 취약 상태 운영 |
| 조치 | compose 전 지점 `${POSTGRES_PASSWORD:?}` 필수화 → 미설정 시 `docker compose` 가 기동 거부. 코드 기본값 제거 → core-api 는 `DATABASE_URL` 없으면 import 단계에서 `RuntimeError` 로 기동 실패. edge-api 는 내부 DB 자격증명 자체를 갖지 않음(M-22) |
| 증거 | 커밋 `a73c190`(backend), `4ba2def`(compose), 후속 커밋(M-22). 로컬: `API_ROLE=core python -c "from app.main import app"` → `RuntimeError: required env DATABASE_URL is not set`. CI verify job 은 env 를 명시 주입해야만 통과 |

### 사례 2 — Trivy 게이트: HIGH 36건 머지 전 차단
| 항목 | 내용 |
|---|---|
| 발견 | PR #3 첫 CI 실행(run 32631316840) `build-scan-push` 실패 — `python:3.12-slim`(debian 13.6) 베이스 OS 패키지 util-linux 계열(bsdutils·libblkid1·libmount1·libuuid1·mount·login 등) HIGH 36 / CRITICAL 0. 파이썬 패키지 0건 |
| 위험 | 수정판(`2.41.5-0+deb13u1`)이 존재하는 알려진 취약점을 실은 이미지가 GHCR 로 푸시될 뻔함 |
| 조치 | `backend/Dockerfile` 에 `apt-get update && apt-get upgrade -y` 추가(커밋 `970b83d`). 재실행 CI success — 게이트 ②가 설계대로 **머지 전** 차단 |
| 증거 | 실패 run: https://github.com/myeongsun125/MoGuk/actions/runs/32631316840 · 성공 run: 동일 브랜치 후속 run (커밋 970b83d) |

## 결정 기록
- **M-22** edge-api 내부 DB 자격증명 0 · core_net 미가입 · `/health` = self + core 릴레이(하트비트) · core_net `internal: true`
- **M-23** 암호문 시연 저장소 edge-db 자리(profile full), 8/26 알파 확정
- DDL: 단일 출처 = `db/migrations/001_tenant_template.sql`(§2 상단 명시), `CREATE EXTENSION vector`·`tenant_settings` 시드·멱등화 승인
- `ingestion/.gitkeep` 삭제 승인 (v3 트리는 `pipeline/`)
- A-06 브랜치 보호: private 유지 + main 직push 금지 컨벤션
