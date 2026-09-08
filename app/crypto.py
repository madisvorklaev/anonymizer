"""Local symmetric encryption for stored redaction snapshots.

The key never leaves this machine. Losing data/secret.key means stored
snapshots can no longer be decrypted, so back it up if you care about
being able to restore later.
"""
from pathlib import Path

from cryptography.fernet import Fernet

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
KEY_PATH = DATA_DIR / "secret.key"


def _load_or_create_key() -> bytes:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if KEY_PATH.exists():
        return KEY_PATH.read_bytes()
    key = Fernet.generate_key()
    KEY_PATH.write_bytes(key)
    return key


_fernet = Fernet(_load_or_create_key())


def encrypt(data: bytes) -> bytes:
    return _fernet.encrypt(data)


def decrypt(token: bytes) -> bytes:
    return _fernet.decrypt(token)
