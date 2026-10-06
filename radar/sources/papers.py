from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timedelta, timezone

from ..feeds import parse
from ..http import fetch, get_json
from ..models import Item, to_date


def _hf_daily(cfg: dict) -> list[Item]:
    min_up = int(cfg.get("hf_daily_min_upvotes", 0))
    today = datetime.now(timezone.utc).date()
    items: list[Item] = []
    for d in (today, today - timedelta(days=1), today - timedelta(days=2)):
        try:
            papers = get_json(f"https://huggingface.co/api/daily_papers?date={d}&limit=100")
        except Exception as e:
            print(f"[papers] hf daily {d}: error {e}")
            continue
        for p in papers:
            paper = p.get("paper", p)
            pid = paper.get("id")
            up = paper.get("upvotes", 0) or 0
            if not pid or up < min_up:
                continue
            title = re.sub(r"\s+", " ", paper.get("title") or p.get("title") or pid)
            items.append(Item(source="papers", key=f"arxiv:{pid}", title=title,
                              url=f"https://huggingface.co/papers/{pid}",
                              detail=f"▲{up}", group="HF Daily Papers",
                              published=to_date(p.get("publishedAt")) or str(d)))
    return items


def _arxiv(cfg: dict) -> list[Item]:
    q = " ".join(cfg.get("query", "").split())
    params = urllib.parse.urlencode({
        "search_query": q, "sortBy": "submittedDate", "sortOrder": "descending",
        "max_results": int(cfg.get("max_results", 50))})
    entries = parse(fetch(f"https://export.arxiv.org/api/query?{params}"))
    items = []
    for e in entries:
        # e.g. http://arxiv.org/abs/2510.01234v2 -> 2510.01234
        aid = re.sub(r"v\d+$", "", e.id.rsplit("/abs/", 1)[-1])
        items.append(Item(source="papers", key=f"arxiv:{aid}", title=e.title,
                          url=f"https://arxiv.org/abs/{aid}", detail=e.published[:10],
                          group="arXiv", published=to_date(e.published)))
    return items


def collect(cfg: dict) -> list[Item]:
    items: list[Item] = []
    if cfg.get("hf_daily_papers", True):
        items += _hf_daily(cfg)
    if (cfg.get("arxiv") or {}).get("enabled", False):
        try:
            items += _arxiv(cfg["arxiv"])
        except Exception as e:
            print(f"[papers] arxiv: error {e}")
    return items
