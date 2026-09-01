"""M-19 저장 암호화 — AES-GCM 봉인·이중 읽기 단위. [새봄]

검증 대상 계약:
- 봉인 형식 = nonce(12B) || ciphertext || tag, nonce 는 매회 랜덤
- 왕복 / 변조 시 예외 / 잘못된 키 예외 (조용한 폴백 없음)
- 키 미설정: seal_text 는 예외(평문 저장 폴백 금지), open_text 는 평문 통과
- 마커 없는 입력(기존 행)은 그대로 통과 — 이중 읽기

네트워크·LLM 실호출 없음.
"""

import base64
import os

import pytest
from cryptography.exceptions import InvalidTag

from app.services import crypto

PLAIN = "프레스 방호장치가 작동하지 않습니다. 확인 부탁드립니다."


def _key() -> str:
    return base64.urlsafe_b64encode(os.urandom(crypto.KEY_BYTES)).decode()


@pytest.fixture
def keyed(monkeypatch):
    value = _key()
    monkeypatch.setenv(crypto.KEY_ENV, value)
    return crypto.tenant_key()


# ── 봉인 형식 ─────────────────────────────────────────────

def test_seal_layout_is_nonce_ct_tag(keyed):
    blob = crypto.seal(PLAIN.encode("utf-8"), keyed)
    assert len(blob) > crypto.NONCE_BYTES
    # nonce 12B + ct(평문 길이) + tag 16B
    assert len(blob) == crypto.NONCE_BYTES + len(PLAIN.encode("utf-8")) + 16


def test_nonce_is_random_per_call(keyed):
    a = crypto.seal(b"same", keyed)
    b = crypto.seal(b"same", keyed)
    assert a[: crypto.NONCE_BYTES] != b[: crypto.NONCE_BYTES]
    assert a != b                       # 같은 평문이라도 봉인문은 매번 다르다


def test_roundtrip_bytes(keyed):
    blob = crypto.seal(PLAIN.encode("utf-8"), keyed)
    assert crypto.open_(blob, keyed).decode("utf-8") == PLAIN


def test_tampered_blob_raises(keyed):
    blob = bytearray(crypto.seal(PLAIN.encode("utf-8"), keyed))
    blob[-1] ^= 1                       # tag 1비트 변조
    with pytest.raises(InvalidTag):
        crypto.open_(bytes(blob), keyed)


def test_wrong_key_raises(keyed):
    blob = crypto.seal(PLAIN.encode("utf-8"), keyed)
    with pytest.raises(InvalidTag):
        crypto.open_(blob, os.urandom(crypto.KEY_BYTES))


def test_short_blob_raises(keyed):
    with pytest.raises(ValueError):
        crypto.open_(b"short", keyed)


# ── 텍스트 계층 · 이중 읽기 ───────────────────────────────

def test_seal_text_marker_and_roundtrip(keyed):
    sealed = crypto.seal_text(PLAIN)
    assert sealed.startswith(crypto.ENC_MARKER) and crypto.ENC_MARKER == "enc1:"
    assert PLAIN not in sealed                      # 평문이 그대로 남지 않는다
    assert crypto.open_text(sealed) == PLAIN


@pytest.mark.parametrize("value", ["마커 없는 기존 평문", "", "enc0:다른마커", None])
def test_open_text_passes_through_unmarked(keyed, value):
    assert crypto.open_text(value) == value


# ── 키 로더 ───────────────────────────────────────────────

def test_seal_text_without_key_raises(monkeypatch):
    """평문 폴백 쓰기 금지 — 키가 없으면 쓰기는 실패해야 한다."""
    monkeypatch.delenv(crypto.KEY_ENV, raising=False)
    with pytest.raises(crypto.CryptoKeyError):
        crypto.seal_text(PLAIN)


def test_open_text_without_key_still_passes_plain(monkeypatch):
    """읽기는 이중 — 키가 없어도 마커 없는 기존 행은 그대로 나온다."""
    monkeypatch.delenv(crypto.KEY_ENV, raising=False)
    assert crypto.open_text("기존 평문 행") == "기존 평문 행"


def test_open_text_without_key_raises_for_sealed(monkeypatch, keyed):
    sealed = crypto.seal_text(PLAIN)
    monkeypatch.delenv(crypto.KEY_ENV, raising=False)
    with pytest.raises(crypto.CryptoKeyError):
        crypto.open_text(sealed)


def test_key_env_without_padding_loads_same_key(monkeypatch):
    """배포 실값은 패딩 '=' 없는 43자 — 패딩·개행 유무와 무관하게 같은 키 bytes 로 로드."""
    padded = base64.urlsafe_b64encode(os.urandom(crypto.KEY_BYTES)).decode()
    assert len(padded) == 44 and padded.endswith("=")
    monkeypatch.setenv(crypto.KEY_ENV, padded)
    k_padded = crypto.tenant_key()

    unpadded = padded.rstrip("=")
    assert len(unpadded) == 43
    monkeypatch.setenv(crypto.KEY_ENV, unpadded)
    assert crypto.tenant_key() == k_padded

    monkeypatch.setenv(crypto.KEY_ENV, unpadded + chr(10))   # 개행 혼입도 strip 으로 흡수
    assert crypto.tenant_key() == k_padded


@pytest.mark.parametrize(
    "bad", ["!!not-base64!!", base64.urlsafe_b64encode(b"short-key").decode()]
)
def test_bad_key_env_raises(monkeypatch, bad):
    monkeypatch.setenv(crypto.KEY_ENV, bad)
    with pytest.raises(crypto.CryptoKeyError):
        crypto.tenant_key()


def test_key_is_loaded_at_use_time_not_import(monkeypatch):
    """모듈 적재는 키 없이도 성공한다 — 키는 호출 시점에 읽는다."""
    monkeypatch.delenv(crypto.KEY_ENV, raising=False)
    import importlib

    importlib.reload(crypto)            # 키 없는 환경에서 재적재해도 예외 없음
    value = _key()
    monkeypatch.setenv(crypto.KEY_ENV, value)
    assert len(crypto.tenant_key()) == crypto.KEY_BYTES
