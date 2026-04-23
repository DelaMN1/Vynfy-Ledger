from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import sqlalchemy as sa

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


ADMIN_EMAIL = "maxdela38@gmail.com"
MOCK_EMAIL_PATTERNS = (
    re.compile(r"@vynfy\.internal$", re.IGNORECASE),
    re.compile(r"@example\.(com|org|net)$", re.IGNORECASE),
    re.compile(r"(^|[._+-])(test|demo|sample|fake)([._+-]|@|$)", re.IGNORECASE),
)


@dataclass(frozen=True)
class TablePlan:
    name: str
    model_name: str
    filter_fn: str | None = None


TABLE_PLANS = (
    TablePlan("users", "User", "filter_users"),
    TablePlan("categories", "Category"),
    TablePlan("accounts", "Account"),
    TablePlan("payment_methods", "PaymentMethod"),
    TablePlan("budgets", "Budget"),
    TablePlan("spend_policies", "SpendPolicy"),
    TablePlan("accounting_mappings", "AccountingMapping"),
    TablePlan("transactions", "Transaction", "filter_transactions"),
    TablePlan("attachments", "Attachment", "filter_attachments"),
    TablePlan("transaction_comments", "TransactionComment", "filter_transaction_comments"),
    TablePlan("transaction_status_history", "TransactionStatusHistory", "filter_transaction_status_history"),
    TablePlan("audit_logs", "AuditLog", "filter_audit_logs"),
    TablePlan("reconciliation_sessions", "ReconciliationSession", "filter_reconciliation_sessions"),
)

AUTH_TABLE_PLANS = (
    TablePlan("user_sessions", "UserSession", "filter_user_sessions"),
)


