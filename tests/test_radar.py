import json

import pytest

from radar import __main__ as cli
from radar import feeds, report
from radar.models import Item
from radar.sources import huggingface, news
from radar.state import State

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Acme releases Foo-2 model</title><link>https://ex.com/a</link>
<guid>a1</guid><description>&lt;p&gt;New open-weight LLM&lt;/p&gt;</description></item>
<item><title>Quarterly earnings</title><link>https://ex.com/b</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><id>tag:x,1</id><title>Hello</title><link rel="alternate" href="https://ex.com/c"/>
<summary>world</summary><updated>2026-10-01</updated></entry></feed>"""


def test_parse_rss_and_atom():
    rss = feeds.parse(RSS)
    assert [e.id for e in rss] == ["a1", "https://ex.com/b"]
    assert rss[0].summary == "New open-weight LLM"
    atom = feeds.parse(ATOM)
    assert atom[0].link == "https://ex.com/c" and atom[0].id == "tag:x,1"


def test_news_filter_requires_release_and_model_keyword():
    cfg = {"release_keywords": ["release"], "model_keywords": ["model"]}
    assert news.is_relevant("Acme releases Foo-2 model", "", cfg)
    assert not news.is_relevant("Acme releases earnings", "", cfg)
    assert not news.is_relevant("A model of the economy", "", cfg)


def test_state_diff_and_new_buckets(tmp_path):
    st = State(tmp_path / "s.json")
    a = Item("huggingface", "Qwen/A", "Qwen/A", group="Qwen")
    b = Item("huggingface", "Qwen/B", "Qwen/B", group="Qwen")
    assert st.diff([a, a]) == [a]
    assert st.is_new_bucket(a)
    st.record([a])
    st.save()
    st2 = State(tmp_path / "s.json")
    assert st2.diff([a, b]) == [b]
    assert not st2.is_new_bucket(b)


def test_telegram_chunks_respect_limit():
    items = [Item("news", str(i), "x" * 150, url=f"https://ex.com/{i}", group="g")
             for i in range(100)]
    chunks = report.telegram_chunks(items, "hdr", limit=1000)
    assert len(chunks) > 1 and all(len(c) <= 1000 for c in chunks)


def test_huggingface_collect(monkeypatch):
    def fake_get_json(url, **kw):
        if "trendingScore" in url:
            return [{"id": "someone/Cool-7B"}, {"id": "Qwen/Dup"}]
        return [{"id": "Qwen/Qwen9-72B", "safetensors": {"total": 72_700_000_000},
                 "pipeline_tag": "text-generation", "createdAt": "2026-10-05T00:00:00Z"},
                {"id": "Qwen/Qwen9-72B-AWQ"}]
    monkeypatch.setattr(huggingface, "get_json", fake_get_json)
    items = huggingface.collect({"authors": ["Qwen"], "trending_top_n": 2,
                                 "exclude_patterns": ["(?i)-(awq|gptq)(-|$)"]})
    assert [i.key for i in items] == ["Qwen/Qwen9-72B", "someone/Cool-7B"]
    assert items[0].detail.startswith("72.7B params")


def test_cli_first_run_is_silent_then_reports(tmp_path, monkeypatch):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("news:\n  enabled: true\nnotify: {}\n")
    state = tmp_path / "s.json"
    batch = [[Item("news", "1", "one", group="Feed")]]

    class FakeNews:
        @staticmethod
        def collect(_):
            return batch[0]

    monkeypatch.setattr(cli, "SOURCES", {"news": FakeNews})
    sent = []
    monkeypatch.setattr(cli.notify, "github_issue", lambda t, b, l: sent.append(("issue", t)))
    monkeypatch.setattr(cli.notify, "telegram", lambda c: sent.append(("tg", c)))

    assert cli.main(["--config", str(cfg), "--state", str(state)]) == 0
    assert sent == []  # first sight of the feed: recorded silently

    batch[0] = [Item("news", "1", "one", group="Feed"), Item("news", "2", "two", group="Feed")]
    assert cli.main(["--config", str(cfg), "--state", str(state)]) == 0
    assert [k for k, _ in sent] == ["issue", "tg"]
    assert "(1)" in sent[0][1]
    assert json.loads(state.read_text())["seen"]["news"] == ["1", "2"]


def test_cli_keeps_state_when_all_notifiers_fail(tmp_path, monkeypatch):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("news:\n  enabled: true\nnotify: {}\n")
    state = tmp_path / "s.json"
    state.write_text(json.dumps({"buckets": ["news/Feed"], "seen": {"news": []}}))

    class FakeNews:
        @staticmethod
        def collect(_):
            return [Item("news", "9", "nine", group="Feed")]

    def boom(*a):
        raise RuntimeError("down")

    monkeypatch.setattr(cli, "SOURCES", {"news": FakeNews})
    monkeypatch.setattr(cli.notify, "github_issue", boom)
    monkeypatch.setattr(cli.notify, "telegram", boom)
    assert cli.main(["--config", str(cfg), "--state", str(state)]) == 1
    assert json.loads(state.read_text())["seen"]["news"] == []


def test_cli_test_telegram(monkeypatch):
    sent = []
    monkeypatch.setattr(cli.notify, "telegram", lambda c: sent.append(c) or True)
    assert cli.main(["--test-telegram"]) == 0
    assert "test message" in sent[0][0]
    monkeypatch.setattr(cli.notify, "telegram", lambda c: False)
    assert cli.main(["--test-telegram"]) == 1
