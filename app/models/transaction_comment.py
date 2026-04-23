from __future__ import annotations

from app.extensions import db
from app.models.base import TimestampMixin


class TransactionComment(TimestampMixin, db.Model):
    __tablename__ = "transaction_comments"

    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)

    transaction = db.relationship("Transaction", back_populates="comments")
    user = db.relationship("User")
