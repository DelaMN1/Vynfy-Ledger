from __future__ import annotations

from app.extensions import db
from app.models.base import TimestampMixin


class AccountingMapping(TimestampMixin, db.Model):
    __tablename__ = "accounting_mappings"
    __table_args__ = (
        db.Index("ix_accounting_mappings_active_scope", "is_active", "transaction_type", "category_id", "account_id", "payment_method_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    transaction_type = db.Column(db.String(20), index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), index=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), index=True)
    payment_method_id = db.Column(db.Integer, db.ForeignKey("payment_methods.id"), index=True)
    gl_code = db.Column(db.String(50), nullable=False)
    cost_center = db.Column(db.String(50))
    project_code = db.Column(db.String(50))
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    category = db.relationship("Category")
    account = db.relationship("Account")
    payment_method = db.relationship("PaymentMethod")
