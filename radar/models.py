from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Item:
    """A single detected thing (model, release, paper, article)."""

    source: str  # e.g. "huggingface", "providers", "news"
    key: str  # unique within the source; used for de-duplication
    title: str
    url: str = ""
    detail: str = ""
    group: str = ""  # sub-heading in reports, e.g. org name or feed name
    extra: dict = field(default_factory=dict, compare=False, hash=False)
