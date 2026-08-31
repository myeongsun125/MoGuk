"""인증 — 초대 토큰 → PIN 해시 → JWT + 리프레시 (M-15). [새봄]

계약(001 정본):
- workers(pin_hash, invited_at, activated_at) / invites(token PK, worker_id, expires_at, used_at)
- invites 의 expires_at·used_at 이 "일회성 초대 토큰(만료·1회 소진)"(M-15·BLUEPRINT §4-9)의
  저장 근거다. 만료·소진·미존재는 **전부 동일한 401** 로 응답해 토큰 존재 여부를 노출하지 않는다.

PIN:
- 평문 저장 금지. PBKDF2-HMAC-SHA256(표준 라이브러리 hashlib) + 사용자별 랜덤 솔트.
- 저장 형식 `pbkdf2_sha256$<iters>$<salt_b64>$<hash_b64>` — 알고리즘·반복수를 값에 담아
  추후 상향 시 기존 해시와 공존 가능.

JWT:
- HS256 + JWT_SECRET(기존 env, compose 가 edge·core 양쪽에 주입).
- 페이로드: sub·wid(worker_id)·tenant·typ(access|refresh)·iat·exp·jti.
  wid·tenant 는 M-04 테넌트 해석과 PR-2 actor 의 소스가 된다.
- 만료·회전 정책은 계약 공백 — 아래 기본값으로 구현하고 env 로 조정 가능하게 둔다.
  JWT_ACCESS_TTL_S=1800(30분) · JWT_REFRESH_TTL_S=1209600(14일)
  ※ .env.example·compose 등재는 BG 후속. 미등재 상태에서도 기본값으로 동작한다.

리프레시 회전의 한계: 001 에 리프레시 저장소(jti 블랙리스트 등)가 없어 **회전은 새 쌍 발급까지**이고
구 리프레시를 만료 전에 무효화하지 못한다. M-xx 후보로 보고한다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import uuid

import jwt

from app.services import tenancy

log = logging.getLogger(__name__)

# PIN 해시 파라미터
PBKDF2_ALGO = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 240_000
PBKDF2_SALT_BYTES = 16

DEFAULT_ACCESS_TTL_S = 1800
DEFAULT_REFRESH_TTL_S = 1_209_600
JWT_ALGORITHM = "HS256"

TYP_ACCESS = "access"
TYP_REFRESH = "refresh"

# 계정 존재 여부가 드러나지 않도록 실패는 전부 이 메시지 하나로 응답한다.
AUTH_FAILED_MESSAGE = "인증에 실패했습니다."

_SELECT_INVITE = """
SELECT i.token, i.worker_id, i.expires_at, i.used_at, w.id, w.lang
FROM invites i JOIN workers w ON w.id = i.worker_id
WHERE i.token = %(token)s
"""

_ACTIVATE_WORKER = """
UPDATE workers SET pin_hash = %(pin_hash)s, activated_at = now() WHERE id = %(id)s
"""

_CONSUME_INVITE = """
UPDATE invites SET used_at = now() WHERE token = %(token)s AND used_at IS NULL
"""

_SELECT_WORKER_BY_EMP_NO = """
SELECT id, pin_hash FROM workers WHERE emp_no = %(emp_no)s
"""


class AuthError(Exception):
    """인증 실패 — 사유를 응답으로 구분하지 않는다(계정 존재 여부 비노출)."""


# ── 설정 ──────────────────────────────────────────────────

def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        log.warning("auth: env %s=%r 가 정수가 아님 — 기본값 %s 사용", name, raw, default)
        return default
    if value <= 0:
        log.warning("auth: env %s=%r 가 0 이하 — 기본값 %s 사용", name, raw, default)
        return default
    return value


def access_ttl_s() -> int:
    return _env_int("JWT_ACCESS_TTL_S", DEFAULT_ACCESS_TTL_S)


def refresh_ttl_s() -> int:
    return _env_int("JWT_REFRESH_TTL_S", DEFAULT_REFRESH_TTL_S)


def jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        # 기동 시 필수 — 비어 있으면 서명 검증이 무의미해진다
        raise RuntimeError("required env JWT_SECRET is not set (see .env.example)")
    return secret


# ── PIN 해시 (평문 저장 금지) ─────────────────────────────

def hash_pin(pin: str, *, salt: bytes | None = None, iterations: int | None = None) -> str:
    salt = secrets.token_bytes(PBKDF2_SALT_BYTES) if salt is None else salt
    iterations = PBKDF2_ITERATIONS if iterations is None else iterations
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations)
    return "$".join(
        [
            PBKDF2_ALGO,
            str(iterations),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        ]
    )


def verify_pin(pin: str, stored: str | None) -> bool:
    """저장 해시와 대조. 형식 위반·미설정은 False (예외를 던지지 않는다)."""
    if not stored:
        return False
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != PBKDF2_ALGO:
            return False
        expected = base64.b64decode(hash_b64)
        digest = hashlib.pbkdf2_hmac(
            "sha256", pin.encode("utf-8"), base64.b64decode(salt_b64), int(iters)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)


def _burn_time() -> None:
    """계정 미존재 시에도 대조와 비슷한 시간을 쓰게 해 타이밍으로 구분되지 않게 한다."""
    hashlib.pbkdf2_hmac("sha256", b"-", b"-" * PBKDF2_SALT_BYTES, PBKDF2_ITERATIONS)


# ── JWT ───────────────────────────────────────────────────

def _issue(worker_id: int, tenant: str, typ: str, ttl_s: int) -> str:
    now = int(time.time())
    payload = {
        "sub": f"worker:{worker_id}",
        "wid": worker_id,
        "tenant": tenant,
        "typ": typ,
        "iat": now,
        "exp": now + ttl_s,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGORITHM)


def issue_token_pair(worker_id: int, tenant: str | None = None) -> dict:
    """{jwt, refresh} — skeleton §3 응답 계약."""
    tenant = tenant or tenancy.tenant_slug()
    return {
        "jwt": _issue(worker_id, tenant, TYP_ACCESS, access_ttl_s()),
        "refresh": _issue(worker_id, tenant, TYP_REFRESH, refresh_ttl_s()),
    }


def decode_token(token: str, *, expect_typ: str = TYP_ACCESS) -> dict:
    """서명·만료·용도 검증. 실패는 전부 AuthError (사유 비노출)."""
    try:
        claims = jwt.decode(
            token,
            jwt_secret(),
            algorithms=[JWT_ALGORITHM],  # alg 혼동 방지 — HS256 만 허용
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthError(str(exc)) from exc
    if claims.get("typ") != expect_typ:
        raise AuthError(f"typ mismatch: {claims.get('typ')!r} != {expect_typ!r}")
    if not isinstance(claims.get("wid"), int):
        raise AuthError("wid claim missing")
    return claims


def rotate(refresh_token: str) -> dict:
    """리프레시 → 새 {jwt, refresh} 쌍. 구 리프레시 무효화는 저장소 부재로 불가(미해결)."""
    claims = decode_token(refresh_token, expect_typ=TYP_REFRESH)
    return issue_token_pair(claims["wid"], claims.get("tenant"))


# ── 저장소 연동 ───────────────────────────────────────────

def activate(token: str, pin: str) -> dict:
    """초대 토큰 1회 소진 + PIN 해시 저장 → {jwt, refresh, lang}. 단일 트랜잭션.

    lang(M-35) 은 workers.lang(001 CHECK vi|in) 그대로다 — JWT claim 에는 넣지 않는다.
    """
    tenant = tenancy.tenant_slug()
    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_INVITE, {"token": token})
            row = cur.fetchone()
            if row is None:
                _burn_time()
                raise AuthError("invite not found")
            _, worker_id, expires_at, used_at, _, lang = row
            if used_at is not None:
                raise AuthError("invite already used")
            if expires_at is not None and expires_at.timestamp() <= time.time():
                raise AuthError("invite expired")

            cur.execute(_ACTIVATE_WORKER, {"id": worker_id, "pin_hash": hash_pin(pin)})
            cur.execute(_CONSUME_INVITE, {"token": token})
            if cur.rowcount == 0:  # 동시 활성화 경합 — 먼저 소진한 쪽만 성공
                raise AuthError("invite already used (race)")
        conn.commit()

    log.info("auth: activate worker_id=%s tenant=%s lang=%s", worker_id, tenant, lang)
    return {**issue_token_pair(worker_id, tenant), "lang": lang}


def login(emp_no: str, pin: str) -> dict:
    """사번+PIN → {jwt, refresh}. 계정 미존재·PIN 불일치를 응답으로 구분하지 않는다."""
    tenant = tenancy.tenant_slug()
    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_WORKER_BY_EMP_NO, {"emp_no": emp_no})
            row = cur.fetchone()
    if row is None:
        _burn_time()
        raise AuthError("worker not found")
    worker_id, pin_hash = row
    if not verify_pin(pin, pin_hash):
        raise AuthError("pin mismatch")

    log.info("auth: login worker_id=%s tenant=%s", worker_id, tenant)
    return issue_token_pair(worker_id, tenant)
