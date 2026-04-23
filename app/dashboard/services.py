from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func

from app.extensions import db
from app.models import Account, Budget, Category, Transaction, User
from app.transactions.services import budget_snapshot_for_budget, recent_transactions, visible_transactions_query
from app.utils.enums import (
    EXPENSE_PAYABLE_STATUSES,
    EXPENSE_SETTLED_STATUSES,
    REVENUE_RECEIVABLE_STATUSES,
    REVENUE_SETTLED_STATUSES,
    ExpenseStatus,
    TransactionType,
)
from app.utils.types import BudgetHealthRow, DashboardContext, DashboardDrilldownRow, DashboardQueueItem, MonthlyTotals


def _date_range(range_key: str) -> tuple[date, date]:
    today = date.today()
    if range_key == "quarter":
        start = today - timedelta(days=90)
    elif range_key == "year":
        start = today.replace(month=1, day=1)
    else:
        start = today.replace(day=1)
    return start, today


def _budget_rows(user: User) -> list[BudgetHealthRow]:
    rows: list[BudgetHealthRow] = []
    budget_query = Budget.query.filter_by(is_active=True)
    if not user.is_admin:
        budget_query = budget_query.filter((Budget.owner_id.is_(None)) | (Budget.owner_id == user.id))
    for budget in budget_query.order_by(Budget.name.asc()).all():
        snapshot = budget_snapshot_for_budget(budget, period_date=date.today())
        rows.append(
            {
                "name": budget.name,
                "actual": snapshot["actual"],
                "budget_amount": snapshot["budget_amount"],
                "remaining": snapshot["remaining"],
                "utilization_percent": snapshot["utilization_percent"],
                "alert_triggered": snapshot["alert_triggered"],
                "over_budget": snapshot["over_budget"],
                "category_id": budget.category_id,
                "account_id": budget.account_id,
                "owner_id": budget.owner_id,
            }
        )
    rows.sort(key=lambda item: (item["over_budget"], item["alert_triggered"], item["utilization_percent"]), reverse=True)
    return rows[:6]


def _action_queue(user: User) -> list[DashboardQueueItem]:
    query = visible_transactions_query(user).filter(
        Transaction.status.in_(
            set(EXPENSE_PAYABLE_STATUSES)
            | set(REVENUE_RECEIVABLE_STATUSES)
        )
    )
    items = query.order_by(Transaction.transaction_date.asc(), Transaction.created_at.asc()).limit(8).all()
    return [
        {
            "id": item.id,
            "title": item.title,
            "status": item.status,
            "amount": Decimal(item.amount or 0),
            "owner_name": item.submitted_by.full_name,
            "detail_url": f"/transactions/{item.id}",
        }
        for item in items
    ]


def _drilldown_rows(user: User, start_date: date, end_date: date) -> list[DashboardDrilldownRow]:
    query = (
        db.session.query(Category.name, func.coalesce(func.sum(Transaction.amount), 0), func.count(Transaction.id))
        .join(Transaction, Transaction.category_id == Category.id)
        .filter(
            Transaction.transaction_type == TransactionType.EXPENSE.value,
            Transaction.deleted_at.is_(None),
            Transaction.transaction_date >= start_date,
            Transaction.transaction_date <= end_date,
        )
    )
    if not user.is_admin:
        query = query.filter(Transaction.submitted_by_id == user.id)
    rows = query.group_by(Category.name).order_by(func.sum(Transaction.amount).desc()).limit(5).all()
    return [{"label": label, "total": Decimal(total or 0), "transaction_count": int(count or 0)} for label, total, count in rows]


