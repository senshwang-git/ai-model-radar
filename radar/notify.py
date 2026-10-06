from __future__ import annotations

import os
import re
import time
import urllib.error

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


TOKEN_RE = re.compile(r"^\d+:[A-Za-z0-9_-]{30,}$")


def clean_token(raw: str) -> str:
    """Tolerate common paste mistakes: whitespace, quotes, a 'bot' prefix."""
    t = re.sub(r"\s+", "", raw or "").strip("'\"")
    return t[3:] if t.lower().startswith("bot") else t


def describe_token(raw: str) -> str:
    """Non-secret diagnostics about the token's shape (never prints the token)."""
    raw = raw or ""
    t = clean_token(raw)
    ws = bool(re.search(r"\s", raw))
    return (f"raw_len={len(raw)} cleaned_len={len(t)} colon={':' in t} "
            f"format_ok={bool(TOKEN_RE.match(t))} had_whitespace={ws}")


def telegram(chunks: list[str]) -> bool:
    raw = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    token = clean_token(raw)
    chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat:
        print("[notify] TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set, skipping telegram")
        return False
    if not TOKEN_RE.match(token):
        print(f"[notify] warning: TELEGRAM_BOT_TOKEN looks malformed ({describe_token(raw)})")
    for i, text in enumerate(chunks):
        try:
            post_json(f"https://api.telegram.org/bot{token}/sendMessage",
                      {"chat_id": chat, "text": text, "parse_mode": "HTML",
                       "disable_web_page_preview": True})
        except urllib.error.HTTPError as e:
            # Surface Telegram's reason, e.g. "Bad Request: chat not found".
            msg = f"telegram HTTP {e.code}: {e.read().decode(errors='replace')}"
            if e.code == 401:
                msg += f" [token check: {describe_token(raw)}]"
            raise RuntimeError(msg) from None
        if i + 1 < len(chunks):
            time.sleep(1.1)  # stay under Telegram's per-chat rate limit
    print(f"[notify] telegram: sent {len(chunks)} message(s)")
    return True
