from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from app.models import Transaction, User
from app.transactions.services import TransactionFilters, apply_filters, export_transactions_csv, visible_transactions_query
from app.utils.enums import ExpenseStatus, RevenueStatus, TransactionType


REPORT_OPTIONS = [
    ("revenue_monthly", "Revenue by month"),
    ("expense_monthly", "Expenses by month"),
    ("cash_flow_monthly", "Net cash flow by month"),
    ("expense_category", "Expenses by category"),
    ("revenue_source", "Revenue by source"),
    ("receivables", "Outstanding receivables"),
    ("payables", "Outstanding payables"),
]


def build_report(user: User, report_key: str, filters: TransactionFilters) -> dict:
    rows = defaultdict(Decimal)
    items = apply_filters(visible_transactions_query(user), filters).order_by(Transaction.transaction_date.asc()).all()
    for item in items:
        month_label = item.transaction_date.strftime("%b %Y")
        if report_key == "revenue_monthly" and item.transaction_type == TransactionType.REVENUE.value:
            rows[month_label] += Decimal(item.received_amount or 0)
        elif report_key == "expense_monthly" and item.transaction_type == TransactionType.EXPENSE.value:
            if item.status in {ExpenseStatus.PAID.value, ExpenseStatus.REIMBURSED.value}:
                rows[month_label] += Decimal(item.amount or 0)
        elif report_key == "cash_flow_monthly":
            if item.transaction_type == TransactionType.REVENUE.value:
                rows[month_label] += Decimal(item.received_amount or 0)
            elif item.status in {ExpenseStatus.PAID.value, ExpenseStatus.REIMBURSED.value}:
                rows[month_label] -= Decimal(item.amount or 0)
        elif report_key == "expense_category" and item.transaction_type == TransactionType.EXPENSE.value:
            rows[item.category.name] += Decimal(item.amount or 0)
        elif report_key == "revenue_source" and item.transaction_type == TransactionType.REVENUE.value:
            rows[item.counterparty or item.title] += Decimal(item.received_amount or 0)
        elif report_key == "receivables" and item.transaction_type == TransactionType.REVENUE.value:
            if item.status in {RevenueStatus.EXPECTED.value, RevenueStatus.PARTIALLY_RECEIVED.value, RevenueStatus.OVERDUE.value}:
                rows[item.counterparty or item.title] += Decimal(item.expected_amount or item.amount or 0) - Decimal(item.received_amount or 0)
        elif report_key == "payables" and item.transaction_type == TransactionType.EXPENSE.value:
            if item.status in {ExpenseStatus.SUBMITTED.value, ExpenseStatus.APPROVED.value, ExpenseStatus.OVERDUE.value}:
                rows[item.counterparty or item.title] += Decimal(item.amount or 0)
    return {
        "labels": list(rows.keys()),
        "values": [float(value) for value in rows.values()],
        "rows": [(label, float(value)) for label, value in rows.items()],
        "metric_total": float(sum(rows.values(), Decimal("0"))),
    }


def export_report_csv(user: User, report_key: str, filters: TransactionFilters) -> str:
    report_keys = {value for value, _label in REPORT_OPTIONS}
    report = build_report(user, report_key, filters)
    if report_key in report_keys:
        lines = ["label,value"]
        lines.extend(f"{label},{value}" for label, value in report["rows"])
        return "\n".join(lines)
    return export_transactions_csv(user=user, filters=filters)
