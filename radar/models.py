from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def to_date(value) -> str:
    """Normalize ISO-8601, RFC-822 or unix-epoch timestamps to UTC 'YYYY-MM-DD'."""
    if value in (None, ""):
        return ""
    try:
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(value, tz=timezone.utc)
        else:
            s = str(value).strip()
            try:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            except ValueError:
                dt = parsedate_to_datetime(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError, OverflowError):
        return ""


@dataclass(frozen=True)
class Item:
    """A single detected thing (model, release, paper, article)."""

    source: str  # e.g. "huggingface", "providers", "news"
    key: str  # unique within the source; used for de-duplication
    title: str
    url: str = ""
    detail: str = ""
    group: str = ""  # sub-heading in reports, e.g. org name or feed name
    published: str = ""  # UTC date 'YYYY-MM-DD' when known
    extra: dict = field(default_factory=dict, compare=False, hash=False)
