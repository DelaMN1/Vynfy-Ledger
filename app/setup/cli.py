from __future__ import annotations

import click
from flask.cli import with_appcontext

from app.extensions import db
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
