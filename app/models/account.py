from __future__ import annotations

from app.extensions import db
from app.models.base import TimestampMixin
from app.utils.enums import AccountType


class Account(TimestampMixin, db.Model):
    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    type = db.Column(db.String(30), nullable=False, default=AccountType.BANK.value)
    opening_balance = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    current_balance_cached = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    currency_code = db.Column(db.String(10), nullable=False, default="GHS")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
