from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from flask import Flask, abort, g, redirect, render_template, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from app.admin.routes import admin_bp
from app.auth.routes import auth_bp
from app.config import DEFAULT_CONFIG_NAME, DevelopmentConfig, config_by_name
from app.dashboard.routes import dashboard_bp
from app.extensions import csrf, db, limiter, migrate
from app.reconciliation.routes import reconciliation_bp
from app.reports.routes import reports_bp
from app.settings.routes import settings_bp
from app.transactions.routes import transactions_bp
from app.utils.auth import apply_auth_cookie, load_user_from_session
from app.utils.formatting import currency, status_badge_class, yes_no

PUBLIC_ENDPOINTS = {
    "index",
    "auth.login",
    "auth.verify_login",
    "auth.login_magic",
    "auth.register",
    "auth.verify_email",
    "auth.forgot_password",
    "auth.reset_password",
    "auth.resend_verification",
    "auth.resend_login",
    "static",
}


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    env_name = (config_name or DEFAULT_CONFIG_NAME or "development").lower()
    app.config.from_object(config_by_name.get(env_name, DevelopmentConfig))
    if app.config["TRUST_PROXY_COUNT"]:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=app.config["TRUST_PROXY_COUNT"], x_proto=app.config["TRUST_PROXY_COUNT"], x_host=app.config["TRUST_PROXY_COUNT"])

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["OUTBOX_FOLDER"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)

    register_hooks(app)
    register_filters(app)
    register_blueprints(app)
    register_errors(app)
    register_shell_context(app)
    register_cli(app)

    @app.get("/")
    def index():
        if getattr(g, "current_user", None):
            return redirect(url_for("dashboard.overview"))
        return redirect(url_for("auth.login"))

    return app


def register_hooks(app: Flask) -> None:
    def _https_url() -> str:
        parts = urlsplit(request.url)
        return urlunsplit(("https", parts.netloc, parts.path, parts.query, parts.fragment))

    def _login_redirect():
        if request.method in {"GET", "HEAD"}:
            return redirect(url_for("auth.login", next=request.full_path))
        return redirect(url_for("auth.login"))

    @app.before_request
    def enforce_security():
        load_user_from_session()
        if app.config["FORCE_HTTPS"] and not request.is_secure:
            return redirect(_https_url(), code=301)
        if request.endpoint and request.endpoint not in PUBLIC_ENDPOINTS and not getattr(g, "current_user", None):
            return _login_redirect()

    @app.after_request
    def finalize_auth(response):
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if app.config["FORCE_HTTPS"] and request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return apply_auth_cookie(response)

    @app.context_processor
    def inject_globals():
        return {"current_user": getattr(g, "current_user", None), "app_name": app.config["APP_NAME"]}


def register_filters(app: Flask) -> None:
    app.jinja_env.filters["currency"] = currency
    app.jinja_env.filters["yes_no"] = yes_no
    app.jinja_env.filters["status_badge_class"] = status_badge_class


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(reconciliation_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(admin_bp)


def register_errors(app: Flask) -> None:
    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("partials/error.html", title="Forbidden", message="You do not have access to this page."), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("partials/error.html", title="Not found", message="The requested page could not be found."), 404

    @app.errorhandler(413)
    def too_large(_error):
        return render_template("partials/error.html", title="Upload too large", message="Files must be 5MB or smaller."), 413

    @app.errorhandler(500)
    def internal_error(_error):
        db.session.rollback()
        return (
            render_template("partials/error.html", title="Server error", message="Something went wrong. Try again."),
            500,
        )


def register_shell_context(app: Flask) -> None:
    import app.models as models

    @app.shell_context_processor
    def shell_context():
        return {"db": db, "models": models}


def register_cli(app: Flask) -> None:
    from app.settings.services import seed_demo_data
    from app.utils.exceptions import ServiceError

    @app.cli.command("seed")
    def seed_command():
        try:
            seed_demo_data()
        except ServiceError as exc:
            print(exc)
            raise SystemExit(1) from exc
        print("Seed data created.")
