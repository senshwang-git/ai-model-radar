from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import Item

# Keep at most this many keys per source so the state file stays small.
MAX_KEYS_PER_SOURCE = 5000


def bucket(it: Item) -> str:
    return f"{it.source}/{it.group}"


class State:
    """Persistent record of already-seen item keys.

    Keys are de-duplicated per source. Buckets (source/group, e.g.
    "huggingface/Qwen") track which feeds/orgs have been seen at least once, so
    a newly added org or feed is recorded silently instead of flooding alerts.
    """

    def __init__(self, path: Path):
        self.path = path
        raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.seen: dict[str, list[str]] = raw.get("seen", {})
        self.buckets: set[str] = set(raw.get("buckets", []))

    def is_new_bucket(self, it: Item) -> bool:
        return bucket(it) not in self.buckets

    def diff(self, items: list[Item]) -> list[Item]:
        seen = {s: set(keys) for s, keys in self.seen.items()}
        out, picked = [], set()
        for it in items:
            k = (it.source, it.key)
            if it.key not in seen.get(it.source, ()) and k not in picked:
                out.append(it)
                picked.add(k)
        return out

    def record(self, items: list[Item]) -> None:
        index = {s: set(keys) for s, keys in self.seen.items()}
        for it in items:
            self.buckets.add(bucket(it))
            keys = self.seen.setdefault(it.source, [])
            idx = index.setdefault(it.source, set())
            if it.key not in idx:
                keys.append(it.key)
                idx.add(it.key)
        for keys in self.seen.values():
            if len(keys) > MAX_KEYS_PER_SOURCE:
                del keys[: len(keys) - MAX_KEYS_PER_SOURCE]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "buckets": sorted(self.buckets),
            "seen": self.seen,
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                             encoding="utf-8")
