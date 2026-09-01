"""테스트 공통 — core 역할 경로도 돌리기 위해 DATABASE_URL 더미 주입(닿지 않는 포트). 역할은 테스트에서 monkeypatch."""

import base64
import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/test")

# M-19: 원문 봉인은 평문 폴백이 없어 키가 없으면 접수(쓰기)가 실패한다.
# 시크릿이 아니라 테스트용 고정 더미 — 운영 키는 배포 env(TENANT_CRYPTO_KEY)로만 온다.
# 키 부재 동작을 검증하는 테스트는 monkeypatch.delenv 로 각자 지운다.
os.environ.setdefault(
    "TENANT_CRYPTO_KEY",
    base64.urlsafe_b64encode(b"moguk-test-key-32bytes-padding!!").decode(),
)
