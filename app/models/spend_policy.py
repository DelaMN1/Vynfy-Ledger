from __future__ import annotations

from app.extensions import db
from app.models.base import TimestampMixin


class SpendPolicy(TimestampMixin, db.Model):
    __tablename__ = "spend_policies"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    transaction_type = db.Column(db.String(20), index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), index=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), index=True)
    payment_method_id = db.Column(db.Integer, db.ForeignKey("payment_methods.id"), index=True)
    max_amount = db.Column(db.Numeric(12, 2))
    require_attachment = db.Column(db.Boolean, nullable=False, default=False)
    require_note = db.Column(db.Boolean, nullable=False, default=False)
    block_on_over_budget = db.Column(db.Boolean, nullable=False, default=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    category = db.relationship("Category")
    account = db.relationship("Account")
    payment_method = db.relationship("PaymentMethod")
