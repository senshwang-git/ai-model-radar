import json

import pytest


@pytest.fixture(autouse=True)
def _no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

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
    assert "수집 1건" in sent[0][1]
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


def test_clean_token():
    from radar.notify import TOKEN_RE, clean_token, describe_token
    good = "123456789:AAHabcdefghijklmnopqrstuvwxyz012345"
    for raw in (good, f" {good}\n", f"bot{good}", f'"{good}"'):
        assert clean_token(raw) == good
    assert TOKEN_RE.match(good)
    d = describe_token("x y")
    assert "format_ok=False" in d and "had_whitespace=True" in d


def test_to_date_formats():
    from radar.models import to_date
    assert to_date("2026-10-05T23:30:00Z") == "2026-10-05"
    assert to_date("2026-10-06T08:00:00+09:00") == "2026-10-05"  # KST -> UTC
    assert to_date("Mon, 05 Oct 2026 10:00:00 GMT") == "2026-10-05"
    assert to_date(1791158400) == "2026-10-05"
    assert to_date("garbage") == "" and to_date(None) == ""


def test_cli_lookback_ignores_state(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("news:\n  enabled: true\nnotify: {}\n")
    state = tmp_path / "s.json"
    state.write_text(json.dumps({"buckets": ["news/F"], "seen": {"news": ["a", "b"]}}))

    class FakeNews:
        @staticmethod
        def collect(_):
            return [Item("news", "a", "yesterday-1", group="F", published="2026-10-05"),
                    Item("news", "b", "older", group="F", published="2026-10-01"),
                    Item("news", "c", "undated", group="F")]

    monkeypatch.setattr(cli, "SOURCES", {"news": FakeNews})
    monkeypatch.setattr(cli.notify, "github_issue", lambda *a: pytest.fail("notified"))
    before = state.read_text()
    assert cli.main(["--config", str(cfg), "--state", str(state), "--since", "2026-10-05"]) == 0
    out = capsys.readouterr().out
    assert "yesterday-1" in out and "older" not in out and "1 had no publish date" in out
    assert state.read_text() == before


def test_cli_lookback_send_telegram(tmp_path, monkeypatch):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("news:\n  enabled: true\nnotify: {}\n")

    class FakeNews:
        @staticmethod
        def collect(_):
            return [Item("news", "a", "hit", group="F", published="2026-10-05")]

    sent = []
    monkeypatch.setattr(cli, "SOURCES", {"news": FakeNews})
    monkeypatch.setattr(cli.notify, "telegram", lambda c: sent.append(c) or True)
    argv = ["--config", str(cfg), "--state", str(tmp_path / "s.json"), "--since", "2026-10-05"]
    assert cli.main(argv) == 0 and sent == []
    assert cli.main(argv + ["--send-telegram"]) == 0
    assert "hit" in sent[0][0] and "다시보기" in sent[0][0]


def _fake_anthropic(monkeypatch, payload, stop_reason="end_turn"):
    import sys
    import types

    calls = []

    class Block:
        type = "text"
        text = json.dumps(payload)

    class Resp:
        content = [Block()]
        usage = types.SimpleNamespace(input_tokens=10, output_tokens=5)

    Resp.stop_reason = stop_reason

    class Messages:
        def create(self, **kw):
            calls.append(kw)
            return Resp()

    class Client:
        def __init__(self):
            self.beta = types.SimpleNamespace(messages=Messages())

    mod = types.SimpleNamespace(Anthropic=Client, APIStatusError=RuntimeError,
                                APIConnectionError=ConnectionError)
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    return calls


def test_digest_build_and_render(monkeypatch):
    from radar import digest
    items = [Item("news", "1", "Reflection debuts Beam", url="https://tc/beam", group="TechCrunch AI"),
             Item("news", "2", "OpenAI adds ads", url="https://v/ads", group="The Verge AI"),
             Item("github_releases", "vllm@v1", "vllm v1", url="https://gh/v1", group="vllm")]
    calls = _fake_anthropic(monkeypatch, {
        "headline": "Reflection AI가 Beam을 공개했습니다.",
        "releases": [{"name": "Beam", "org": "Reflection AI", "summary_ko": "501B MoE 오픈 웨이트 모델.",
                      "specs": "501B MoE, 활성 23B", "item_ids": [0, 0, 99]}],
        "notable": [{"title_ko": "vLLM v1", "summary_ko": "새 릴리스.", "item_ids": [2]}]})
    d = digest.build(items, {"model": "claude-opus-5-5"})
    assert calls[0]["model"] == "claude-opus-5-5"
    assert calls[0]["output_config"]["format"]["type"] == "json_schema"
    assert [i.key for i in d.releases[0].items] == ["1"]  # deduped, bad id dropped
    tg = report.digest_telegram(d, "title")
    assert "Beam · Reflection AI" in tg[0] and "TechCrunch AI" in tg[0] and "ads" not in tg[0]
    md = report.digest_markdown(d, items, {})
    assert "신규 모델 (1)" in md and "수집된 전체 항목 (3)" in md


def test_digest_falls_back_without_key_or_on_refusal(monkeypatch):
    from radar import digest
    items = [Item("news", "1", "x")]
    assert digest.build(items, {}) is None  # no key (autouse fixture)
    _fake_anthropic(monkeypatch, {}, stop_reason="refusal")
    assert digest.build(items, {}) is None


def test_cli_skips_notification_when_digest_finds_nothing(tmp_path, monkeypatch):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("news:\n  enabled: true\nnotify: {}\n")
    state = tmp_path / "s.json"
    state.write_text(json.dumps({"buckets": ["news/F"], "seen": {"news": []}}))

    class FakeNews:
        @staticmethod
        def collect(_):
            return [Item("news", "9", "OpenAI adds ads", group="F")]

    _fake_anthropic(monkeypatch, {"headline": "새 모델 없음", "releases": [], "notable": []})
    monkeypatch.setattr(cli, "SOURCES", {"news": FakeNews})
    monkeypatch.setattr(cli.notify, "github_issue", lambda *a: pytest.fail("notified"))
    monkeypatch.setattr(cli.notify, "telegram", lambda *a: pytest.fail("notified"))
    assert cli.main(["--config", str(cfg), "--state", str(state)]) == 0
    assert json.loads(state.read_text())["seen"]["news"] == ["9"]


def _fake_cli(monkeypatch, stdout, returncode=0):
    import subprocess
    import types
    from radar import digest
    calls = []

    def run(cmd, **kw):
        calls.append((cmd, kw))
        return types.SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)

    monkeypatch.setattr(digest.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(digest.subprocess, "run", run)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    return calls


def test_digest_via_cli_subscription(monkeypatch):
    from radar import digest
    payload = {"headline": "h", "releases": [{"name": "Beam", "org": "R", "summary_ko": "s",
                                              "specs": "", "item_ids": [0]}], "notable": []}
    calls = _fake_cli(monkeypatch, json.dumps({"is_error": False, "num_turns": 2,
                                               "structured_output": payload}))
    d = digest.build([Item("news", "1", "Beam", url="u", group="TC")], {"model": "claude-opus-5-5"})
    cmd, kw = calls[0]
    assert "--json-schema" in cmd and cmd[cmd.index("--tools") + 1] == ""
    assert '"title": "Beam"' in kw["input"]
    assert d.releases[0].title == "Beam · R"


def test_digest_cli_failure_falls_back_to_api(monkeypatch):
    from radar import digest
    _fake_cli(monkeypatch, "not json", returncode=1)
    api_calls = _fake_anthropic(monkeypatch, {"headline": "h", "releases": [], "notable": []})
    d = digest.build([Item("news", "1", "x")], {})
    assert d is not None and len(api_calls) == 1
