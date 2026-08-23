"""테스트 공통 — DATABASE_URL 은 런타임 필수 env 이므로 테스트에서만 더미로 주입 (닿지 않는 포트)."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/test")
