import os
import base64
import hashlib
import hmac
from typing import Optional

try:
    from cryptography.fernet import Fernet
    HAS_FERNET = True
except ImportError:
    HAS_FERNET = False
    Fernet = None

def _get_encryption_key() -> bytes:
    """Retrieves or derives the 32-byte encryption key."""
    env_key = os.environ.get("TOKEN_ENCRYPTION_KEY")
    if env_key:
        raw = env_key.strip().encode("utf-8")
        # Ensure 32-byte base64 valid key
        try:
            decoded = base64.urlsafe_b64decode(raw)
            if len(decoded) == 32:
                return raw
        except Exception:
            pass
        # Derive 32-byte urlsafe base64 key from arbitrary secret
        derived = hashlib.sha256(raw).digest()
        return base64.urlsafe_b64encode(derived)
    
    # Fallback default key for development/test only
    dev_secret = b"CodeVanguardDevEncryptionKey2026!"
    return base64.urlsafe_b64encode(hashlib.sha256(dev_secret).digest())

def encrypt_token(raw_token: Optional[str]) -> Optional[str]:
    """
    Encrypts a user OAuth access token using Fernet (AES-128-CBC + HMAC-SHA256).
    Falls back gracefully to standard library HMAC stream encryption if cryptography is not installed.
    """
    if not raw_token:
        return None

    key = _get_encryption_key()

    if HAS_FERNET and Fernet:
        f = Fernet(key)
        return f.encrypt(raw_token.encode("utf-8")).decode("utf-8")

    # Fallback standard-library cipher: HMAC-SHA256 authenticated XOR stream
    raw_bytes = raw_token.encode("utf-8")
    salt = os.urandom(16)
    stream_key = hmac.new(key, salt, hashlib.sha256).digest()
    
    # Keystream expansion
    keystream = bytearray()
    counter = 0
    while len(keystream) < len(raw_bytes):
        keystream.extend(hmac.new(stream_key, counter.to_bytes(4, 'big'), hashlib.sha256).digest())
        counter += 1

    encrypted = bytes(b ^ k for b, k in zip(raw_bytes, keystream[:len(raw_bytes)]))
    auth_tag = hmac.new(stream_key, encrypted, hashlib.sha256).digest()
    payload = salt + auth_tag + encrypted
    return "cv1:" + base64.urlsafe_b64encode(payload).decode("utf-8")

def decrypt_token(cipher_token: Optional[str]) -> Optional[str]:
    """
    Decrypts an encrypted user access token back into plaintext.
    """
    if not cipher_token:
        return None

    key = _get_encryption_key()

    if cipher_token.startswith("cv1:"):
        # Fallback decryption
        try:
            payload = base64.urlsafe_b64decode(cipher_token[4:].encode("utf-8"))
            salt = payload[:16]
            expected_tag = payload[16:48]
            encrypted = payload[48:]

            stream_key = hmac.new(key, salt, hashlib.sha256).digest()
            calculated_tag = hmac.new(stream_key, encrypted, hashlib.sha256).digest()

            if not hmac.compare_digest(expected_tag, calculated_tag):
                raise ValueError("Token decryption authentication failed.")

            keystream = bytearray()
            counter = 0
            while len(keystream) < len(encrypted):
                keystream.extend(hmac.new(stream_key, counter.to_bytes(4, 'big'), hashlib.sha256).digest())
                counter += 1

            decrypted = bytes(b ^ k for b, k in zip(encrypted, keystream[:len(encrypted)]))
            return decrypted.decode("utf-8")
        except Exception as e:
            raise ValueError(f"Failed to decrypt user token: {e}")

    if HAS_FERNET and Fernet:
        try:
            f = Fernet(key)
            return f.decrypt(cipher_token.encode("utf-8")).decode("utf-8")
        except Exception as e:
            raise ValueError(f"Failed to decrypt user token: {e}")

    raise ValueError("Cannot decrypt token: cryptography library is required for standard Fernet tokens.")
