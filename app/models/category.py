from __future__ import annotations

from app.extensions import db
from app.models.base import TimestampMixin
from app.utils.enums import CategoryType


class Category(TimestampMixin, db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    type = db.Column(db.String(30), nullable=False, default=CategoryType.EXPENSE.value, index=True)
    color = db.Column(db.String(20), nullable=False, default="#1d4ed8")
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
