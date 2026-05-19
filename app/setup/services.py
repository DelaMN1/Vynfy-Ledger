from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from flask import current_app, g, has_request_context
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import Account, Category, PaymentMethod, Transaction, User
from app.utils.audit import record_audit
from app.utils.enums import (
    AccountType,
    CategoryType,
    EXPENSE_SETTLED_STATUSES,
    REVENUE_SETTLED_STATUSES,
    TransactionType,
)
from app.utils.exceptions import ServiceError


@dataclass(frozen=True)
class SetupRequirement:
    key: str
    label: str
    description: str
    endpoint: str | None
    admin_only: bool = True


BASELINE_CATEGORIES = (
    ("Sales", CategoryType.REVENUE.value, "#15803d", "Primary revenue receipts."),
    ("Services", CategoryType.REVENUE.value, "#0f766e", "Service and consulting income."),
    ("Operations", CategoryType.EXPENSE.value, "#dc2626", "General operating expenses."),
    ("Marketing", CategoryType.EXPENSE.value, "#ea580c", "Campaign and growth spend."),
    ("Travel", CategoryType.EXPENSE.value, "#2563eb", "Travel and field operations."),
)
BASELINE_ACCOUNTS = (
    ("Main Bank", AccountType.BANK.value, Decimal("0.00"), "GHS"),
)
BASELINE_PAYMENT_METHODS = (
    "Bank Transfer",
    "Cash",
    "Mobile Money",
)
SETUP_REQUIREMENTS = (
    SetupRequirement(
        key="active_admin",
        label="First admin account",
        description="Create at least one active admin who can manage users and setup data.",
        endpoint=None,
        admin_only=False,
    ),
    SetupRequirement(
        key="revenue_category",
        label="Revenue category",
        description="Create at least one active revenue category for simplified revenue entry.",
        endpoint="settings.categories",
    ),
    SetupRequirement(
        key="expense_category",
        label="Expense category",
        description="Create at least one active expense category for simplified expense entry.",
        endpoint="settings.categories",
    ),
    SetupRequirement(
        key="account",
        label="Ledger account",
        description="Create at least one active account to post cash movement and balances.",
        endpoint="settings.accounts",
    ),
    SetupRequirement(
        key="payment_method",
        label="Payment method",
        description="Create at least one payment method so operators can classify how money moved.",
        endpoint="settings.payment_methods",
    ),
)


def active_admin_count() -> int:
    return int(User.query.filter_by(role="admin", is_active=True).count())


def bootstrap_token_required() -> bool:
    return bool(current_app.config.get("BOOTSTRAP_SETUP_TOKEN"))


def bootstrap_is_allowed() -> bool:
    if not current_app.config.get("BOOTSTRAP_SETUP_ENABLED", False):
        return False
    if current_app.config.get("APP_ENV") == "production" and not current_app.config.get("BOOTSTRAP_SETUP_TOKEN"):
        return False
    return True


def bootstrap_is_open() -> bool:
    return bootstrap_is_allowed() and active_admin_count() == 0


def bootstrap_status() -> dict[str, object]:
    admin_count = active_admin_count()
    return {
        "bootstrap_open": bootstrap_is_allowed() and admin_count == 0,
        "bootstrap_token_required": bootstrap_token_required(),
        "active_admin": admin_count > 0,
    }


def validate_bootstrap_token(token: str | None) -> None:
    expected = current_app.config.get("BOOTSTRAP_SETUP_TOKEN")
    if not expected:
        return
    if (token or "").strip() != expected:
        raise ServiceError("Bootstrap access token is invalid.")


def _has_active_category(category_type: str) -> bool:
    return Category.query.filter_by(type=category_type, is_active=True).first() is not None


def _compute_setup_status() -> dict[str, object]:
    bootstrap = bootstrap_status()
    checks = {
        "active_admin": bool(bootstrap["active_admin"]),
        "revenue_category": _has_active_category(CategoryType.REVENUE.value),
        "expense_category": _has_active_category(CategoryType.EXPENSE.value),
        "account": Account.query.filter_by(is_active=True).first() is not None,
        "payment_method": PaymentMethod.query.filter_by(is_active=True).first() is not None,
    }
    missing = [item for item in SETUP_REQUIREMENTS if not checks[item.key]]
    return {
        "bootstrap_open": bootstrap["bootstrap_open"],
        "bootstrap_token_required": bootstrap["bootstrap_token_required"],
        "checks": checks,
        "missing_requirements": missing,
        "is_ready": not missing,
        "is_ready_for_basic_entry": all(checks[key] for key in ("revenue_category", "expense_category", "account", "payment_method")),
    }


def setup_status() -> dict[str, object]:
    if has_request_context():
        cached = getattr(g, "_setup_status", None)
        if cached is None:
            cached = _compute_setup_status()
            g._setup_status = cached
        return cached
    return _compute_setup_status()


def setup_state_or_none() -> dict[str, object] | None:
    try:
        return setup_status()
    except SQLAlchemyError:
        return None


def bootstrap_state_or_none() -> dict[str, object] | None:
    try:
        return bootstrap_status()
    except SQLAlchemyError:
        return None


def missing_setup_message(*, transaction_type: str | None = None) -> str:
    state = setup_status()
    if state["is_ready"]:
        return ""
    labels = ", ".join(item.label.lower() for item in state["missing_requirements"])
    if transaction_type == TransactionType.REVENUE.value:
        return f"Revenue entry is unavailable until setup is complete: {labels}."
    if transaction_type == TransactionType.EXPENSE.value:
        return f"Expense entry is unavailable until setup is complete: {labels}."
    return f"Setup is incomplete: {labels}."


