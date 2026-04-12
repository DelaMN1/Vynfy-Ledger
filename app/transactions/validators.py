from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.utils.enums import ExpenseStatus, RevenueStatus, TransactionType
from app.utils.exceptions import ServiceError


EXPENSE_TRANSITIONS = {
    ExpenseStatus.DRAFT.value: {ExpenseStatus.SUBMITTED.value},
    ExpenseStatus.SUBMITTED.value: {
        ExpenseStatus.APPROVED.value,
        ExpenseStatus.REJECTED.value,
        ExpenseStatus.RETURNED.value,
    },
    ExpenseStatus.RETURNED.value: {ExpenseStatus.DRAFT.value},
    ExpenseStatus.APPROVED.value: {ExpenseStatus.PAID.value},
}

REVENUE_TRANSITIONS = {
    RevenueStatus.DRAFT.value: {RevenueStatus.EXPECTED.value, RevenueStatus.CANCELLED.value},
    RevenueStatus.EXPECTED.value: {
        RevenueStatus.PARTIALLY_RECEIVED.value,
        RevenueStatus.RECEIVED.value,
        RevenueStatus.OVERDUE.value,
        RevenueStatus.CANCELLED.value,
    },
    RevenueStatus.PARTIALLY_RECEIVED.value: {
        RevenueStatus.RECEIVED.value,
        RevenueStatus.OVERDUE.value,
        RevenueStatus.CANCELLED.value,
    },
    RevenueStatus.OVERDUE.value: {
        RevenueStatus.PARTIALLY_RECEIVED.value,
        RevenueStatus.RECEIVED.value,
        RevenueStatus.CANCELLED.value,
    },
}


def validate_status_transition(transaction_type: str, current_status: str, next_status: str, *, override: bool = False) -> None:
    if override or current_status == next_status:
        return
    transitions = EXPENSE_TRANSITIONS if transaction_type == TransactionType.EXPENSE.value else REVENUE_TRANSITIONS
    if next_status not in transitions.get(current_status, set()):
        raise ServiceError(f"Invalid status transition from {current_status} to {next_status}.")


def derive_revenue_status(expected_amount: Decimal, received_amount: Decimal | None, due_date, today: date) -> str:
    received = received_amount or Decimal("0")
    if received >= expected_amount:
        return RevenueStatus.RECEIVED.value
    if received > 0:
        return RevenueStatus.PARTIALLY_RECEIVED.value
    if due_date and due_date < today:
        return RevenueStatus.OVERDUE.value
    return RevenueStatus.EXPECTED.value
