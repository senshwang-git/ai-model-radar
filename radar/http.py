from __future__ import annotations

import gzip
import json
import time
import zlib
import urllib.error
import urllib.request

USER_AGENT = "ai-model-radar/0.1 (+https://github.com/senshwang-git/ai-model-radar)"
# Some sites serve bot-challenge pages to unknown agents; feeds retry with this.
BROWSER_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")


def decode_body(body: bytes, encoding: str = "") -> bytes:
    """Undo gzip/deflate, also when a server compresses without saying so."""
    encoding = (encoding or "").lower()
    try:
        if "gzip" in encoding or body[:2] == b"\x1f\x8b":
            return gzip.decompress(body)
        if "deflate" in encoding:
            try:
                return zlib.decompress(body)
            except zlib.error:
                return zlib.decompress(body, -zlib.MAX_WBITS)  # raw deflate
    except (OSError, EOFError, zlib.error):
        pass
    return body


def fetch_response(url: str, headers: dict | None = None, data: bytes | None = None,
                   method: str | None = None, timeout: int = 30,
                   retries: int = 3) -> tuple[bytes, dict]:
    """Return (decoded body, lower-cased response headers)."""
    hdrs = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}
    hdrs.update(headers or {})
    last_err: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                body = decode_body(resp.read(), resp_headers.get("content-encoding", ""))
                return body, resp_headers
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


def fetch(url: str, headers: dict | None = None, **kw) -> bytes:
    return fetch_response(url, headers=headers, **kw)[0]


def get_json(url: str, headers: dict | None = None, **kw):
    h = {"Accept": "application/json"}
    h.update(headers or {})
    return json.loads(fetch(url, headers=h, **kw))


def post_json(url: str, payload: dict, headers: dict | None = None, **kw):
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    h.update(headers or {})
    body = fetch(url, headers=h, data=json.dumps(payload).encode(), method="POST", **kw)
    return json.loads(body) if body else None
