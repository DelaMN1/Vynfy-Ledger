from __future__ import annotations

from decimal import Decimal


def currency(value: Decimal | float | int | None) -> str:
    amount = Decimal(value or 0)
    return f"GHS {amount:,.2f}"


def yes_no(value: bool) -> str:
    return "Yes" if value else "No"
