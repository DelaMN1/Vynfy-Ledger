from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func

from app.extensions import db
from app.models import Account, Category, Transaction, User
from app.transactions.services import recent_transactions, visible_transactions_query
from app.utils.enums import ExpenseStatus, RevenueStatus, TransactionType


def _date_range(range_key: str) -> tuple[date, date]:
    today = date.today()
    if range_key == "quarter":
        start = today - timedelta(days=90)
    elif range_key == "year":
        start = today.replace(month=1, day=1)
    else:
        start = today.replace(day=1)
    return start, today


def dashboard_context(user: User, *, range_key: str = "month") -> dict:
    start_date, end_date = _date_range(range_key)
    records = (
        visible_transactions_query(user)
        .filter(Transaction.transaction_date >= start_date, Transaction.transaction_date <= end_date)
        .all()
    )
    revenue_total = sum(
        Decimal(item.received_amount or 0)
        for item in records
        if item.transaction_type == TransactionType.REVENUE.value
        and item.status in {RevenueStatus.PARTIALLY_RECEIVED.value, RevenueStatus.RECEIVED.value}
    )
    expense_total = sum(
        Decimal(item.amount or 0)
        for item in records
        if item.transaction_type == TransactionType.EXPENSE.value
        and item.status in {ExpenseStatus.PAID.value, ExpenseStatus.REIMBURSED.value}
    )
    receivables = sum(
        Decimal(item.expected_amount or item.amount or 0) - Decimal(item.received_amount or 0)
        for item in visible_transactions_query(user, TransactionType.REVENUE.value).all()
        if item.status in {RevenueStatus.EXPECTED.value, RevenueStatus.PARTIALLY_RECEIVED.value, RevenueStatus.OVERDUE.value}
    )
    payables = sum(
        Decimal(item.amount or 0)
        for item in visible_transactions_query(user, TransactionType.EXPENSE.value).all()
        if item.status in {ExpenseStatus.SUBMITTED.value, ExpenseStatus.APPROVED.value, ExpenseStatus.OVERDUE.value}
    )
    overdue_items = (
        visible_transactions_query(user)
        .filter(Transaction.due_date.is_not(None), Transaction.due_date < date.today())
        .filter(Transaction.status.notin_([ExpenseStatus.PAID.value, RevenueStatus.RECEIVED.value]))
        .count()
    )
    pending_approvals = (
        visible_transactions_query(user, TransactionType.EXPENSE.value)
        .filter(Transaction.status == ExpenseStatus.SUBMITTED.value)
        .count()
        if user.is_admin
        else 0
    )
    top_expenses = (
        db.session.query(Category.name, func.coalesce(func.sum(Transaction.amount), 0))
        .join(Transaction, Transaction.category_id == Category.id)
        .filter(
            Transaction.transaction_type == TransactionType.EXPENSE.value,
            Transaction.deleted_at.is_(None),
            Transaction.transaction_date >= start_date,
            Transaction.transaction_date <= end_date,
        )
        .group_by(Category.name)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(5)
        .all()
    )
    monthly = defaultdict(lambda: {"revenue": Decimal("0"), "expense": Decimal("0")})
    for item in visible_transactions_query(user).filter(Transaction.transaction_date >= date.today() - timedelta(days=180)).all():
        key = item.transaction_date.strftime("%b %Y")
        if item.transaction_type == TransactionType.REVENUE.value:
            monthly[key]["revenue"] += Decimal(item.received_amount or 0)
        elif item.status in {ExpenseStatus.PAID.value, ExpenseStatus.REIMBURSED.value}:
            monthly[key]["expense"] += Decimal(item.amount or 0)

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
        },
        "recent_transactions": recent_transactions(user),
        "expense_chart": {"labels": [row[0] for row in top_expenses], "values": [float(row[1]) for row in top_expenses]},
        "trend_chart": {
            "labels": list(monthly.keys()),
            "revenue": [float(item["revenue"]) for item in monthly.values()],
            "expense": [float(item["expense"]) for item in monthly.values()],
        },
    }
