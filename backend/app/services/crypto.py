"""저장 시 암호화 — AES-GCM(nonce||ct||tag), 테넌트 키 (M-19). [새봄]

적용 범위(총괄 확정 2026-09-01): risk_reports.original_text 1컬럼.
questions·ko_summary 는 이월, 001 무접촉(컬럼 타입 변경 없음 — text 에 마커+base64 문자열).

규약:
- 봉인 형식 = nonce(12B) || ciphertext || tag  (§ 계약 문면 그대로)
- 텍스트 계층 = "enc1:" + urlsafe-base64(봉인 바이트)
- **이중 읽기**: 마커가 있으면 복호, 없으면 평문 그대로 통과(기존 행 호환).
- **평문 폴백 쓰기 금지**: 키 부재·형식 오류면 seal_text 가 예외를 올린다.
  암호화하지 못한 원문을 평문으로 저장하는 경로는 존재하지 않는다.

키: env TENANT_CRYPTO_KEY = urlsafe-base64(32바이트). import 시점이 아니라
사용 시점에 읽는다 — 키 없는 환경(테스트·edge)에서도 모듈 적재는 성공해야 한다.
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_ENV = "TENANT_CRYPTO_KEY"
KEY_BYTES = 32          # AES-256
NONCE_BYTES = 12        # GCM 표준 nonce 길이
ENC_MARKER = "enc1:"    # 텍스트 계층 봉인 마커 (버전 축 = 1)

# env 원문 → 디코드된 키. env 가 바뀌면 캐시가 자동으로 빗나간다(테스트 격리).
_key_cache: dict[str, bytes] = {}


class CryptoKeyError(RuntimeError):
    """테넌트 키 부재·형식 오류·길이 오류 — 쓰기는 이 예외로 실패한다(평문 폴백 없음)."""


def tenant_key() -> bytes:
    """env TENANT_CRYPTO_KEY 를 디코드해 32바이트 키로 돌려준다(사용 시점 로드)."""
    raw = os.getenv(KEY_ENV)
    if not raw:
        raise CryptoKeyError(
            f"{KEY_ENV} 미설정 — 원문 봉인 불가(M-19: 평문 저장 폴백 없음)"
        )
    # 배포 env 실값은 패딩 '=' 없는 43자로 올 수 있다(EC2 실측) — 디코드 전 보정.
    # 개행·공백 혼입도 함께 걷어낸다. 보정 실패(형식·길이)는 아래 검증이 그대로 잡는다.
    raw = raw.strip()
    raw += "=" * (-len(raw) % 4)
    cached = _key_cache.get(raw)
    if cached is not None:
        return cached
    try:
        key = base64.urlsafe_b64decode(raw)
    except (ValueError, TypeError) as exc:
        raise CryptoKeyError(f"{KEY_ENV} 형식 오류 — urlsafe-base64 아님: {exc}") from exc
    if len(key) != KEY_BYTES:
        raise CryptoKeyError(
            f"{KEY_ENV} 길이 오류 — {len(key)}바이트 (필요 {KEY_BYTES}바이트)"
        )
    _key_cache[raw] = key
    return key


def seal(payload: bytes, tenant_key: bytes) -> bytes:
    """AES-GCM 봉인. 반환 = nonce || ciphertext || tag."""
    nonce = os.urandom(NONCE_BYTES)
    return nonce + AESGCM(tenant_key).encrypt(nonce, payload, None)


def open_(blob: bytes, tenant_key: bytes) -> bytes:
    """seal 의 역연산. 무결성 실패는 예외를 그대로 올린다(조용한 폴백 없음)."""
    if len(blob) <= NONCE_BYTES:
        raise ValueError(f"봉인 블롭 길이 부족 — {len(blob)}바이트")
    nonce, body = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
    return AESGCM(tenant_key).decrypt(nonce, body, None)


def seal_text(text: str) -> str:
    """평문 → "enc1:"+urlsafe-b64. 키가 없으면 CryptoKeyError — 평문을 돌려주지 않는다."""
    blob = seal(text.encode("utf-8"), tenant_key())
    return ENC_MARKER + base64.urlsafe_b64encode(blob).decode("ascii")


def open_text(value: str | None) -> str | None:
    """이중 읽기 — 마커가 있으면 복호, 없으면(기존 평문 행) 입력 그대로."""
    if not isinstance(value, str) or not value.startswith(ENC_MARKER):
        return value
    blob = base64.urlsafe_b64decode(value[len(ENC_MARKER):])
    return open_(blob, tenant_key()).decode("utf-8")
