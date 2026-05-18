from __future__ import annotations

from app.extensions import db
from app.models.base import TimestampMixin
from app.utils.enums import Role
from app.utils.security import hash_password, verify_password
from app.utils.time import utcnow


class User(TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=Role.STAFF.value)
    can_create_revenue = db.Column(db.Boolean, nullable=False, default=False)
    email_verified = db.Column(db.Boolean, nullable=False, default=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime(timezone=True))
    last_login_at = db.Column(db.DateTime(timezone=True))
    password_changed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    submitted_transactions = db.relationship(
        "Transaction", foreign_keys="Transaction.submitted_by_id", back_populates="submitted_by", lazy="dynamic"
    )
    approved_transactions = db.relationship(
        "Transaction", foreign_keys="Transaction.approved_by_id", back_populates="approved_by", lazy="dynamic"
    )

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN.value

    def set_password(self, password: str) -> None:
        self.password_hash = hash_password(password)
        self.password_changed_at = utcnow()

    def check_password(self, password: str) -> bool:
        return verify_password(self.password_hash, password)

    @classmethod
    def create_admin(cls, full_name: str, email: str, password: str) -> "User":
        admin = cls(
            full_name=full_name.strip(),
            email=email.strip().lower(),
            role=Role.ADMIN.value,
            is_active=True,
            email_verified=True,
            can_create_revenue=True,
        )

        admin.set_password(password)
        db.session.add(admin)

        return admin