class MigrationAbort(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import local SQLite data into PostgreSQL.")
    parser.add_argument("--source", default=str(Path("instance") / "vynfy_ledger.db"))
    parser.add_argument("--target-url", required=True)
    parser.add_argument("--preserve-email", action="append", default=[])
    parser.add_argument("--remove-email", action="append", default=[])
    parser.add_argument("--include-auth-tables", action="store_true")
    parser.add_argument("--allow-ambiguous", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_path = Path(args.source)
    if not source_path.exists():
        raise SystemExit(f"SQLite source database not found: {source_path}")

    os.environ["DATABASE_URL"] = args.target_url
    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("FLASK_ENV", "development")

    from app import create_app
    from app.extensions import db
    import app.models as models

    app = create_app("development")
    with app.app_context():
        context = MigrationContext(
            sqlite_path=source_path,
            db=db,
            models=models,
            include_auth_tables=args.include_auth_tables,
            preserve_emails={ADMIN_EMAIL, *args.preserve_email},
            remove_emails=set(args.remove_email),
            allow_ambiguous=args.allow_ambiguous,
            dry_run=args.dry_run,
        )
        context.run()
    return 0


class MigrationContext:
    def __init__(
        self,
        *,
        sqlite_path: Path,
        db: Any,
        models: Any,
        include_auth_tables: bool,
        preserve_emails: set[str],
        remove_emails: set[str],
        allow_ambiguous: bool,
        dry_run: bool,
    ) -> None:
        self.sqlite_path = sqlite_path
        self.db = db
        self.models = models
        self.include_auth_tables = include_auth_tables
        self.preserve_emails = {email.lower() for email in preserve_emails}
        self.remove_emails = {email.lower() for email in remove_emails}
        self.allow_ambiguous = allow_ambiguous
        self.dry_run = dry_run

        self.source = sqlite3.connect(self.sqlite_path)
        self.source.row_factory = sqlite3.Row
        self.source_tables = self._load_source_rows()
        self.cleanup = self._analyze_cleanup()
        self.imported_counts: dict[str, int] = {}

    def run(self) -> None:
        self._print_source_summary()
        self._print_cleanup_summary()
        self._enforce_cleanup_guards()
        self._ensure_target_is_empty()

        if self.dry_run:
            print("Dry run complete. No PostgreSQL rows were written.")
            return

        try:
            for plan in self._plans():
                self._import_table(plan)
            self.db.session.commit()
        except Exception:
            self.db.session.rollback()
            raise

        for plan in self._plans():
            self._reset_sequence(plan.name)

        print("Import complete.")
        for table_name, count in self.imported_counts.items():
            print(f"  imported {table_name}: {count}")

    def _plans(self) -> tuple[TablePlan, ...]:
        if self.include_auth_tables:
            return TABLE_PLANS + AUTH_TABLE_PLANS
        return TABLE_PLANS

    def _load_source_rows(self) -> dict[str, list[dict[str, Any]]]:
        tables = {plan.name for plan in self._plans()}
        rows: dict[str, list[dict[str, Any]]] = {}
        cur = self.source.cursor()
        for table_name in tables:
            cur.execute(f"SELECT * FROM {table_name} ORDER BY id")
            rows[table_name] = [dict(row) for row in cur.fetchall()]
        return rows

    def _analyze_cleanup(self) -> dict[str, Any]:
        users = self.source_tables["users"]
        preserved_user_ids: set[int] = set()
        removed_user_ids: set[int] = set()
        ambiguous_users: list[dict[str, Any]] = []
        removed_users: list[dict[str, Any]] = []

        for user in users:
            email = (user.get("email") or "").strip().lower()
            if email in self.preserve_emails:
                preserved_user_ids.add(user["id"])
                continue
            if email in self.remove_emails or self._is_obvious_mock_email(email):
                removed_user_ids.add(user["id"])
                removed_users.append(user)
                continue
            preserved_user_ids.add(user["id"])
            ambiguous_users.append(user)

        kept_transaction_ids: set[int] = set()
        removed_transaction_ids: set[int] = set()
        cleared_transaction_approvers = 0
        for row in self.source_tables["transactions"]:
            submitted_by_id = row.get("submitted_by_id")
            if submitted_by_id in removed_user_ids:
                removed_transaction_ids.add(row["id"])
                continue
            kept_transaction_ids.add(row["id"])
            if row.get("approved_by_id") in removed_user_ids:
                cleared_transaction_approvers += 1

        kept_attachment_ids: set[int] = set()
        removed_attachment_ids: set[int] = set()
        for row in self.source_tables["attachments"]:
            if row.get("transaction_id") not in kept_transaction_ids or row.get("uploaded_by_id") in removed_user_ids:
                removed_attachment_ids.add(row["id"])
                continue
            kept_attachment_ids.add(row["id"])

        kept_comment_ids: set[int] = set()
        for row in self.source_tables["transaction_comments"]:
            if row.get("transaction_id") in kept_transaction_ids and row.get("user_id") not in removed_user_ids:
                kept_comment_ids.add(row["id"])

        kept_status_history_ids: set[int] = set()
        for row in self.source_tables["transaction_status_history"]:
            changed_by_id = row.get("changed_by_id")
            if row.get("transaction_id") in kept_transaction_ids and changed_by_id not in removed_user_ids:
                kept_status_history_ids.add(row["id"])

        kept_session_ids: set[int] = set()
        if self.include_auth_tables:
            kept_session_ids = {row["id"] for row in self.source_tables["user_sessions"] if row.get("user_id") not in removed_user_ids}

        removed_audit_log_ids: set[int] = set()
        for row in self.source_tables["audit_logs"]:
            if row.get("user_id") in removed_user_ids:
                removed_audit_log_ids.add(row["id"])
                continue
            entity_type = (row.get("entity_type") or "").lower()
            entity_id = row.get("entity_id")
            if entity_type == "user" and entity_id in removed_user_ids:
                removed_audit_log_ids.add(row["id"])
            elif entity_type == "transaction" and entity_id in removed_transaction_ids:
                removed_audit_log_ids.add(row["id"])
            elif entity_type == "attachment" and entity_id in removed_attachment_ids:
                removed_audit_log_ids.add(row["id"])

        return {
            "preserved_user_ids": preserved_user_ids,
            "removed_user_ids": removed_user_ids,
            "ambiguous_users": ambiguous_users,
            "removed_users": removed_users,
            "kept_transaction_ids": kept_transaction_ids,
            "removed_transaction_ids": removed_transaction_ids,
            "kept_attachment_ids": kept_attachment_ids,
            "removed_attachment_ids": removed_attachment_ids,
            "kept_comment_ids": kept_comment_ids,
            "kept_status_history_ids": kept_status_history_ids,
            "kept_session_ids": kept_session_ids,
            "removed_audit_log_ids": removed_audit_log_ids,
            "cleared_transaction_approvers": cleared_transaction_approvers,
        }

    def _print_source_summary(self) -> None:
        print(f"Source SQLite: {self.sqlite_path}")
        for plan in self._plans():
            print(f"  source {plan.name}: {len(self.source_tables[plan.name])}")

    def _print_cleanup_summary(self) -> None:
        print("Cleanup analysis:")
        print(f"  preserve admin email: {ADMIN_EMAIL}")
        print(f"  remove obvious mock users: {len(self.cleanup['removed_users'])}")
        for user in self.cleanup["removed_users"]:
            print(f"    remove user {user['id']}: {user['email']} ({user['full_name']})")
        print(f"  ambiguous users requiring review: {len(self.cleanup['ambiguous_users'])}")
        for user in self.cleanup["ambiguous_users"]:
            print(f"    ambiguous user {user['id']}: {user['email']} ({user['full_name']})")
        print(f"  transactions removed with mock submitters: {len(self.cleanup['removed_transaction_ids'])}")
        print(f"  transaction approvers cleared because approver is removed: {self.cleanup['cleared_transaction_approvers']}")
        print(f"  attachments removed with deleted rows: {len(self.cleanup['removed_attachment_ids'])}")
        print(f"  audit logs removed with deleted users/entities: {len(self.cleanup['removed_audit_log_ids'])}")
        if not self.include_auth_tables:
            print("  auth tables: skipped by default")

    def _enforce_cleanup_guards(self) -> None:
        if self.cleanup["ambiguous_users"] and not self.allow_ambiguous:
            raise MigrationAbort(
                "Cleanup has ambiguous users. Resolve them with --preserve-email/--remove-email, "
                "or rerun with --allow-ambiguous to preserve them."
            )
        if ADMIN_EMAIL not in self.preserve_emails:
            raise MigrationAbort(f"{ADMIN_EMAIL} must be preserved.")

    def _ensure_target_is_empty(self) -> None:
        connection = self.db.session.connection()
        for plan in self._plans():
            table = getattr(self.models, plan.model_name).__table__
            count = connection.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()
            if count:
                raise MigrationAbort(f"Target PostgreSQL table '{plan.name}' is not empty ({count} rows).")

    def _import_table(self, plan: TablePlan) -> None:
        rows = list(self.source_tables[plan.name])
        if plan.filter_fn:
            rows = getattr(self, plan.filter_fn)(rows)

        table = getattr(self.models, plan.model_name).__table__
        payload = [self._coerce_row(table, row) for row in rows]
        if payload:
            self.db.session.execute(table.insert(), payload)
        self.imported_counts[plan.name] = len(payload)

    def filter_users(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [row for row in rows if row["id"] in self.cleanup["preserved_user_ids"]]

    def filter_transactions(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered = []
        for row in rows:
            if row["id"] not in self.cleanup["kept_transaction_ids"]:
                continue
            copy = dict(row)
            if copy.get("approved_by_id") in self.cleanup["removed_user_ids"]:
                copy["approved_by_id"] = None
            filtered.append(copy)
        return filtered

    def filter_attachments(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered = []
        kept_attachment_ids = self.cleanup["kept_attachment_ids"]
        for row in rows:
            if row["id"] not in kept_attachment_ids:
                continue
            copy = dict(row)
            duplicate_id = copy.get("duplicate_of_attachment_id")
            if duplicate_id and duplicate_id not in kept_attachment_ids:
                copy["duplicate_of_attachment_id"] = None
            filtered.append(copy)
        return filtered

    def filter_transaction_comments(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        kept_ids = self.cleanup["kept_comment_ids"]
        return [row for row in rows if row["id"] in kept_ids]

    def filter_transaction_status_history(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        kept_ids = self.cleanup["kept_status_history_ids"]
        return [row for row in rows if row["id"] in kept_ids]

    def filter_audit_logs(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        removed_ids = self.cleanup["removed_audit_log_ids"]
        filtered = []
        for row in rows:
            if row["id"] in removed_ids:
                continue
            copy = dict(row)
            if copy.get("user_id") in self.cleanup["removed_user_ids"]:
                copy["user_id"] = None
            filtered.append(copy)
        return filtered

    def filter_reconciliation_sessions(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        kept_transaction_ids = self.cleanup["kept_transaction_ids"]
        preserved_user_ids = self.cleanup["preserved_user_ids"]
        filtered = []
        for row in rows:
            copy = dict(row)
            selected_ids = copy.get("selected_transaction_ids") or []
            if isinstance(selected_ids, str):
                selected_ids = json.loads(selected_ids)
            cleaned_ids = [item for item in selected_ids if item in kept_transaction_ids]
            copy["selected_transaction_ids"] = cleaned_ids
            if copy.get("completed_by_id") not in preserved_user_ids:
                copy["completed_by_id"] = None
            filtered.append(copy)
        return filtered

    def filter_user_sessions(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        kept_ids = self.cleanup["kept_session_ids"]
        return [row for row in rows if row["id"] in kept_ids]

    def _coerce_row(self, table: sa.Table, row: dict[str, Any]) -> dict[str, Any]:
        coerced: dict[str, Any] = {}
        for column in table.columns:
            if column.name not in row:
                continue
            coerced[column.name] = self._coerce_value(column.type, row[column.name])
        return coerced

    def _coerce_value(self, column_type: sa.types.TypeEngine[Any], value: Any) -> Any:
        if value is None:
            return None
        if isinstance(column_type, sa.DateTime):
            if isinstance(value, datetime):
                return value
            return datetime.fromisoformat(str(value))
        if isinstance(column_type, sa.Date):
            if isinstance(value, date) and not isinstance(value, datetime):
                return value
            return date.fromisoformat(str(value))
        if isinstance(column_type, sa.Numeric):
            return Decimal(str(value))
        if isinstance(column_type, sa.Boolean):
            return bool(value)
        if isinstance(column_type, sa.JSON):
            if isinstance(value, (dict, list)):
                return value
            return json.loads(value)
        if isinstance(column_type, sa.Integer):
            return int(value)
        return value

    def _reset_sequence(self, table_name: str) -> None:
        table = sa.sql.quoted_name(table_name, quote=False)
        query = sa.text(
            f"""
            SELECT setval(
                pg_get_serial_sequence('{table}', 'id'),
                COALESCE((SELECT MAX(id) FROM {table}), 1),
                EXISTS (SELECT 1 FROM {table})
            )
            """
        )
        self.db.session.execute(query)
        self.db.session.commit()

    @staticmethod
    def _is_obvious_mock_email(email: str) -> bool:
        return any(pattern.search(email) for pattern in MOCK_EMAIL_PATTERNS)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MigrationAbort as exc:
        print(f"Migration aborted: {exc}")
        raise SystemExit(1) from exc
