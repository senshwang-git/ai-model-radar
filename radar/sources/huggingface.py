from __future__ import annotations

import re
import urllib.parse

from ..http import get_json
from ..models import Item, to_date

API = "https://huggingface.co/api/models"
EXPAND = ["createdAt", "pipeline_tag", "safetensors", "gated", "library_name"]


def _query(params: dict) -> str:
    q = list(params.items()) + [("expand[]", e) for e in EXPAND]
    return f"{API}?{urllib.parse.urlencode(q)}"


def _fmt_params(n: int | None) -> str:
    if not n:
        return ""
    for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if n >= div:
            return f"{n / div:.1f}{unit}".replace(".0", "")
    return str(n)


def _detail(m: dict) -> str:
    parts = []
    params = _fmt_params(((m.get("safetensors") or {}).get("total")))
    if params:
        parts.append(f"{params} params")
    if m.get("pipeline_tag"):
        parts.append(m["pipeline_tag"])
    if m.get("gated"):
        parts.append("gated")
    if m.get("createdAt"):
        parts.append(m["createdAt"][:10])
    return " · ".join(parts)


def _item(m: dict, group: str) -> Item:
    mid = m.get("id") or m.get("modelId")
    return Item(source="huggingface", key=mid, title=mid, group=group,
                url=f"https://huggingface.co/{mid}", detail=_detail(m),
                published=to_date(m.get("createdAt")))


def collect(cfg: dict) -> list[Item]:
    excludes = [re.compile(p) for p in cfg.get("exclude_patterns", [])]
    limit = int(cfg.get("per_author_limit", 30))
    authors = cfg.get("authors", [])
    items: list[Item] = []
    errors = []

    for author in authors:
        try:
            models = get_json(_query({"author": author, "sort": "createdAt",
                                      "direction": -1, "limit": limit}))
        except Exception as e:  # keep going for other authors
            errors.append(f"{author}: {e}")
            continue
        for m in models:
            it = _item(m, author)
            if not any(p.search(it.key) for p in excludes):
                items.append(it)

    top_n = int(cfg.get("trending_top_n", 0) or 0)
    if top_n:
        lowered = {a.lower() for a in authors}
        try:
            models = get_json(_query({"sort": "trendingScore", "direction": -1,
                                      "limit": top_n}))
            for m in models:
                it = _item(m, "🔥 trending")
                if it.key.split("/")[0].lower() not in lowered and \
                        not any(p.search(it.key) for p in excludes):
                    items.append(it)
        except Exception as e:
            errors.append(f"trending: {e}")

    if errors and not items:
        raise RuntimeError("; ".join(errors))
    for e in errors:
        print(f"[huggingface] warning: {e}")
    return items
