from __future__ import annotations

import html
from collections import OrderedDict

from .models import Item

SECTIONS = OrderedDict([
    ("huggingface", "🤗 Hugging Face models"),
    ("providers", "🔌 Provider API models"),
    ("github_releases", "📦 Serving / framework releases"),
    ("papers", "📄 Papers"),
    ("news", "📰 News"),
])


def _grouped(items: list[Item]):
    by_src: dict[str, dict[str, list[Item]]] = OrderedDict()
    for src in SECTIONS:
        for it in items:
            if it.source == src:
                by_src.setdefault(src, OrderedDict()).setdefault(it.group, []).append(it)
    return by_src


def markdown(items: list[Item], errors: dict[str, str], max_len: int = 60000) -> str:
    lines: list[str] = []
    for src, groups in _grouped(items).items():
        n = sum(len(v) for v in groups.values())
        lines.append(f"## {SECTIONS[src]} ({n})\n")
        for group, its in groups.items():
            lines.append(f"**{group}**\n")
            for it in its:
                title = it.title.replace("[", "\\[").replace("]", "\\]")
                entry = f"- [{title}]({it.url})" if it.url else f"- {title}"
                if it.detail:
                    entry += f" — {it.detail}"
                lines.append(entry)
            lines.append("")
    if errors:
        lines.append("<details><summary>⚠️ Source errors</summary>\n")
        lines += [f"- `{s}`: {e}" for s, e in errors.items()]
        lines.append("\n</details>")
    body = "\n".join(lines)
    if len(body) > max_len:
        body = body[:max_len].rsplit("\n", 1)[0] + "\n\n… (truncated)"
    return body


def telegram_chunks(items: list[Item], header: str, limit: int = 4000) -> list[str]:
    """Telegram HTML messages, each under the 4096-char limit."""
    e = html.escape
    lines = [f"<b>{e(header)}</b>"]
    for src, groups in _grouped(items).items():
        lines.append("")
        lines.append(f"<b>{e(SECTIONS[src])}</b>")
        for group, its in groups.items():
            lines.append(f"<i>{e(group)}</i>")
            for it in its:
                t = e(it.title[:200])
                line = f'• <a href="{e(it.url, quote=True)}">{t}</a>' if it.url else f"• {t}"
                if it.detail and src != "news":
                    line += f" — {e(it.detail[:80])}"
                lines.append(line)

    chunks, cur = [], ""
    for line in lines:
        if cur and len(cur) + len(line) + 1 > limit:
            chunks.append(cur)
            cur = ""
        cur = f"{cur}\n{line}" if cur else line[:limit]
    if cur:
        chunks.append(cur)
    return chunks
