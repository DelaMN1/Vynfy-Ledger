from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, url_for

from app.auth.forms import BootstrapAdminForm
from app.auth.services import bootstrap_admin_user
from app.extensions import db, limiter
from app.setup.services import bootstrap_is_open, seed_baseline_data, setup_status, validate_bootstrap_token
from app.utils.decorators import admin_required, login_required


setup_bp = Blueprint("setup", __name__)


@setup_bp.route("/setup/initialize", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def initialize():
    if not bootstrap_is_open():
        if getattr(g, "current_user", None):
            return redirect(url_for("setup.overview"))
        return redirect(url_for("auth.login"))
    form = BootstrapAdminForm()
    if form.validate_on_submit():
        try:
            validate_bootstrap_token(form.access_token.data)
            bootstrap_admin_user(
                full_name=form.full_name.data,
                email=form.email.data,
                password=form.password.data,
            )
            seed_baseline_data()
            db.session.commit()
            flash("Initial admin created and baseline setup data seeded. Sign in to continue.", "success")
            return redirect(url_for("auth.login"))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return render_template("setup/bootstrap.html", form=form, bootstrap_token_required=setup_status()["bootstrap_token_required"])


@setup_bp.get("/setup")
@login_required
def overview():
    state = setup_status()
    return render_template("setup/index.html", setup_state=state)


@setup_bp.post("/setup/seed-baseline")
@admin_required
def seed_baseline():
    created = seed_baseline_data(actor=g.current_user)
    db.session.commit()
    created_total = sum(created.values())
    if created_total:
        flash(f"Baseline setup data created ({created_total} records).", "success")
    else:
        flash("Baseline setup data already exists.", "warning")
    return redirect(url_for("setup.overview"))
