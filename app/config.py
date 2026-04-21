from __future__ import annotations

import os
import secrets
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"
_INSECURE_SECRET_VALUES = {
    "",
    "secret",
    "jwt_secret",
    "change-me-in-production-with-32-plus-random-chars",
    "change-me-in-production-with-another-32-plus-secret",
    "replace-with-32-plus-random-characters",
    "replace-with-another-32-plus-random-characters",
}

load_dotenv(BASE_DIR / ".env")
DEFAULT_CONFIG_NAME = (os.getenv("APP_ENV") or os.getenv("FLASK_ENV") or "development").lower()


def _database_uri() -> str:
    env_value = os.getenv("DATABASE_URL")
    if not env_value:
        return f"sqlite:///{(INSTANCE_DIR / 'vynfy_ledger.db').as_posix()}"
    if env_value == "sqlite:///vynfy_ledger.db":
        return f"sqlite:///{(INSTANCE_DIR / 'vynfy_ledger.db').as_posix()}"
    return env_value


def _is_production() -> bool:
    return DEFAULT_CONFIG_NAME == "production"


def _csrf_time_limit() -> int | None:
    value = (os.getenv("WTF_CSRF_TIME_LIMIT") or "").strip()
    if not value or value.lower() == "none":
        return None
    return int(value)


def _secret_setting(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if value and value.lower() not in _INSECURE_SECRET_VALUES and len(value) >= 32:
        return value
    if _is_production():
        raise RuntimeError(f"{name} must be set to a unique secret with at least 32 characters in production.")
    return secrets.token_hex(32)


class Config:
    APP_NAME = "Vynfy Ledger"
    APP_ENV = DEFAULT_CONFIG_NAME
    SECRET_KEY = _secret_setting("SECRET_KEY")
    SECURITY_PASSWORD_SALT = _secret_setting("SECURITY_PASSWORD_SALT")
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Keep CSRF tokens valid for long-lived pages like the logout form.
    WTF_CSRF_TIME_LIMIT = _csrf_time_limit()
    REMEMBER_COOKIE_HTTPONLY = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = APP_ENV == "production"
    PREFERRED_URL_SCHEME = "https" if APP_ENV == "production" else "http"
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    UPLOAD_FOLDER = str(INSTANCE_DIR / "uploads")
    OUTBOX_FOLDER = str(INSTANCE_DIR / "outbox")
    ACCESS_SESSION_TTL = timedelta(minutes=int(os.getenv("ACCESS_SESSION_MINUTES", "45")))
    SESSION_ROTATE_AFTER = timedelta(minutes=int(os.getenv("SESSION_ROTATE_AFTER_MINUTES", "15")))
    LOGIN_LOCKOUT_BASE_MINUTES = int(os.getenv("LOGIN_LOCKOUT_BASE_MINUTES", "1"))
    MAX_LOGIN_LOCKOUT_MINUTES = int(os.getenv("MAX_LOGIN_LOCKOUT_MINUTES", "60"))
    MAX_FAILED_LOGINS = int(os.getenv("MAX_FAILED_LOGINS", "10"))
    PASSWORD_RESET_MINUTES = int(os.getenv("PASSWORD_RESET_MINUTES", "30"))
    ADMIN_STEP_UP_MINUTES = int(os.getenv("ADMIN_STEP_UP_MINUTES", "15"))
    PASSWORD_MIN_LENGTH = 12
    REGISTRATION_ENABLED = os.getenv("REGISTRATION_ENABLED", "true").lower() == "true"
    MAIL_FROM = os.getenv("MAIL_FROM", "no-reply@vynfy.internal")
    SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY") or (
        os.getenv("SMTP_PASSWORD") if os.getenv("SMTP_HOST") == "smtp.sendgrid.net" and os.getenv("SMTP_USERNAME") == "apikey" else None
    )
    SMTP_HOST = os.getenv("SMTP_HOST")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    FORCE_HTTPS = os.getenv("FORCE_HTTPS", "true" if APP_ENV == "production" else "false").lower() == "true"
    TRUST_PROXY_COUNT = int(os.getenv("TRUST_PROXY_COUNT", "1" if APP_ENV == "production" else "0"))
    ALLOW_DEMO_SEED = os.getenv("ALLOW_DEMO_SEED", "false").lower() == "true"
    RATELIMIT_HEADERS_ENABLED = True
    RATELIMIT_DEFAULT = "300 per hour"
    DEFAULT_PAGE_SIZE = 10
    DASHBOARD_MONTHS = 6
    COMPANY_NAME = os.getenv("COMPANY_NAME", "Vynfy")


class DevelopmentConfig(Config):
    DEBUG = True
    ALLOW_DEMO_SEED = True


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SERVER_NAME = "localhost.localdomain"
    SESSION_COOKIE_SECURE = False
    FORCE_HTTPS = False
    TRUST_PROXY_COUNT = 0
    ALLOW_DEMO_SEED = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    FORCE_HTTPS = True
    ALLOW_DEMO_SEED = False


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