def ensure_entry_setup(transaction_type: str | None = None) -> None:
    state = setup_status()
    required_keys = {"account", "payment_method"}
    if transaction_type == TransactionType.REVENUE.value:
        required_keys.add("revenue_category")
    elif transaction_type == TransactionType.EXPENSE.value:
        required_keys.add("expense_category")
    else:
        required_keys.update({"revenue_category", "expense_category"})
    missing = [item for item in state["missing_requirements"] if item.key in required_keys]
    if missing:
        labels = ", ".join(item.label.lower() for item in missing)
        raise ServiceError(f"Complete setup before continuing: {labels}.")


def seed_baseline_data(*, actor: User | None = None) -> dict[str, int]:
    created = {
        "categories": 0,
        "accounts": 0,
        "payment_methods": 0,
    }
    for name, category_type, color, description in BASELINE_CATEGORIES:
        existing = Category.query.filter(func.lower(Category.name) == name.lower()).first()
        if existing:
            if not existing.is_active:
                existing.is_active = True
            continue
        db.session.add(Category(name=name, type=category_type, color=color, description=description))
        created["categories"] += 1
    for name, account_type, opening_balance, currency_code in BASELINE_ACCOUNTS:
        existing = Account.query.filter(func.lower(Account.name) == name.lower()).first()
        if existing:
            if not existing.is_active:
                existing.is_active = True
            continue
        db.session.add(
            Account(
                name=name,
                type=account_type,
                opening_balance=opening_balance,
                current_balance_cached=opening_balance,
                currency_code=currency_code,
            )
        )
        created["accounts"] += 1
    for name in BASELINE_PAYMENT_METHODS:
        existing = PaymentMethod.query.filter(func.lower(PaymentMethod.name) == name.lower()).first()
        if existing:
            if not existing.is_active:
                existing.is_active = True
            continue
        db.session.add(PaymentMethod(name=name))
        created["payment_methods"] += 1
    record_audit(
        user_id=actor.id if actor else None,
        entity_type="setup",
        entity_id=None,
        action="seed_baseline",
        new_values=created,
    )
    return created


def recomputed_account_balance(account: Account) -> Decimal:
    revenue_total = (
        db.session.query(func.coalesce(func.sum(Transaction.received_amount), 0))
        .filter(
            Transaction.account_id == account.id,
            Transaction.transaction_type == TransactionType.REVENUE.value,
            Transaction.status.in_(REVENUE_SETTLED_STATUSES),
            Transaction.deleted_at.is_(None),
        )
        .scalar()
    )
    expense_total = (
        db.session.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.account_id == account.id,
            Transaction.transaction_type == TransactionType.EXPENSE.value,
            Transaction.status.in_(EXPENSE_SETTLED_STATUSES),
            Transaction.deleted_at.is_(None),
        )
        .scalar()
    )
    return Decimal(account.opening_balance or 0) + Decimal(revenue_total or 0) - Decimal(expense_total or 0)


def sync_account_balance(account_id: int) -> Decimal | None:
    account = db.session.get(Account, account_id)
    if not account:
        return None
    balance = recomputed_account_balance(account)
    account.current_balance_cached = balance
    return balance


def account_balance_snapshot(account: Account) -> dict[str, object]:
    recomputed = recomputed_account_balance(account)
    cached = Decimal(account.current_balance_cached or 0)
    drift = recomputed - cached
    return {
        "account": account,
        "cached_balance": cached,
        "recomputed_balance": recomputed,
        "drift": drift,
        "is_in_sync": drift == 0,
    }


def account_balance_snapshots() -> list[dict[str, object]]:
    accounts = Account.query.order_by(Account.name.asc()).all()
    revenue_totals = dict(
        db.session.query(Transaction.account_id, func.coalesce(func.sum(Transaction.received_amount), 0))
        .filter(
            Transaction.transaction_type == TransactionType.REVENUE.value,
            Transaction.status.in_(REVENUE_SETTLED_STATUSES),
            Transaction.deleted_at.is_(None),
        )
        .group_by(Transaction.account_id)
        .all()
    )
    expense_totals = dict(
        db.session.query(Transaction.account_id, func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.transaction_type == TransactionType.EXPENSE.value,
            Transaction.status.in_(EXPENSE_SETTLED_STATUSES),
            Transaction.deleted_at.is_(None),
        )
        .group_by(Transaction.account_id)
        .all()
    )
    snapshots: list[dict[str, object]] = []
    for account in accounts:
        recomputed = Decimal(account.opening_balance or 0) + Decimal(revenue_totals.get(account.id, 0) or 0) - Decimal(expense_totals.get(account.id, 0) or 0)
        cached = Decimal(account.current_balance_cached or 0)
        drift = recomputed - cached
        snapshots.append(
            {
                "account": account,
                "cached_balance": cached,
                "recomputed_balance": recomputed,
                "drift": drift,
                "is_in_sync": drift == 0,
            }
        )
    return snapshots


def recalculate_all_account_balances(*, actor: User | None = None) -> list[dict[str, object]]:
    snapshots = account_balance_snapshots()
    for snapshot in snapshots:
        account = snapshot["account"]
        assert isinstance(account, Account)
        account.current_balance_cached = snapshot["recomputed_balance"]
    record_audit(
        user_id=actor.id if actor else None,
        entity_type="account",
        entity_id=None,
        action="recalculate_balances",
        new_values={"accounts": len(snapshots)},
    )
    return snapshots
