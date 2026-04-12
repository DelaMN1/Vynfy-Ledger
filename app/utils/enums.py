from __future__ import annotations

from enum import StrEnum


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


def choices(enum_type: type[StrEnum]) -> list[tuple[str, str]]:
    return [(item.value, item.value.replace("_", " ").title()) for item in enum_type]
