"""Client HTTP politicos: 1 cerere/secundă/domeniu, User-Agent explicit, reîncercări rare, cache pe disc.

Cache-ul brut stă în data/raw/<namespace>/ (gitignored). O rerulare citește din cache și nu atinge rețeaua.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from pipeline.config import MIN_INTERVAL_S, RAW, USER_AGENT

log = logging.getLogger(__name__)

_last_request: dict[str, float] = {}
_client: httpx.Client | None = None


def client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
            timeout=httpx.Timeout(90.0, connect=20.0),
            follow_redirects=True,
        )
    return _client


def _throttle(host: str) -> None:
    wait = _last_request.get(host, 0.0) + MIN_INTERVAL_S - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_request[host] = time.monotonic()


def cache_path(namespace: str, key: str, suffix: str = ".json") -> Path:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return RAW / namespace / digest[:2] / f"{digest}{suffix}"


def request(method: str, url: str, *, params: dict[str, Any] | None = None,
            data: dict[str, Any] | None = None, max_tries: int = 4) -> httpx.Response:
    host = urlsplit(url).netloc
    delay = 5.0
    for attempt in range(1, max_tries + 1):
        _throttle(host)
        try:
            resp = client().request(method, url, params=params, data=data)
        except httpx.TransportError as exc:
            log.warning("%s %s: %s (încercarea %d)", method, url, exc, attempt)
        else:
            if resp.status_code == 200:
                return resp
            if resp.status_code not in (429, 500, 502, 503, 504):
                resp.raise_for_status()
            retry_after = resp.headers.get("Retry-After", "")
            if retry_after.isdigit():
                delay = max(delay, float(retry_after))
            log.warning("%s %s -> HTTP %s (încercarea %d), aștept %.0fs",
                        method, url, resp.status_code, attempt, delay)
        if attempt == max_tries:
            break
        time.sleep(delay)
        delay *= 2
    raise RuntimeError(f"Cererea a eșuat după {max_tries} încercări: {method} {url}")


def today() -> str:
    return time.strftime("%Y-%m-%d")


def cached_json(namespace: str, key: str, fetch, *, refresh: bool = False) -> Any:
    """Întoarce JSON din cache sau apelează fetch() -> obiect JSON și îl salvează."""
    path = cache_path(namespace, key)
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    obj = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"key": key, "retrieved_at": time.strftime("%Y-%m-%d"), "data": obj},
                              ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return json.loads(path.read_text(encoding="utf-8"))
