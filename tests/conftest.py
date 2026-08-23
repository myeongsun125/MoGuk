"""테스트 공통 — core 역할 경로도 돌리기 위해 DATABASE_URL 더미 주입(닿지 않는 포트). 역할은 테스트에서 monkeypatch."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/test")
