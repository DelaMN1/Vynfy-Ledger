from __future__ import annotations

from datetime import date
from decimal import Decimal

from flask import current_app
from sqlalchemy import case, extract, func, or_

from app.models import Category, Transaction, User
from app.transactions.services import apply_filters, export_transactions_csv, visible_transactions_query
from app.utils.formatting import safe_csv_cell
from app.utils.enums import (
    EXPENSE_PAYABLE_STATUSES,
    EXPENSE_SETTLED_STATUSES,
    REVENUE_RECEIVABLE_STATUSES,
    REVENUE_SETTLED_STATUSES,
    TransactionType,
)
from app.utils.types import ReportOptions, ReportResult, TransactionFilters


REPORT_OPTIONS: ReportOptions = (
    ("revenue_monthly", "Revenue by month"),
    ("expense_monthly", "Expenses by month"),
    ("cash_flow_monthly", "Net cash flow by month"),
    ("expense_category", "Expenses by category"),
    ("revenue_source", "Revenue by source"),
    ("receivables", "Outstanding receivables"),
    ("payables", "Outstanding payables"),
)


def normalize_report_key(report_key: str) -> str:
    report_keys = {value for value, _label in REPORT_OPTIONS}
    return report_key if report_key in report_keys else "transactions"


def _enforce_report_row_limit(query) -> None:
    limit = current_app.config["MAX_EXPORT_ROWS"]
    row_ids = query.with_entities(Transaction.id).order_by(None).limit(limit + 1).all()
    if len(row_ids) > limit:
        raise ValueError(f"Report exceeds the maximum allowed size of {limit} rows. Narrow the filters and try again.")


def _monthly_rows(query, value_expression) -> list[tuple[str, float]]:
    year_col = extract("year", Transaction.transaction_date).label("year")
    month_col = extract("month", Transaction.transaction_date).label("month")
    rows = (
        query.with_entities(year_col, month_col, func.coalesce(func.sum(value_expression), 0).label("total"))
        .group_by(year_col, month_col)
        .order_by(year_col.asc(), month_col.asc())
        .all()
    )
    return [
        (date(int(year), int(month), 1).strftime("%b %Y"), float(total))
        for year, month, total in rows
    ]


def _labeled_rows(query, label_expression, value_expression) -> list[tuple[str, float]]:
    rows = (
        query.with_entities(label_expression.label("label"), func.coalesce(func.sum(value_expression), 0).label("total"))
        .group_by(label_expression)
        .order_by(label_expression.asc())
        .all()
    )
    return [(str(label), float(total)) for label, total in rows]


def _cash_flow_monthly_rows(query) -> list[tuple[str, float]]:
    year_col = extract("year", Transaction.transaction_date).label("year")
    month_col = extract("month", Transaction.transaction_date).label("month")
    signed_amount = case(
        (
            (
                (Transaction.transaction_type == TransactionType.REVENUE.value)
                & Transaction.status.in_(REVENUE_SETTLED_STATUSES)
            ),
            func.coalesce(Transaction.received_amount, 0),
        ),
        (
            (
                (Transaction.transaction_type == TransactionType.EXPENSE.value)
                & Transaction.status.in_(EXPENSE_SETTLED_STATUSES)
            ),
            -func.coalesce(Transaction.amount, 0),
        ),
        else_=0,
    )
    rows = (
        query.filter(
            or_(
                (
                    (Transaction.transaction_type == TransactionType.REVENUE.value)
                    & Transaction.status.in_(REVENUE_SETTLED_STATUSES)
                ),
                (
                    (Transaction.transaction_type == TransactionType.EXPENSE.value)
                    & Transaction.status.in_(EXPENSE_SETTLED_STATUSES)
                ),
            )
        )
        .with_entities(year_col, month_col, func.coalesce(func.sum(signed_amount), 0).label("total"))
        .group_by(year_col, month_col)
        .order_by(year_col.asc(), month_col.asc())
        .all()
    )
    return [(date(int(year), int(month), 1).strftime("%b %Y"), float(total)) for year, month, total in rows]


def build_report(user: User, report_key: str, filters: TransactionFilters) -> ReportResult:
    base_query = apply_filters(visible_transactions_query(user), filters)
    _enforce_report_row_limit(base_query)

    rows: list[tuple[str, float]]
    if report_key == "revenue_monthly":
        rows = _monthly_rows(
            base_query.filter(
                Transaction.transaction_type == TransactionType.REVENUE.value,
                Transaction.status.in_(REVENUE_SETTLED_STATUSES),
            ),
            Transaction.received_amount,
        )
    elif report_key == "expense_monthly":
        rows = _monthly_rows(
            base_query.filter(
                Transaction.transaction_type == TransactionType.EXPENSE.value,
                Transaction.status.in_(EXPENSE_SETTLED_STATUSES),
            ),
            Transaction.amount,
        )
    elif report_key == "cash_flow_monthly":
        rows = _cash_flow_monthly_rows(base_query)
    elif report_key == "expense_category":
        rows = _labeled_rows(
            base_query.join(Category, Category.id == Transaction.category_id).filter(
                Transaction.transaction_type == TransactionType.EXPENSE.value
            ),
            Category.name,
            Transaction.amount,
        )
    elif report_key == "revenue_source":
        label_expression = func.coalesce(Transaction.counterparty, Transaction.title)
        rows = _labeled_rows(
            base_query.filter(
                Transaction.transaction_type == TransactionType.REVENUE.value,
                Transaction.status.in_(REVENUE_SETTLED_STATUSES),
            ),
            label_expression,
            Transaction.received_amount,
        )
    elif report_key == "receivables":
        label_expression = func.coalesce(Transaction.counterparty, Transaction.title)
        rows = _labeled_rows(
            base_query.filter(
                Transaction.transaction_type == TransactionType.REVENUE.value,
                Transaction.status.in_(REVENUE_RECEIVABLE_STATUSES),
            ),
            label_expression,
            func.coalesce(Transaction.expected_amount, Transaction.amount, 0) - func.coalesce(Transaction.received_amount, 0),
        )
    elif report_key == "payables":
        label_expression = func.coalesce(Transaction.counterparty, Transaction.title)
        rows = _labeled_rows(
            base_query.filter(
                Transaction.transaction_type == TransactionType.EXPENSE.value,
                Transaction.status.in_(EXPENSE_PAYABLE_STATUSES),
            ),
            label_expression,
            Transaction.amount,
        )
    else:
        rows = []

    return {
        "labels": [label for label, _value in rows],
        "values": [value for _label, value in rows],
        "rows": rows,
        "metric_total": float(sum((Decimal(str(value)) for _label, value in rows), Decimal("0"))),
    }


def export_report_csv(user: User, report_key: str, filters: TransactionFilters) -> str:
    report_key = normalize_report_key(report_key)
    report_keys = {value for value, _label in REPORT_OPTIONS}
    report = build_report(user, report_key, filters)
    if report_key in report_keys:
        lines = ["label,value"]
        lines.extend(f"{safe_csv_cell(label)},{value}" for label, value in report["rows"])
        return "\n".join(lines)
    return export_transactions_csv(user=user, filters=filters)
