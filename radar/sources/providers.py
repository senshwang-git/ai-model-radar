from __future__ import annotations

import os
import urllib.parse

from ..http import get_json
from ..models import Item


def _openai_compatible(base: str, key: str) -> list[tuple[str, str]]:
    data = get_json(base, headers={"Authorization": f"Bearer {key}"})
    return [(m["id"], "") for m in data.get("data", [])]


def _anthropic(key: str) -> list[tuple[str, str]]:
    out, after = [], None
    while True:
        url = "https://api.anthropic.com/v1/models?limit=1000"
        if after:
            url += "&after_id=" + urllib.parse.quote(after)
        data = get_json(url, headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
        out += [(m["id"], m.get("display_name", "")) for m in data.get("data", [])]
        if not data.get("has_more"):
            return out
        after = data.get("last_id")


def _gemini(key: str) -> list[tuple[str, str]]:
    out, token = [], None
    while True:
        url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000"
        if token:
            url += "&pageToken=" + urllib.parse.quote(token)
        data = get_json(url, headers={"x-goog-api-key": key})
        out += [(m["name"].removeprefix("models/"), m.get("displayName", ""))
                for m in data.get("models", [])]
        token = data.get("nextPageToken")
        if not token:
            return out


PROVIDERS = {
    "openai": (lambda k: _openai_compatible("https://api.openai.com/v1/models", k),
               "https://platform.openai.com/docs/models"),
    "anthropic": (_anthropic, "https://docs.anthropic.com/en/docs/about-claude/models"),
    "gemini": (_gemini, "https://ai.google.dev/gemini-api/docs/models"),
    "mistral": (lambda k: _openai_compatible("https://api.mistral.ai/v1/models", k),
                "https://docs.mistral.ai/getting-started/models/"),
    "xai": (lambda k: _openai_compatible("https://api.x.ai/v1/models", k),
            "https://docs.x.ai/docs/models"),
    "deepseek": (lambda k: _openai_compatible("https://api.deepseek.com/models", k),
                 "https://api-docs.deepseek.com/quick_start/pricing"),
}


def collect(cfg: dict) -> list[Item]:
    items: list[Item] = []
    for name, (fn, docs_url) in PROVIDERS.items():
        pcfg = cfg.get(name)
        if not pcfg:
            continue
        key = os.environ.get(pcfg.get("env", ""), "")
        if not key:
            print(f"[providers] {name}: {pcfg.get('env')} not set, skipping")
            continue
        try:
            models = fn(key)
        except Exception as e:
            print(f"[providers] {name}: error {e}")
            continue
        for mid, display in models:
            items.append(Item(source="providers", key=mid, title=mid, group=name,
                              url=docs_url, detail=display if display != mid else ""))
    return items