def dashboard_context(user: User, *, range_key: str = "month") -> DashboardContext:
    start_date, end_date = _date_range(range_key)
    records = visible_transactions_query(user).filter(Transaction.transaction_date >= start_date, Transaction.transaction_date <= end_date).all()
    revenue_total = sum(
        Decimal(item.received_amount or 0)
        for item in records
        if item.transaction_type == TransactionType.REVENUE.value and item.status in REVENUE_SETTLED_STATUSES
    )
    expense_total = sum(
        Decimal(item.amount or 0)
        for item in records
        if item.transaction_type == TransactionType.EXPENSE.value and item.status in EXPENSE_SETTLED_STATUSES
    )
    receivables = sum(
        Decimal(item.expected_amount or item.amount or 0) - Decimal(item.received_amount or 0)
        for item in visible_transactions_query(user, TransactionType.REVENUE.value).all()
        if item.status in REVENUE_RECEIVABLE_STATUSES
    )
    payables = sum(
        Decimal(item.amount or 0)
        for item in visible_transactions_query(user, TransactionType.EXPENSE.value).all()
        if item.status in EXPENSE_PAYABLE_STATUSES
    )
    overdue_items = (
        visible_transactions_query(user)
        .filter(Transaction.due_date.is_not(None), Transaction.due_date < date.today())
        .filter(Transaction.status.notin_(set(EXPENSE_SETTLED_STATUSES) | set(REVENUE_SETTLED_STATUSES)))
        .count()
    )
    pending_approvals = (
        visible_transactions_query(user, TransactionType.EXPENSE.value).filter(Transaction.status == ExpenseStatus.SUBMITTED.value).count()
        if user.is_admin
        else 0
    )
    top_expense_query = (
        db.session.query(Category.name, func.coalesce(func.sum(Transaction.amount), 0))
        .join(Transaction, Transaction.category_id == Category.id)
        .filter(
            Transaction.transaction_type == TransactionType.EXPENSE.value,
            Transaction.deleted_at.is_(None),
            Transaction.transaction_date >= start_date,
            Transaction.transaction_date <= end_date,
        )
    )
    if not user.is_admin:
        top_expense_query = top_expense_query.filter(Transaction.submitted_by_id == user.id)
    top_expenses = top_expense_query.group_by(Category.name).order_by(func.sum(Transaction.amount).desc()).limit(5).all()
    monthly: defaultdict[str, MonthlyTotals] = defaultdict(lambda: {"revenue": Decimal("0"), "expense": Decimal("0")})
    for item in visible_transactions_query(user).filter(Transaction.transaction_date >= date.today() - timedelta(days=180)).all():
        key = item.transaction_date.strftime("%b %Y")
        if item.transaction_type == TransactionType.REVENUE.value:
            monthly[key]["revenue"] += Decimal(item.received_amount or 0)
        elif item.status in EXPENSE_SETTLED_STATUSES:
            monthly[key]["expense"] += Decimal(item.amount or 0)

    budget_rows = _budget_rows(user)
    return {
        "range_key": range_key,
        "summary": {
            "revenue_this_month": revenue_total,
            "expenses_this_month": expense_total,
            "net_cash_flow": revenue_total - expense_total,
            "cash_snapshot": sum(Decimal(item.current_balance_cached or 0) for item in Account.query.filter_by(is_active=True).all()),
            "outstanding_receivables": receivables,
            "outstanding_payables": payables,
            "pending_approvals": pending_approvals,
            "overdue_items": overdue_items,
            "budget_alerts": sum(1 for item in budget_rows if item["alert_triggered"]),
            "unreconciled_transactions": visible_transactions_query(user).filter(Transaction.is_reconciled.is_(False)).count(),
        },
        "recent_transactions": recent_transactions(user),
        "expense_chart": {"labels": [row[0] for row in top_expenses], "values": [float(row[1]) for row in top_expenses]},
        "trend_chart": {
            "labels": list(monthly.keys()),
            "revenue": [float(item["revenue"]) for item in monthly.values()],
            "expense": [float(item["expense"]) for item in monthly.values()],
        },
        "budget_rows": budget_rows,
        "action_queue": _action_queue(user),
        "drilldown_rows": _drilldown_rows(user, start_date, end_date),
    }
