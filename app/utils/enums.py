from __future__ import annotations

from enum import StrEnum
from typing import TypeVar

from app.utils.types import ChoiceOptions


TStrEnum = TypeVar("TStrEnum", bound=StrEnum)


class Role(StrEnum):
    ADMIN = "admin"
    STAFF = "staff"


class TransactionType(StrEnum):
    REVENUE = "revenue"
    EXPENSE = "expense"


class RevenueStatus(StrEnum):
    DRAFT = "Draft"
    EXPECTED = "Expected"
    PARTIALLY_RECEIVED = "Partially Received"
    RECEIVED = "Received"
    OVERDUE = "Overdue"
    CANCELLED = "Cancelled"


class ExpenseStatus(StrEnum):
    DRAFT = "Draft"
    SUBMITTED = "Submitted"
    RETURNED = "Returned"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    PAID = "Paid"
    REIMBURSED = "Reimbursed"
    OVERDUE = "Overdue"


class AccountType(StrEnum):
    BANK = "bank"
    CASH = "cash"
    MOBILE_MONEY = "mobile_money"
    WALLET = "wallet"


class CategoryType(StrEnum):
    REVENUE = "revenue"
    EXPENSE = "expense"


class ReconciliationStatus(StrEnum):
    DRAFT = "draft"
    FINALIZED = "finalized"


REVENUE_STATUS_VALUES = frozenset(status.value for status in RevenueStatus)
EXPENSE_STATUS_VALUES = frozenset(status.value for status in ExpenseStatus)
TRANSACTION_STATUS_VALUES = {
    TransactionType.REVENUE.value: REVENUE_STATUS_VALUES,
    TransactionType.EXPENSE.value: EXPENSE_STATUS_VALUES,
}

REVENUE_SETTLED_STATUSES = frozenset({RevenueStatus.PARTIALLY_RECEIVED.value, RevenueStatus.RECEIVED.value})
EXPENSE_SETTLED_STATUSES = frozenset({ExpenseStatus.PAID.value, ExpenseStatus.REIMBURSED.value})
REVENUE_RECEIVABLE_STATUSES = frozenset({RevenueStatus.EXPECTED.value, RevenueStatus.PARTIALLY_RECEIVED.value, RevenueStatus.OVERDUE.value})
EXPENSE_PAYABLE_STATUSES = frozenset({ExpenseStatus.SUBMITTED.value, ExpenseStatus.APPROVED.value, ExpenseStatus.OVERDUE.value})
REVENUE_EDITABLE_STATUSES = frozenset(
    {
        RevenueStatus.DRAFT.value,
        RevenueStatus.EXPECTED.value,
        RevenueStatus.OVERDUE.value,
        RevenueStatus.PARTIALLY_RECEIVED.value,
    }
)
EXPENSE_EDITABLE_STATUSES = frozenset({ExpenseStatus.DRAFT.value, ExpenseStatus.RETURNED.value})

STATUS_BADGE_GROUPS = {
    "bg-emerald-100 text-emerald-900": frozenset({RevenueStatus.RECEIVED.value, ExpenseStatus.PAID.value, ExpenseStatus.APPROVED.value}),
    "bg-amber-100 text-amber-900": frozenset({ExpenseStatus.SUBMITTED.value, RevenueStatus.EXPECTED.value, RevenueStatus.PARTIALLY_RECEIVED.value}),
    "bg-rose-100 text-rose-900": frozenset({ExpenseStatus.REJECTED.value, RevenueStatus.CANCELLED.value, RevenueStatus.OVERDUE.value, ExpenseStatus.OVERDUE.value}),
}
STATUS_BADGE_DEFAULT = "bg-slate-100 text-slate-800"


def choices(enum_type: type[TStrEnum]) -> ChoiceOptions:
    return [(item.value, item.value.replace("_", " ").title()) for item in enum_type]
