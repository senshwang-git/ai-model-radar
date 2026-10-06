from __future__ import annotations

import os
import time

from .http import post_json


def github_issue(title: str, body: str, labels: list[str]) -> str | None:
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("[notify] GITHUB_TOKEN/GITHUB_REPOSITORY not set, skipping issue")
        return None
    res = post_json(f"https://api.github.com/repos/{repo}/issues",
                    {"title": title, "body": body, "labels": labels},
                    headers={"Authorization": f"Bearer {token}",
                             "Accept": "application/vnd.github+json"})
    url = res.get("html_url")
    print(f"[notify] issue created: {url}")
    return url


def telegram(chunks: list[str]) -> bool:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[notify] TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set, skipping telegram")
        return False
    for i, text in enumerate(chunks):
        post_json(f"https://api.telegram.org/bot{token}/sendMessage",
                  {"chat_id": chat, "text": text, "parse_mode": "HTML",
                   "disable_web_page_preview": True})
        if i + 1 < len(chunks):
            time.sleep(1.1)  # stay under Telegram's per-chat rate limit
    print(f"[notify] telegram: sent {len(chunks)} message(s)")
    return True
