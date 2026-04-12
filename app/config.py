from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"


class Config:
    APP_NAME = "Vynfy Ledger"
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-with-32-plus-random-chars")
    SECURITY_PASSWORD_SALT = os.getenv(
        "SECURITY_PASSWORD_SALT", "change-me-in-production-with-another-32-plus-secret"
    )
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{(INSTANCE_DIR / 'vynfy_ledger.db').as_posix()}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_TIME_LIMIT = 3600
    REMEMBER_COOKIE_HTTPONLY = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("FLASK_ENV") == "production"
    PREFERRED_URL_SCHEME = "https" if os.getenv("FLASK_ENV") == "production" else "http"
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    UPLOAD_FOLDER = str(INSTANCE_DIR / "uploads")
    OUTBOX_FOLDER = str(INSTANCE_DIR / "outbox")
    ACCESS_SESSION_TTL = timedelta(minutes=int(os.getenv("ACCESS_SESSION_MINUTES", "45")))
    SESSION_ROTATE_AFTER = timedelta(minutes=int(os.getenv("SESSION_ROTATE_AFTER_MINUTES", "15")))
    LOGIN_LOCKOUT_MINUTES = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))
    MAX_FAILED_LOGINS = int(os.getenv("MAX_FAILED_LOGINS", "5"))
    PASSWORD_MIN_LENGTH = 12
    REGISTRATION_ENABLED = os.getenv("REGISTRATION_ENABLED", "true").lower() == "true"
    MAIL_FROM = os.getenv("MAIL_FROM", "no-reply@vynfy.internal")
    SMTP_HOST = os.getenv("SMTP_HOST")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    FORCE_HTTPS = os.getenv("FORCE_HTTPS", "false").lower() == "true"
    RATELIMIT_HEADERS_ENABLED = True
    RATELIMIT_DEFAULT = "300 per hour"
    DEFAULT_PAGE_SIZE = 10
    DASHBOARD_MONTHS = 6
    COMPANY_NAME = os.getenv("COMPANY_NAME", "Vynfy")


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SERVER_NAME = "localhost.localdomain"
    SESSION_COOKIE_SECURE = False
    FORCE_HTTPS = False


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    FORCE_HTTPS = True


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
