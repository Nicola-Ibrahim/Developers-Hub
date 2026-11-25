"""Password and opaque-secret primitives for the internal identity adapter."""

import hashlib
import hmac

from argon2 import PasswordHasher as Argon2PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_SCRYPT_N = 1 << 14
_SCRYPT_R = 8
_SCRYPT_P = 1


class Argon2idPasswordHasher:
    def __init__(self) -> None:
        self._argon2 = Argon2PasswordHasher()
        self._dummy_hash = self._argon2.hash("devops-hub-dummy-password-value")

    def hash(self, password: str) -> str:
        return self._argon2.hash(password)

    def verify(self, password: str, encoded: str | None) -> bool:
        if encoded is None:
            try:
                self._argon2.verify(self._dummy_hash, password)
            except (InvalidHashError, VerificationError, VerifyMismatchError):
                pass
            return False
        if encoded.startswith("$argon2id$"):
            try:
                return self._argon2.verify(encoded, password)
            except (InvalidHashError, VerificationError, VerifyMismatchError):
                return False
        return self._verify_scrypt(password, encoded)

    def needs_rehash(self, encoded: str) -> bool:
        if not encoded.startswith("$argon2id$"):
            return True
        try:
            return self._argon2.check_needs_rehash(encoded)
        except InvalidHashError:
            return True

    @staticmethod
    def _verify_scrypt(password: str, encoded: str) -> bool:
        try:
            algorithm, n, r, p, salt_hex, expected_hex = encoded.split("$", 5)
            if (
                algorithm != "scrypt"
                or int(n) != _SCRYPT_N
                or int(r) != _SCRYPT_R
                or int(p) != _SCRYPT_P
            ):
                return False
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(expected_hex)
            if len(salt) != 16 or len(expected) != 32:
                return False
            candidate = hashlib.scrypt(
                password.encode(),
                salt=salt,
                n=_SCRYPT_N,
                r=_SCRYPT_R,
                p=_SCRYPT_P,
                dklen=len(expected),
            )
            return hmac.compare_digest(candidate, expected)
        except (ValueError, TypeError, MemoryError):
            return False
