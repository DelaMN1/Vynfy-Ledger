from __future__ import annotations

from app.extensions import db
from app.models.audit_log import AuditLog
from app.utils.security import get_request_ip
from app.utils.types import JsonValue


def record_audit(
    *,
    user_id: int | None,
    entity_type: str,
    entity_id: int | None,
    action: str,
    old_values: JsonValue | None = None,
    new_values: JsonValue | None = None,
) -> None:
    log = AuditLog(
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_values_json=old_values,
        new_values_json=new_values,
        ip_address=get_request_ip(),
    )
    db.session.add(log)
