from __future__ import annotations

from app.extensions import db
from app.models.base import TimestampMixin


class Budget(TimestampMixin, db.Model):
    __tablename__ = "budgets"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    transaction_type = db.Column(db.String(20), index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), index=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), index=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    alert_percent = db.Column(db.Integer, nullable=False, default=80)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    category = db.relationship("Category")
    account = db.relationship("Account")
    owner = db.relationship("User")
