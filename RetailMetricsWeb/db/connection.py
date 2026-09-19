from __future__ import annotations

from collections.abc import Generator
import logging

from fastapi import Depends, Request

from psycopg2.extensions import connection
from psycopg2.pool import ThreadedConnectionPool

from core.config import Settings
from core.config import get_settings


logger = logging.getLogger(__name__)


_pool: ThreadedConnectionPool | None = None


def initialize_pool(settings: Settings) -> None:
    global _pool
    if _pool is not None:
        return
    _pool = ThreadedConnectionPool(
        settings.db_pool_min,
        settings.db_pool_max,
        **settings.database_kwargs(),
    )


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


def get_db_connection(request: Request, settings: Settings = Depends(get_settings)) -> Generator[connection, None, None]:
    if _pool is None:
        raise RuntimeError("Database connection pool is not initialized")
    conn = _pool.getconn()
    try:
        yield conn
        if settings.audit_trail_enabled:
            from services.audit import event_for_request, write_event
            event = event_for_request(request)
            if event is not None:
                write_event(conn, request, event)
        conn.commit()
        ids = list(getattr(request.state, "notification_ids", ()))
        if ids:
            try:
                from services.notifications.outbox import dispatch_ids
                request.state.notification_outcomes = dispatch_ids(conn, ids, settings)
            except Exception:
                # The business transaction was already committed. Never roll it back.
                conn.rollback()
                logger.exception("post-commit notification dispatch failed")
        messages = list(getattr(request.state, "post_commit_notification_messages", ()))
        if messages:
            try:
                from services.notifications.providers import ProviderFailure, provider_for
                provider = provider_for(settings)
                for message in messages:
                    if message.channel == "email":
                        provider.send_email(message)
                    else:
                        provider.send_sms(message)
            except ProviderFailure as exc:
                # Never log the token-containing message, recipient, SMTP response, or credentials.
                logger.warning("post-commit authentication notification failed code=%s", exc.code)
            except Exception:
                logger.error("post-commit authentication notification failed unexpectedly")
    except Exception:
        conn.rollback()
        if settings.audit_trail_enabled and getattr(request.state, "audit_failed_login", False):
            try:
                from services.audit import AuditEvent, write_event
                write_event(conn, request, AuditEvent("LOGIN_FAILED"))
                conn.commit()
            except Exception:
                conn.rollback()
                logger.error("failed-login audit could not be recorded")
        raise
    finally:
        _pool.putconn(conn)
