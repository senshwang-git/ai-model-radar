"""Post-processing with Claude: keep real model releases and write a Korean digest."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field

from .models import Item

SYSTEM_PROMPT = """\
You are the editor of a daily Korean-language briefing on newly released AI models,
read by an engineer who works on LLM serving systems.

You receive a JSON list of items collected automatically from Hugging Face model
uploads, provider model APIs, GitHub releases of serving frameworks, papers, and AI
news feeds. Most items are noise. Your job:

1. `releases`: genuinely new AI models announced or released in these items (new
   model families, new versions, new open-weight checkpoints, new API models).
   - Merge items about the same model into one entry (a news article plus the
     Hugging Face repo, or several outlets covering the same launch).
   - Exclude quantized/converted re-uploads, fine-tunes by individuals, adapters,
     product features, business news, ads, funding, policy, opinion pieces, and
     papers that merely use or study existing models.
   - A paper counts only if it introduces a named model (e.g. a technical report).
2. `notable`: at most 5 other items worth a glance for an LLM-serving engineer,
   e.g. a major release of vLLM / SGLang / TensorRT-LLM / llama.cpp, or a
   significant serving/efficiency paper. Leave empty if nothing qualifies.
3. Everything else is dropped silently.

Write all prose in natural, concise Korean. Keep model, company, and product names in
their original form. Put concrete facts in `specs` (parameter count, active
parameters, architecture such as MoE, context length, modality, license,
open-weight vs API-only) only when the items state them; never invent numbers.
`item_ids` must reference the input ids that support each entry.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {
            "type": "string",
            "description": "One Korean sentence summarizing the day. If there are no "
                           "releases, say so plainly.",
        },
        "releases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "org": {"type": "string"},
                    "summary_ko": {"type": "string",
                                   "description": "1-2 Korean sentences."},
                    "specs": {"type": "string",
                              "description": "Short Korean/English spec line, or ''."},
                    "item_ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["name", "org", "summary_ko", "specs", "item_ids"],
                "additionalProperties": False,
            },
        },
        "notable": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title_ko": {"type": "string"},
                    "summary_ko": {"type": "string", "description": "One Korean sentence."},
                    "item_ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["title_ko", "summary_ko", "item_ids"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["headline", "releases", "notable"],
    "additionalProperties": False,
}


@dataclass
class Entry:
    title: str
    summary: str
    specs: str = ""
    items: list[Item] = field(default_factory=list)


@dataclass
class Digest:
    headline: str
    releases: list[Entry]
    notable: list[Entry]


def _payload(items: list[Item]) -> str:
    rows = [{"id": i, "source": it.source, "where": it.group, "title": it.title,
             "detail": it.detail[:400], "date": it.published, "url": it.url}
            for i, it in enumerate(items)]
    return json.dumps(rows, ensure_ascii=False)


def _resolve(ids: list[int], items: list[Item]) -> list[Item]:
    return [items[i] for i in dict.fromkeys(ids) if 0 <= i < len(items)]


def parse_digest(data: dict, items: list[Item]) -> Digest:
    releases = [Entry(title=f"{r['name']} · {r['org']}" if r.get("org") else r["name"],
                      summary=r["summary_ko"], specs=r.get("specs", ""),
                      items=_resolve(r.get("item_ids", []), items))
                for r in data.get("releases", [])]
    notable = [Entry(title=n["title_ko"], summary=n["summary_ko"],
                     items=_resolve(n.get("item_ids", []), items))
               for n in data.get("notable", [])]
    return Digest(headline=data.get("headline", ""), releases=releases, notable=notable)


def _token_kind(tok: str) -> str:
    """Non-secret description of a credential's type (never prints the value)."""
    tok = tok.strip()
    if tok.startswith("sk-ant-oat"):
        kind = "subscription OAuth token (sk-ant-oat…)"
    elif tok.startswith("sk-ant-api"):
        kind = "API key (sk-ant-api…) — bills API credits, not the subscription"
    elif tok.startswith("sk-ant-admin"):
        kind = "Admin API key"
    else:
        kind = "unrecognized format"
    return f"{kind}, len={len(tok)}"


