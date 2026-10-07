from sqlalchemy.orm import Session

from app.models import AuditLog, User


def audit(
    db: Session,
    user: User | None,
    action: str,
    entity: str,
    entity_id: int | str | None = None,
    payload: dict | None = None,
) -> None:
    """Adds an audit record to the session; the caller commits it with its own changes."""
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            payload=payload or {},
        )
    )
