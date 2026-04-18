from __future__ import annotations

import hashlib
import random
import secrets
from typing import cast

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.utils.types import TokenPayload


password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
DUMMY_PASSWORD_HASH = password_hasher.hash("VynfyLedgerDummyPassword123!")

COMMON_PASSWORD_SNIPPETS: frozenset[str] = frozenset(
    {
        "password",
        "123456",
        "qwerty",
        "admin",
        "welcome",
    }
)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def consume_dummy_password_check(password: str) -> None:
    verify_password(DUMMY_PASSWORD_HASH, password)


def validate_password_policy(password: str) -> list[str]:
    errors: list[str] = []
    min_length = current_app.config["PASSWORD_MIN_LENGTH"]
    if len(password) < min_length:
        errors.append(f"Password must be at least {min_length} characters.")
    if password.lower() == password or password.upper() == password:
        errors.append("Password must include a mix of uppercase and lowercase letters.")
    if not any(char.isdigit() for char in password):
        errors.append("Password must include at least one number.")
    lowered = password.lower()
    if any(snippet in lowered for snippet in COMMON_PASSWORD_SNIPPETS):
        errors.append("Password is too common. Use a stronger passphrase.")
    return errors


def generate_token(payload: TokenPayload) -> str:
    serializer = URLSafeTimedSerializer(
        secret_key=current_app.config["SECRET_KEY"], salt=current_app.config["SECURITY_PASSWORD_SALT"]
    )
    return serializer.dumps(payload)


def load_token(token: str, max_age: int) -> TokenPayload:
    serializer = URLSafeTimedSerializer(
        secret_key=current_app.config["SECRET_KEY"], salt=current_app.config["SECURITY_PASSWORD_SALT"]
    )
    try:
        return cast(TokenPayload, serializer.loads(token, max_age=max_age))
    except (BadSignature, SignatureExpired) as exc:
        raise ValueError("Invalid or expired token.") from exc


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_numeric_code(length: int = 6) -> str:
    digits = [str(random.SystemRandom().randrange(10)) for _ in range(length)]
    return "".join(digits)
