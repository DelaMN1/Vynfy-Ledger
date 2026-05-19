from __future__ import annotations

from decimal import Decimal

from app.utils.enums import STATUS_BADGE_DEFAULT, STATUS_BADGE_GROUPS


def currency(value: Decimal | float | int | None) -> str:
    amount = Decimal(value or 0)
    return f"GHS {amount:,.2f}"


def yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def safe_csv_cell(value: object) -> object:
    if not isinstance(value, str):
        return value
    if not value:
        return value
    stripped = value.lstrip()
    if stripped.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def status_badge_class(status: str) -> str:
    for tone, statuses in STATUS_BADGE_GROUPS.items():
        if status in statuses:
            return tone
    return STATUS_BADGE_DEFAULT
