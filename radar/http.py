from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

USER_AGENT = "ai-model-radar/0.1 (+https://github.com/senshwang-git/ai-model-radar)"


def fetch(url: str, headers: dict | None = None, data: bytes | None = None,
          method: str | None = None, timeout: int = 30, retries: int = 3) -> bytes:
    hdrs = {"User-Agent": USER_AGENT}
    hdrs.update(headers or {})
    last_err: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last_err = e
            # 4xx (other than rate limiting) will not succeed on retry.
            if e.code < 500 and e.code != 429:
                break
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
        time.sleep(2 ** attempt)
    assert last_err is not None
    raise last_err


def get_json(url: str, headers: dict | None = None, **kw):
    h = {"Accept": "application/json"}
    h.update(headers or {})
    return json.loads(fetch(url, headers=h, **kw))


def post_json(url: str, payload: dict, headers: dict | None = None, **kw):
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    h.update(headers or {})
    body = fetch(url, headers=h, data=json.dumps(payload).encode(), method="POST", **kw)
    return json.loads(body) if body else None
