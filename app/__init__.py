from __future__ import annotations

from pathlib import Path

from flask import Flask, abort, g, redirect, render_template, request, url_for

from app.admin.routes import admin_bp
from app.auth.routes import auth_bp
from app.config import DevelopmentConfig, config_by_name
from app.dashboard.routes import dashboard_bp
from app.extensions import csrf, db, limiter, migrate
from app.reconciliation.routes import reconciliation_bp
from app.reports.routes import reports_bp
from app.settings.routes import settings_bp
from app.transactions.routes import transactions_bp
from app.utils.auth import apply_auth_cookie, load_user_from_session
from app.utils.formatting import currency, yes_no


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    env_name = config_name or "development"
    app.config.from_object(config_by_name.get(env_name, DevelopmentConfig))

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
    @app.before_request
    def enforce_security():
        if app.config["FORCE_HTTPS"] and request.headers.get("X-Forwarded-Proto", "http") != "https":
            return redirect(request.url.replace("http://", "https://", 1), code=301)
        load_user_from_session()

    @app.after_request
    def finalize_auth(response):
        return apply_auth_cookie(response)

    @app.context_processor
    def inject_globals():
        return {"current_user": getattr(g, "current_user", None), "app_name": app.config["APP_NAME"]}


def register_filters(app: Flask) -> None:
    app.jinja_env.filters["currency"] = currency
    app.jinja_env.filters["yes_no"] = yes_no


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
    from app import models

    @app.shell_context_processor
    def shell_context():
        return {"db": db, "models": models}


def register_cli(app: Flask) -> None:
    from app.settings.services import seed_demo_data

    @app.cli.command("seed")
    def seed_command():
        seed_demo_data()
        print("Seed data created.")
