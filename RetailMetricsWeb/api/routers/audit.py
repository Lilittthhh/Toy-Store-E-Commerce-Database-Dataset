"""Read-only Admin audit inspection; never exposes a mutation route."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from psycopg2.extensions import connection
from psycopg2.extras import RealDictCursor

from core.config import Settings, get_settings
from core.dependencies import require_roles
from core.models import AppUser, Role
from db.connection import get_db_connection

router = APIRouter(prefix="/admin/audit-logs", tags=["Admin audit trail"])


def _ready(settings: Settings) -> None:
    if not settings.audit_trail_enabled:
        raise HTTPException(503, "Audit Trail is pending Migration 005 deployment.")


@router.get("")
def list_audit_logs(
    limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
    from_date: datetime | None = None, to_date: datetime | None = None,
    actor_type: str | None = Query(None, pattern="^(staff|customer|system|anonymous)$"),
    actor_id: int | None = Query(None, gt=0),
    actor_role: str | None = Query(None, pattern="^(admin|operations_staff|analyst|customer)$"),
    action: str | None = Query(None, pattern="^[A-Z][A-Z0-9_]{1,79}$"),
    entity_type: str | None = Query(None, pattern="^[a-z_]{1,64}$"),
    entity_id: str | None = Query(None, max_length=100),
    search: str | None = Query(None, max_length=100),
    _: AppUser = Depends(require_roles(Role.ADMIN)),
    settings: Settings = Depends(get_settings),
    conn: connection = Depends(get_db_connection),
):
    _ready(settings)
    if from_date and to_date and from_date > to_date:
        raise HTTPException(422, "from_date must not be after to_date.")
    conditions, args = [], []
    for column, value in (("created_at >=", from_date), ("created_at <=", to_date),
                          ("actor_type =", actor_type), ("actor_id =", actor_id),
                          ("actor_role =", actor_role), ("action =", action),
                          ("entity_type =", entity_type), ("entity_id =", entity_id)):
        if value is not None:
            conditions.append(f"{column} %s")
            args.append(value)
    if search:
        conditions.append("(action ILIKE %s OR entity_type ILIKE %s OR entity_id ILIKE %s OR description ILIKE %s)")
        term = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        args.extend([term] * 4)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT count(*) AS total FROM public.audit_logs" + where, args)
        total = cur.fetchone()["total"]
        cur.execute("SELECT * FROM public.audit_logs" + where +
                    " ORDER BY created_at DESC, audit_log_id DESC LIMIT %s OFFSET %s", [*args, limit, offset])
        items = [dict(row) for row in cur.fetchall()]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{audit_log_id}")
def get_audit_log(
    audit_log_id: int = Path(gt=0),
    _: AppUser = Depends(require_roles(Role.ADMIN)),
    settings: Settings = Depends(get_settings),
    conn: connection = Depends(get_db_connection),
):
    _ready(settings)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM public.audit_logs WHERE audit_log_id = %s", (audit_log_id,))
        row = cur.fetchone()
    if row is None:
        raise HTTPException(404, "Audit event not found.")
    return dict(row)
