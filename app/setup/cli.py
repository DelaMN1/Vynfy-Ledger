from __future__ import annotations

import click
from flask.cli import with_appcontext

from app.extensions import db
from app.models import AuditLog, UserSession
from app.setup.services import (
    active_admin_count,
    account_balance_snapshots,
    recalculate_all_account_balances,
    seed_baseline_data,
    setup_status,
)


def register_cli(app) -> None:
    @app.cli.group("setup")
    def setup_group():
        """Setup and baseline data commands."""

    @setup_group.command("status")
    @with_appcontext
    def setup_status_command():
        state = setup_status()
        click.echo(f"active_admins={active_admin_count()}")
        click.echo(f"ready={state['is_ready']}")
        missing = state["missing_requirements"]
        if not missing:
            click.echo("missing=none")
            return
        for item in missing:
            click.echo(f"missing={item.label}")

    @setup_group.command("baseline")
    @with_appcontext
    def setup_baseline_command():
        created = seed_baseline_data()
        db.session.commit()
        for key, value in created.items():
            click.echo(f"{key}={value}")

    @app.cli.group("balances")
    def balances_group():
        """Balance maintenance commands."""

    @balances_group.command("check")
    @with_appcontext
    def balances_check_command():
        snapshots = account_balance_snapshots()
        drifted = 0
        for snapshot in snapshots:
            account = snapshot["account"]
            if not snapshot["is_in_sync"]:
                drifted += 1
            click.echo(
                f"{account.name}: cached={snapshot['cached_balance']} recomputed={snapshot['recomputed_balance']} drift={snapshot['drift']}"
            )
        click.echo(f"drifted_accounts={drifted}")

    @balances_group.command("recalc")
    @with_appcontext
    def balances_recalc_command():
        snapshots = recalculate_all_account_balances()
        db.session.commit()
        click.echo(f"accounts={len(snapshots)}")

    @app.cli.group("maintenance")
    def maintenance_group():
        """Operational cleanup commands."""

    @maintenance_group.command("purge-sessions")
    @with_appcontext
    def purge_sessions_command():
        from app.utils.time import utcnow

        deleted = (
            UserSession.query.filter(
                (UserSession.revoked_at.is_not(None)) | (UserSession.expires_at < utcnow())
            )
            .delete(synchronize_session=False)
        )
        db.session.commit()
        click.echo(f"deleted_sessions={deleted}")

    @maintenance_group.command("purge-audit-logs")
    @click.option("--days", default=90, show_default=True, type=int, help="Delete audit logs older than this many days.")
    @with_appcontext
    def purge_audit_logs_command(days: int):
        from datetime import timedelta

        from app.utils.time import utcnow

        cutoff = utcnow() - timedelta(days=days)
        deleted = AuditLog.query.filter(AuditLog.created_at < cutoff).delete(synchronize_session=False)
        db.session.commit()
        click.echo(f"deleted_audit_logs={deleted}")
