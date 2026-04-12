from __future__ import annotations

from app.extensions import db
from app.models.base import TimestampMixin


class Transaction(TimestampMixin, db.Model):
    __tablename__ = "transactions"
    __table_args__ = (
        db.Index("ix_transactions_type_status", "transaction_type", "status"),
        db.Index("ix_transactions_owner_date", "submitted_by_id", "transaction_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    transaction_type = db.Column(db.String(20), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text)
    counterparty = db.Column(db.String(160))
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False, index=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    payment_method_id = db.Column(db.Integer, db.ForeignKey("payment_methods.id"))
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    expected_amount = db.Column(db.Numeric(12, 2))
    received_amount = db.Column(db.Numeric(12, 2))
    transaction_date = db.Column(db.Date, nullable=False, index=True)
    due_date = db.Column(db.Date)
    settled_date = db.Column(db.Date)
    status = db.Column(db.String(40), nullable=False, index=True)
    reimbursable = db.Column(db.Boolean, nullable=False, default=False)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    reference_number = db.Column(db.String(100))
    note = db.Column(db.Text)
    attachment_count = db.Column(db.Integer, nullable=False, default=0)
    is_reconciled = db.Column(db.Boolean, nullable=False, default=False)
    reconciled_at = db.Column(db.DateTime(timezone=True))
    deleted_at = db.Column(db.DateTime(timezone=True))

    category = db.relationship("Category")
    account = db.relationship("Account")
    payment_method = db.relationship("PaymentMethod")
    submitted_by = db.relationship("User", foreign_keys=[submitted_by_id], back_populates="submitted_transactions")
    approved_by = db.relationship("User", foreign_keys=[approved_by_id], back_populates="approved_transactions")
    attachments = db.relationship("Attachment", back_populates="transaction", cascade="all, delete-orphan")
