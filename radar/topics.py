"""User-defined topics (config `topics:`) followed in addition to new models."""
from __future__ import annotations

import re


def matches(text: str, keywords: list[str]) -> bool:
    """Case-insensitive match where each keyword must start a word, so that
    "GPT" does not match "ChatGPT" and "모델" does not match "수치모델"."""
    return any(re.search(r"(?<![\w])" + re.escape(k), text, re.IGNORECASE)
               for k in keywords)


def match(text: str, topics: list[dict]) -> list[str]:
    """Names of the topics whose keywords appear in `text`."""
    return [t["name"] for t in topics or [] if matches(text, t.get("keywords", []))]
