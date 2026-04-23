from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Literal, Protocol, TypeAlias, TypeVar, TypedDict

if TYPE_CHECKING:
    from app.models import Transaction


ChoiceOption: TypeAlias = tuple[int | str, str]
ChoiceOptions: TypeAlias = list[ChoiceOption]
ReportOption: TypeAlias = tuple[str, str]
ReportOptions: TypeAlias = tuple[ReportOption, ...]
JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
FieldValueT = TypeVar("FieldValueT")


class FieldLike(Protocol[FieldValueT]):
    data: FieldValueT


class ChoiceFieldLike(Protocol):
    choices: ChoiceOptions


@dataclass
class TransactionFilters:
    q: str | None = None
    status: str | None = None
    category_id: int | None = None
    account_id: int | None = None
    owner_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None


class TransactionSnapshot(TypedDict):
    title: str
    status: str
    amount: float
    expected_amount: float
    received_amount: float
    account_id: int
    category_id: int


class ReportResult(TypedDict):
    labels: list[str]
    values: list[float]
    rows: list[tuple[str, float]]
    metric_total: float


class DashboardSummary(TypedDict):
    revenue_this_month: Decimal
    expenses_this_month: Decimal
    net_cash_flow: Decimal
    cash_snapshot: Decimal
    outstanding_receivables: Decimal
    outstanding_payables: Decimal
    pending_approvals: int
    overdue_items: int
    budget_alerts: int
    unreconciled_transactions: int


class DashboardChart(TypedDict):
    labels: list[str]
    values: list[float]


class MonthlyTotals(TypedDict):
    revenue: Decimal
    expense: Decimal


class TrendChart(TypedDict):
    labels: list[str]
    revenue: list[float]
    expense: list[float]


class BudgetHealthRow(TypedDict):
    name: str
    actual: Decimal
    budget_amount: Decimal
    remaining: Decimal
    utilization_percent: int
    alert_triggered: bool
    over_budget: bool
    category_id: int | None
    account_id: int | None
    owner_id: int | None


class DashboardQueueItem(TypedDict):
    id: int
    title: str
    status: str
    amount: Decimal
    owner_name: str
    detail_url: str


class DashboardDrilldownRow(TypedDict):
    label: str
    total: Decimal
    transaction_count: int


class DashboardContext(TypedDict):
    range_key: str
    summary: DashboardSummary
    recent_transactions: list[Transaction]
    expense_chart: DashboardChart
    trend_chart: TrendChart
    budget_rows: list[BudgetHealthRow]
    action_queue: list[DashboardQueueItem]
    drilldown_rows: list[DashboardDrilldownRow]


class VerificationTokenPayload(TypedDict):
    purpose: Literal["verify-email"]
    user_id: int


class PasswordResetTokenPayload(TypedDict):
    purpose: Literal["reset-password"]
    user_id: int
    password_changed_at: str


TokenPayload: TypeAlias = VerificationTokenPayload | PasswordResetTokenPayload


class TransactionChoiceForm(Protocol):
    category_id: ChoiceFieldLike
    account_id: ChoiceFieldLike
    payment_method_id: ChoiceFieldLike


class TransactionFilterChoiceForm(Protocol):
    category_id: ChoiceFieldLike
    account_id: ChoiceFieldLike
    owner_id: ChoiceFieldLike
    status: ChoiceFieldLike


class TransactionFormLike(Protocol):
    title: FieldLike[str]
    description: FieldLike[str | None]
    counterparty: FieldLike[str | None]
    category_id: FieldLike[int]
    account_id: FieldLike[int]
    payment_method_id: FieldLike[int | None]
    transaction_date: FieldLike[date]
    due_date: FieldLike[date | None]
    settled_date: FieldLike[date | None]
    reference_number: FieldLike[str | None]
    note: FieldLike[str | None]
    save_draft: FieldLike[bool]
    expected_amount: FieldLike[Decimal]
    received_amount: FieldLike[Decimal | None]
    amount: FieldLike[Decimal]
    reimbursable: FieldLike[bool]
    status: FieldLike[str | None]
