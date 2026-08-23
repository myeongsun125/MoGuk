#!/usr/bin/env bash
# 테넌트 스키마 생성 — db/migrations/*.sql 의 {slug} 를 치환해 순서대로 적용. [명선]
#
# 사용:
#   DATABASE_URL=postgresql://user:pw@host:5432/db scripts/apply_tenant.sh <slug>
#   docker compose exec -T postgres 환경이면:
#   scripts/apply_tenant.sh <slug> --compose        (compose의 postgres 서비스에 psql)
#
# slug 규칙: ^[a-z][a-z0-9_]{1,30}$ (스키마명 tenant_<slug>)
set -euo pipefail

SLUG="${1:-}"
MODE="${2:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MIGRATIONS="$ROOT/db/migrations"

if [[ ! "$SLUG" =~ ^[a-z][a-z0-9_]{1,30}$ ]]; then
  echo "usage: $0 <slug> [--compose]   (slug: ^[a-z][a-z0-9_]{1,30}$)" >&2
  exit 2
fi

if [[ "$MODE" == "--compose" ]]; then
  : "${POSTGRES_USER:=moguk}"
  : "${POSTGRES_DB:=moguk}"
  PSQL=(docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB")
else
  : "${DATABASE_URL:?DATABASE_URL is required (or pass --compose)}"
  PSQL=(psql -v ON_ERROR_STOP=1 "$DATABASE_URL")
fi

for f in "$MIGRATIONS"/*.sql; do
  echo ">> apply $(basename "$f") → tenant_${SLUG}"
  sed "s/{slug}/${SLUG}/g" "$f" | "${PSQL[@]}"
done
echo "done: tenant_${SLUG}"
