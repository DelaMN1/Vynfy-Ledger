from __future__ import annotations

from app.extensions import db
from app.models.base import TimestampMixin


class TransactionStatusHistory(TimestampMixin, db.Model):
    __tablename__ = "transaction_status_history"

    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id"), nullable=False, index=True)
    changed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    action = db.Column(db.String(80), nullable=False, index=True)
    from_status = db.Column(db.String(40))
    to_status = db.Column(db.String(40))
    note = db.Column(db.Text)
    metadata_json = db.Column(db.JSON)

    transaction = db.relationship("Transaction", back_populates="status_history")
    changed_by = db.relationship("User")