def _call_cli(items: list[Item], cfg: dict) -> dict | None:
    """Claude Code CLI with CLAUDE_CODE_OAUTH_TOKEN (Pro/Max subscription)."""
    exe = shutil.which("claude")
    if not exe:
        print("[digest] claude CLI not installed")
        return None
    cmd = [exe, "-p", "--output-format", "json", "--json-schema", json.dumps(SCHEMA),
           "--model", cfg.get("model", "claude-opus-5-5"), "--system-prompt", SYSTEM_PROMPT,
           "--tools", "", "--no-session-persistence"]
    try:
        # ANTHROPIC_API_KEY outranks the OAuth token in the CLI's credential
        # order, so drop it here to make the CLI bill the subscription.
        env = {k: v for k, v in os.environ.items()
               if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
        proc = subprocess.run(cmd, input=_payload(items), capture_output=True, text=True,
                              timeout=int(cfg.get("timeout", 600)), env=env)
    except subprocess.TimeoutExpired:
        print("[digest] claude CLI timed out")
        return None
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(f"[digest] claude CLI failed (exit {proc.returncode}): "
              f"{(proc.stderr or proc.stdout)[-500:]}")
        return None
    if out.get("is_error") or not isinstance(out.get("structured_output"), dict):
        print(f"[digest] claude CLI error: {out.get('subtype')} {str(out.get('result'))[:300]} "
              f"[token: {_token_kind(os.environ.get('CLAUDE_CODE_OAUTH_TOKEN', ''))}]")
        return None
    print(f"[digest] via claude CLI; turns={out.get('num_turns')} "
          f"cost_equiv=${out.get('total_cost_usd', 0):.3f}")
    return out["structured_output"]


def _call_api(items: list[Item], cfg: dict) -> dict | None:
    """Anthropic API with ANTHROPIC_API_KEY (billed API credits)."""
    import anthropic  # imported lazily so the rest works without the package

    client = anthropic.Anthropic()
    try:
        response = client.beta.messages.create(
            model=cfg.get("model", "claude-opus-5-5"),
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM_PROMPT,
            output_config={"effort": cfg.get("effort", "medium"),
                           "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": _payload(items)}],
        )
    except anthropic.APIStatusError as e:
        print(f"[digest] API error {e.status_code}: {e.message}")
        return None
    except anthropic.APIConnectionError as e:
        print(f"[digest] connection error: {e}")
        return None
    if response.stop_reason in ("refusal", "max_tokens"):
        print(f"[digest] unusable response (stop_reason={response.stop_reason})")
        return None
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"[digest] could not parse response: {e}")
        return None
    print(f"[digest] via API; tokens in={response.usage.input_tokens} "
          f"out={response.usage.output_tokens}")
    return data


def build(items: list[Item], cfg: dict) -> Digest | None:
    """Return a Korean digest, or None when Claude is unavailable or fails.

    Prefers the subscription (CLAUDE_CODE_OAUTH_TOKEN via the claude CLI), then
    the API (ANTHROPIC_API_KEY)."""
    if not cfg.get("enabled", True) or not items:
        return None
    items = items[: int(cfg.get("max_items", 400))]
    callers = []
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        callers.append(_call_cli)
    if os.environ.get("ANTHROPIC_API_KEY"):
        callers.append(_call_api)
    if not callers:
        print("[digest] no CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY; sending raw list")
        return None
    for call in callers:
        data = call(items, cfg)
        if data is None:
            continue
        try:
            digest = parse_digest(data, items)
        except (KeyError, TypeError) as e:
            print(f"[digest] unexpected digest shape: {e}")
            continue
        print(f"[digest] {len(digest.releases)} release(s), {len(digest.notable)} notable "
              f"from {len(items)} item(s)")
        return digest
    return None
