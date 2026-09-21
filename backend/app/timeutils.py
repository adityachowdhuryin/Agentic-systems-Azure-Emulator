from datetime import datetime, timezone


def to_utc_iso(value: datetime | None) -> str | None:
    """Serialize datetimes as ISO-8601 UTC with a Z suffix for correct IST display in the UI."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
