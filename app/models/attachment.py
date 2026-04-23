from __future__ import annotations

from app.extensions import db
from app.models.base import TimestampMixin


class Attachment(TimestampMixin, db.Model):
    __tablename__ = "attachments"

    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id"), nullable=False, index=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False, unique=True)
    file_path = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(120), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    sha256_hash = db.Column(db.String(64), index=True)
    duplicate_of_attachment_id = db.Column(db.Integer, db.ForeignKey("attachments.id"))
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    transaction = db.relationship("Transaction", back_populates="attachments")
    duplicate_of = db.relationship("Attachment", remote_side=[id])
