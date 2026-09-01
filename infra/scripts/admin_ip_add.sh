#!/usr/bin/env bash
# 본선장 등 현장 IP를 admin 화이트리스트에 추가하고 caddy만 재생성 — EC2 ~/MoGuk에서 실행
# 사용: infra/scripts/admin_ip_add.sh <공인IP> [설명]
set -euo pipefail
cd "$(dirname "$0")/../.."
IP="${1:?usage: $0 <ip> [label]}"; LABEL="${2:-}"
grep -q "^ADMIN_ALLOW_IPS=" .env || { echo "ERROR: .env에 ADMIN_ALLOW_IPS 없음"; exit 1; }
if grep "^ADMIN_ALLOW_IPS=" .env | grep -qw "$IP"; then
  echo "이미 등록됨: $IP"
else
  sed -i "s/^ADMIN_ALLOW_IPS=.*/& $IP/" .env
  echo "추가: $IP ${LABEL:+($LABEL)}"
fi
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --no-deps caddy
echo -n "현재 화이트리스트: "; grep "^ADMIN_ALLOW_IPS=" .env | cut -d= -f2
echo "검증: 해당 IP에서 curl -s -o /dev/null -w '%{http_code}' https://moguk.ai.kr/api/v1/admin/dashboard → 200"

