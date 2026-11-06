"""Tiny JSON-over-HTTP helper on the standard library (no extra dependency)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from .base import LLMError


def post_json(url: str, body: dict, *, timeout: float, headers: dict | None = None,
              retries: int = 2) -> dict:
    data = json.dumps(body).encode()
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    last: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:400]
            if e.code in (400, 401, 403, 404, 422):       # caller error: don't retry
                raise LLMError(f"HTTP {e.code} from {url}: {detail}") from e
            last = LLMError(f"HTTP {e.code} from {url}: {detail}")
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last = e
        time.sleep(2 * (attempt + 1))
    raise LLMError(f"Could not reach {url}: {last}")


def get_json(url: str, *, timeout: float = 5, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:  # noqa: BLE001 - status checks just report
        raise LLMError(f"Could not reach {url}: {e}") from e
