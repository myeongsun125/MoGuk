"""저장 시 암호화 — AES-GCM(nonce||ct||tag), 테넌트 키 (M-19). [새봄]"""


def seal(payload: bytes, tenant_key: bytes) -> bytes:
    raise NotImplementedError("[새봄] services.crypto.seal")


def open_(blob: bytes, tenant_key: bytes) -> bytes:
    raise NotImplementedError("[새봄] services.crypto.open_")
