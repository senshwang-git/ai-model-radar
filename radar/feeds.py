"""Minimal RSS 2.0 / Atom parser (stdlib only)."""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class Entry:
    id: str
    title: str
    link: str
    summary: str
    published: str


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(el: ET.Element, name: str) -> ET.Element | None:
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _text(el: ET.Element, *names: str) -> str:
    for n in names:
        c = _child(el, n)
        if c is not None and (c.text or "").strip():
            return c.text.strip()
    return ""


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub(" ", s or ""))).strip()


def parse(data: bytes) -> list[Entry]:
    root = ET.fromstring(data)
    out: list[Entry] = []
    for el in root.iter():
        kind = _local(el.tag)
        if kind == "item":  # RSS 2.0 / RSS 1.0
            link = _text(el, "link")
            guid = _text(el, "guid") or link
            out.append(Entry(id=guid, title=clean(_text(el, "title")), link=link,
                             summary=clean(_text(el, "description", "encoded")),
                             published=_text(el, "pubDate", "date")))
        elif kind == "entry":  # Atom
            link = ""
            for c in el:
                if _local(c.tag) == "link" and c.get("rel", "alternate") == "alternate":
                    link = c.get("href", "")
                    break
            out.append(Entry(id=_text(el, "id") or link, title=clean(_text(el, "title")),
                             link=link, summary=clean(_text(el, "summary", "content")),
                             published=_text(el, "published", "updated")))
    return out
