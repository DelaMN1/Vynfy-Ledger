from __future__ import annotations

from app.extensions import db
from app.models.base import TimestampMixin


class PaymentMethod(TimestampMixin, db.Model):
    __tablename__ = "payment_methods"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
