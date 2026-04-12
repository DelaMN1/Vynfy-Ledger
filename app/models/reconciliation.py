from __future__ import annotations

from app.extensions import db
from app.models.base import TimestampMixin
from app.utils.enums import ReconciliationStatus


class ReconciliationSession(TimestampMixin, db.Model):
    __tablename__ = "reconciliation_sessions"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    statement_ending_balance = db.Column(db.Numeric(12, 2), nullable=False)
    system_balance = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    difference = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default=ReconciliationStatus.DRAFT.value)
    completed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    selected_transaction_ids = db.Column(db.JSON, nullable=False, default=list)

    account = db.relationship("Account")
