"""Small cached GET helper. No API keys. Cache lives under scripts/.cache/."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent / ".cache"
USER_AGENT = "qwen21-anime-style-catalog/0.1 (public metadata; no-download)"


def cache_path(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return CACHE_DIR / f"{digest}.json"


def get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    refresh: bool = False,
    delay_s: float = 0.45,
    timeout: float = 45,
) -> dict:
    path = cache_path(url)
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code in {429, 500, 502, 503, 504}:
                time.sleep(2.5 * (attempt + 1))
                continue
            raise
        except urllib.error.URLError as exc:
            last_err = exc
            time.sleep(1.5 * (attempt + 1))
    else:
        raise RuntimeError(f"GET failed: {url}") from last_err

    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    time.sleep(delay_s)
    return payload
