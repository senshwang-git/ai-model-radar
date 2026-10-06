from __future__ import annotations

import os

from ..http import get_json
from ..models import Item, to_date


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
                              published=to_date(r.get("published_at"))))
    return items
