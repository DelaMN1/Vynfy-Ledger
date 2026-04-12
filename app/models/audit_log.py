from __future__ import annotations

from app.extensions import db
from app.models.base import TimestampMixin


class AuditLog(TimestampMixin, db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    entity_type = db.Column(db.String(80), nullable=False, index=True)
    entity_id = db.Column(db.Integer)
    action = db.Column(db.String(80), nullable=False, index=True)
    old_values_json = db.Column(db.JSON)
    new_values_json = db.Column(db.JSON)
    ip_address = db.Column(db.String(64))
