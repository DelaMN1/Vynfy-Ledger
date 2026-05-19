from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import case, func

from app.extensions import db
from app.models import Account, Transaction, User
from app.transactions.services import recent_transactions, visible_transactions_query
from app.utils.enums import EXPENSE_SETTLED_STATUSES, REVENUE_SETTLED_STATUSES, TransactionType


def _month_bounds(today: date) -> tuple[date, date]:
    start = today.replace(day=1)
    if today.month == 12:
        end = date(today.year + 1, 1, 1)
    else:
        end = date(today.year, today.month + 1, 1)
    return start, end


def dashboard_context(user: User) -> dict[str, object]:
    today = date.today()
    start_date, next_month_start = _month_bounds(today)
    summary_row = (
        visible_transactions_query(user)
        .filter(Transaction.transaction_date >= start_date, Transaction.transaction_date < next_month_start)
        .with_entities(
            func.coalesce(
                func.sum(
                    case(
                        (
                            (Transaction.transaction_type == TransactionType.REVENUE.value)
                            & Transaction.status.in_(REVENUE_SETTLED_STATUSES),
                            Transaction.received_amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            (Transaction.transaction_type == TransactionType.EXPENSE.value)
                            & Transaction.status.in_(EXPENSE_SETTLED_STATUSES),
                            Transaction.amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        )
        .one()
    )
    revenue_total = Decimal(summary_row[0] or 0)
    expense_total = Decimal(summary_row[1] or 0)
    return {
        "month_label": start_date.strftime("%B %Y"),
        "summary": {
            "revenue_this_month": revenue_total,
            "expenses_this_month": expense_total,
            "net_cash_flow": revenue_total - expense_total,
        },
        "recent_transactions": recent_transactions(user, limit=6),
        "active_users": User.query.filter_by(is_active=True).order_by(User.full_name.asc()).all() if user.is_admin else [],
        "active_accounts": Account.query.filter_by(is_active=True).order_by(Account.name.asc()).all() if user.is_admin else [],
    }
