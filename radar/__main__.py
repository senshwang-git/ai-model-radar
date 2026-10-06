from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import notify, report
from .sources import SOURCES
from .state import State


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="radar", description="Detect newly released AI models.")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--state", default="state/seen.json")
    ap.add_argument("--only", nargs="*", choices=list(SOURCES), help="run only these sources")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the report; do not notify or update state")
    ap.add_argument("--no-notify", action="store_true", help="update state without notifying")
    ap.add_argument("--since", metavar="YYYY-MM-DD",
                    help="lookback mode: ignore state and list items published on/after "
                         "this UTC date (implies --dry-run)")
    ap.add_argument("--until", metavar="YYYY-MM-DD",
                    help="lookback mode upper bound, inclusive (default: --since)")
    ap.add_argument("--test-telegram", action="store_true",
                    help="send a test message to Telegram and exit")
    args = ap.parse_args(argv)

    if args.test_telegram:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        try:
            ok = notify.telegram([f"🛰️ <b>ai-model-radar</b> test message ({now})\n"
                                  "Telegram notifications are working."])
        except Exception as e:
            print(f"[notify] telegram test failed: {e}")
            ok = False
        return 0 if ok else 1

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    state = State(Path(args.state))

    collected, errors = [], {}
    for name, mod in SOURCES.items():
        scfg = cfg.get(name) or {}
        if not scfg.get("enabled", False) or (args.only and name not in args.only):
            continue
        try:
            items = mod.collect(scfg)
            print(f"[{name}] collected {len(items)} item(s)")
            collected += items
        except Exception as e:
            print(f"[{name}] FAILED: {e}")
            errors[name] = str(e)

    if args.since:
        return lookback(collected, errors, args.since, args.until or args.since)

    fresh = state.diff(collected)
    # Items from orgs/feeds/providers never seen before are recorded silently.
    new = [it for it in fresh if not state.is_new_bucket(it)]
    silent = len(fresh) - len(new)
    print(f"new: {len(new)} (silently recorded first-seen buckets: {silent})")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    title = f"🛰️ New AI models & releases — {today} ({len(new)})"

    if args.dry_run:
        print("\n" + title + "\n\n" + report.markdown(new, errors))
        return 0

    if new and not args.no_notify:
        ncfg = cfg.get("notify", {})
        attempts, failures = 0, 0
        if ncfg.get("github_issue", {}).get("enabled", True):
            attempts += 1
            try:
                notify.github_issue(title, report.markdown(new, errors),
                                    ncfg.get("github_issue", {}).get("labels", []))
            except Exception as e:
                failures += 1
                print(f"[notify] issue failed: {e}")
        if ncfg.get("telegram", {}).get("enabled", True):
            attempts += 1
            try:
                notify.telegram(report.telegram_chunks(new, title))
            except Exception as e:
                failures += 1
                print(f"[notify] telegram failed: {e}")
        if attempts and failures == attempts:
            # Keep state unchanged so the next run retries these items.
            print("[notify] all notifiers failed; state not updated")
            return 1

    state.record(collected)
    state.save()
    # Fail the run only if every enabled source failed.
    return 1 if errors and not collected else 0


def lookback(collected, errors: dict, since: str, until: str) -> int:
    """Report items whose publish date falls in [since, until] (UTC), ignoring state."""
    hits = [it for it in collected if it.published and since <= it.published <= until]
    undated = sum(1 for it in collected if not it.published)
    by_src: dict[str, int] = {}
    for it in hits:
        by_src[it.source] = by_src.get(it.source, 0) + 1
    span = since if since == until else f"{since} ~ {until}"
    title = f"🔎 Lookback {span} (UTC): {len(hits)} item(s)"
    summary = ", ".join(f"{k}={v}" for k, v in by_src.items()) or "none"
    note = (f"_Collected {len(collected)} item(s); {undated} had no publish date and "
            f"were excluded. Per source: {summary}._\n\n")
    body = f"# {title}\n\n{note}{report.markdown(hits, errors)}"
    print("\n" + body)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as f:
            f.write(body + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
