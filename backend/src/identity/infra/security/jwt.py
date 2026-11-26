"""JWT transport for browser sessions; database session rows remain authoritative."""

import secrets
from datetime import datetime

import jwt
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from jwt import InvalidTokenError

from identity.application.interfaces.session_tokens import SessionTokenIssuer, SessionTokenVerifier

_ISSUER = "developers-hub"
_AUDIENCE = "developers-hub-browser"
_ALGORITHM = "HS256"
_INFO = b"developers-hub/browser-session-jwt/v1"


class JwtSessionTokens(SessionTokenIssuer, SessionTokenVerifier):
    def __init__(self, token_pepper: str) -> None:
        self._key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_INFO).derive(
            token_pepper.encode()
        )

    def issue(self, subject: str, issued_at: datetime, expires_at: datetime) -> str:
        return jwt.encode(
            {
                "iss": _ISSUER,
                "aud": _AUDIENCE,
                "sub": subject,
                "jti": secrets.token_urlsafe(24),
                "iat": int(issued_at.timestamp()),
                "exp": int(expires_at.timestamp()),
            },
            self._key,
            algorithm=_ALGORITHM,
        )

    def verify(self, token: str) -> bool:
        try:
            jwt.decode(
                token,
                self._key,
                algorithms=[_ALGORITHM],
                issuer=_ISSUER,
                audience=_AUDIENCE,
                options={"require": ["iss", "aud", "sub", "jti", "iat", "exp"]},
            )
            return True
        except InvalidTokenError:
            return False
