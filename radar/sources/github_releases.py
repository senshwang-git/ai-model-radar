from __future__ import annotations

import os
import re

from ..http import get_json
from ..models import Item, to_date


NOTES_LIMIT = 3000


def clean_notes(body: str, limit: int = NOTES_LIMIT) -> str:
    """Compact release-note markdown for the digest prompt: drop images, HTML
    comments, contributor/changelog link lists and collapse whitespace."""
    s = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)                    # images
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", s)        # links -> text
    s = re.sub(r"https?://github\.com/\S+/pull/(\d+)", r"#\1", s)     # PR urls
    s = re.sub(r"(?im)^#+\s*(new contributors|full changelog).*", "", s)
    s = re.sub(r"(?m)^\s*\*\s+@\S+ made their first contribution.*$", "", s)
    s = re.sub(r"\n{2,}", "\n", s)
    s = re.sub(r"[ \t]+", " ", s).strip()
    return s[:limit] + ("…" if len(s) > limit else "")


def collect(cfg: dict) -> list[Item]:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    limit = int(cfg.get("per_repo_limit", 5))
    include_pre = bool(cfg.get("include_prereleases", False))

    items: list[Item] = []
    for repo in cfg.get("repos", []):
        try:
            rels = get_json(f"https://api.github.com/repos/{repo}/releases?per_page={limit}",
                            headers=headers)
        except Exception as e:
            print(f"[github_releases] {repo}: error {e}")
            continue
        for r in rels:
            if r.get("draft") or (r.get("prerelease") and not include_pre):
                continue
            tag = r["tag_name"]
            name = r.get("name") or tag
            title = f"{repo} {tag}" if name == tag else f"{repo} {tag} — {name}"
            detail = (r.get("published_at") or "")[:10]
            if r.get("prerelease"):
                detail += " · pre-release"
            items.append(Item(source="github_releases", key=f"{repo}@{tag}", title=title,
                              url=r.get("html_url", ""), detail=detail, group=repo,
                              published=to_date(r.get("published_at")),
                              extra={"notes": clean_notes(r.get("body") or "")}))
    return items
