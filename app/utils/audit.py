from __future__ import annotations

from flask import request

from app.extensions import db
from app.models.audit_log import AuditLog


def record_audit(
    *,
    user_id: int | None,
    entity_type: str,
    entity_id: int | None,
    action: str,
    old_values: dict | None = None,
    new_values: dict | None = None,
) -> None:
    log = AuditLog(
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_values_json=old_values,
        new_values_json=new_values,
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    db.session.add(log)
