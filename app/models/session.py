from __future__ import annotations

from app.extensions import db
from app.models.base import TimestampMixin


class UserSession(TimestampMixin, db.Model):
    __tablename__ = "user_sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    issued_at = db.Column(db.DateTime(timezone=True), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    # Legacy column retained to track the last full credential authentication time.
    second_factor_verified_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    revoked_at = db.Column(db.DateTime(timezone=True))
    replaced_by_token_id = db.Column(db.Integer, db.ForeignKey("user_sessions.id"))
    user_agent = db.Column(db.String(255))
    ip_address = db.Column(db.String(64))

    user = db.relationship("User")
