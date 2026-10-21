from datetime import datetime
import re

from flask import current_app
from sqlalchemy import func, select

from app.extensions import db
from app.services.email_delivery import send_notification_digests_local


def worker_settings():
    daily_time = current_app.config["EMAIL_DAILY_TIME"]
    if not isinstance(daily_time, str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", daily_time):
        raise ValueError("EMAIL_DAILY_TIME trebuie sa fie HH:MM, de exemplu 08:00.")
    try:
        retry_seconds = int(current_app.config["EMAIL_RETRY_SECONDS"])
        if not 60 <= retry_seconds <= 3600:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("EMAIL_RETRY_SECONDS trebuie sa fie intre 60 si 3600.") from None
    return datetime.strptime(daily_time, "%H:%M").time(), retry_seconds


def bucharest_now(moment=None):
    return db.session.scalar(select(func.timezone("Europe/Bucharest", moment if moment is not None else func.clock_timestamp())))


def run_notification_tick(*, last_completed_date=None):
    daily_time, retry_seconds = worker_settings()
    try:
        local_now = bucharest_now()
        today = local_now.date()
        if local_now.time() < daily_time or last_completed_date == today:
            return {"ran": False, "last_completed_date": last_completed_date, "local_time": local_now.isoformat()}
        result = send_notification_digests_local(retry_delay_seconds=retry_seconds)
        return {"ran": True, "last_completed_date": today if result["retryable"] == 0 else last_completed_date,
                "local_time": local_now.isoformat(), **result}
    finally:
        # Do not keep a read transaction open between checks.
        db.session.rollback()
