from __future__ import annotations

import re
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

from ..feeds import parse
from ..http import fetch, get_json
from ..models import Item, to_date
from ..topics import match as match_topics


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
            title = re.sub(r"\s+", " ", paper.get("title") or p.get("title") or pid or "")
            summary = re.sub(r"\s+", " ", paper.get("summary") or "")
            topics = match_topics(f"{title} {summary}", cfg.get("topics", []))
            # Popular papers, plus any paper on a followed topic.
            if not pid or (up < min_up and not topics):
                continue
            items.append(Item(source="papers", key=f"arxiv:{pid}", title=title,
                              url=f"https://huggingface.co/papers/{pid}",
                              detail=f"▲{up} {summary[:300]}".strip(), group="HF Daily Papers",
                              published=to_date(p.get("publishedAt")) or str(d),
                              extra={"topics": topics} if topics else {}))
    return items


def _arxiv(cfg: dict, query: str | None = None, group: str = "arXiv",
           topics: list[str] | None = None) -> list[Item]:
    q = " ".join((query or cfg.get("query", "")).split())
    params = urllib.parse.urlencode({
        "search_query": q, "sortBy": "submittedDate", "sortOrder": "descending",
        "max_results": int(cfg.get("max_results", 50))})
    entries = parse(fetch(f"https://export.arxiv.org/api/query?{params}"))
    items = []
    for e in entries:
        # e.g. http://arxiv.org/abs/2510.01234v2 -> 2510.01234
        aid = re.sub(r"v\d+$", "", e.id.rsplit("/abs/", 1)[-1])
        detail = f"{e.published[:10]} {e.summary[:300]}".strip() if topics else e.published[:10]
        items.append(Item(source="papers", key=f"arxiv:{aid}", title=e.title,
                          url=f"https://arxiv.org/abs/{aid}", detail=detail,
                          group=group, published=to_date(e.published),
                          extra={"topics": topics} if topics else {}))
    return items


TOPIC_CATEGORIES = ["cs.CL", "cs.LG", "cs.AI", "cs.DC", "cs.AR", "cs.PF", "cs.OS"]


def topic_query(topic: dict) -> str:
    """arXiv query: any keyword in title or abstract, within CS categories."""
    cats = " OR ".join(f"cat:{c}" for c in topic.get("arxiv_categories", TOPIC_CATEGORIES))
    terms = " OR ".join(f'ti:"{k}" OR abs:"{k}"' for k in topic.get("keywords", []))
    return f"({cats}) AND ({terms})"


def collect(cfg: dict) -> list[Item]:
    items: list[Item] = []
    if cfg.get("hf_daily_papers", True):
        items += _hf_daily(cfg)
    if (cfg.get("arxiv") or {}).get("enabled", False):
        try:
            items += _arxiv(cfg["arxiv"])
        except Exception as e:
            print(f"[papers] arxiv: error {e}")
    for topic in cfg.get("topics", []):
        if not topic.get("arxiv") or not topic.get("keywords"):
            continue
        time.sleep(3)  # arXiv asks for a few seconds between API calls
        try:
            items += _arxiv({"max_results": topic.get("arxiv_max_results", 20)},
                            query=topic_query(topic), group=f"arXiv · {topic['name']}",
                            topics=[topic["name"]])
        except Exception as e:
            print(f"[papers] arxiv topic {topic['name']}: error {e}")
    return items
