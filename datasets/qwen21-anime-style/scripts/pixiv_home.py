"""Pure helpers for a home-machine Pixiv URL collection.

The Windows entry point is collect_pixiv_windows.py. These functions do not
open a browser, read cookies, or write secrets. R-18 queries are an allowlist
that must pass scripts/safety.py before they are used.
"""

from __future__ import annotations

import re
import time
from collections import Counter
from collections.abc import Callable

from safety import has_person_signal, screen, style_notes

# Adult-coded original illustrations. School, age, and child-coded words are
# rejected by validate_queries before any request is built.
ADULT_R18_QUERIES = [
    "お姉さん オリジナル",
    "熟女 オリジナル",
    "人妻 オリジナル",
    "長身 女性 オリジナル",
    "巨乳 女性 オリジナル",
]

FetchJson = Callable[[str], dict]

_SECRET_KEY = re.compile(r"(?i)cookie|token|authorization|password|secret|phpsessid|sessionid")
_SECRET_VALUE = re.compile(r"(?i)phpsessid=|cookie:|refresh_token|bearer\s+")

ROW_KEYS = (
    "source",
    "url",
    "image_url",
    "id",
    "title",
    "tags",
    "rating",
    "style_notes",
    "keep_reason",
    "width",
    "height",
    "author",
    "nsfw_level",
    "ai_generated",
    "base_model",
    "quality",
    "visual_review",
    "collected_via",
    "screen",
    "user_id",
)

MAX_PAGES = 3
MIN_SHORT = 768
MIN_LONG = 1024


def validate_queries(queries: list[str]) -> None:
    for query in queries:
        ok, why = screen(query)
        if not ok:
            raise RuntimeError(f"Refusing unsafe Pixiv query {query!r}: {why}")


def sanitize_row(row: dict) -> dict:
    """Keep the public catalog fields only. Drop anything that looks like a secret."""
    clean: dict = {}
    for key in ROW_KEYS:
        if key not in row or _SECRET_KEY.search(key):
            continue
        value = row[key]
        if isinstance(value, str) and _SECRET_VALUE.search(value):
            continue
        if isinstance(value, list):
            value = [item for item in value if not (isinstance(item, str) and _SECRET_VALUE.search(item))]
        clean[key] = value
    return clean


def pixiv_block_reason(status: int, text: str) -> str | None:
    sample = (text or "")[:800].lower()
    if status in {401, 403, 451}:
        return f"http_{status}"
    for marker in (
        "access to this page is denied",
        "not available in your country",
        "unavailable in your region",
        "access denied",
    ):
        if marker in sample:
            return "datacenter_or_region_block"
    return None


def bookmark_url(user_id: str, offset: int, rest: str) -> str:
    return (
        "https://www.pixiv.net/ajax/user/"
        f"{user_id}/illusts/bookmarks?tag=&offset={offset}&limit=48&rest={rest}&lang=en"
    )


def search_page_url(word: str, page: int) -> str:
    from fetch_pixiv import search_url

    return search_url(word, page, "r18")


def illust_tags(body: dict) -> list[str]:
    raw = ((body.get("tags") or {}).get("tags") or body.get("tags") or [])
    tags: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            tag = item.get("tag") or ""
        else:
            tag = str(item or "")
        if tag:
            tags.append(tag)
    return tags


def row_from_illust_body(body: dict, *, include_ai: bool = False) -> tuple[dict | None, str]:
    """Turn one illust ajax body into a catalog row, or (None, reason)."""
    if not isinstance(body, dict) or not body or body.get("isMasked"):
        return None, "masked"
    try:
        restrict = int(body.get("xRestrict") or 0)
    except (TypeError, ValueError):
        return None, "bad_restrict"
    if restrict >= 2:
        return None, "r18g"
    if body.get("aiType") == 2 and not include_ai:
        return None, "ai_generated"
    artwork_id = str(body.get("id") or body.get("illustId") or "")
    if not artwork_id.isdigit():
        return None, "no_id"
    tags = illust_tags(body)
    title = str(body.get("title") or "")
    description = str(body.get("description") or body.get("illustComment") or body.get("alt") or "")
    blob = " ".join([title, description, " ".join(tags)])
    ok, why = screen(blob, tags, lo_flag=bool(body.get("lo")))
    if not ok:
        return None, why
    if not has_person_signal(blob, tags):
        return None, "no_person"
    pages = int(body.get("pageCount") or 1)
    if pages > MAX_PAGES:
        return None, "multi_page"
    width = int(body.get("width") or 0)
    height = int(body.get("height") or 0)
    if width and height:
        long_edge, short_edge = max(width, height), min(width, height)
        if long_edge < MIN_LONG or short_edge < MIN_SHORT:
            return None, "small"
    else:
        long_edge = 0
    # Safe-mode pages stay all-ages. Restricted works (xRestrict 1) are adult.
    rating = "adult" if restrict >= 1 else "all-ages"
    notes = style_notes(" ".join(tags + [title]), rating=rating)
    urls = body.get("urls") or {}
    image_url = ""
    if isinstance(urls, dict):
        image_url = urls.get("small") or urls.get("regular") or ""
    bookmarks = int(body.get("bookmarkCount") or 0)
    row = sanitize_row(
        {
            "source": "pixiv",
            "url": f"https://www.pixiv.net/artworks/{artwork_id}",
            "image_url": image_url,
            "id": artwork_id,
            "title": title[:120],
            "tags": tags[:16],
            "rating": rating,
            "style_notes": notes,
            "keep_reason": (
                "Home-machine Pixiv export. Metadata screen passed. "
                "Full-size human review is required before download or training."
            ),
            "width": width,
            "height": height,
            "author": str(body.get("userName") or ""),
            "nsfw_level": "R-18" if restrict >= 1 else "None",
            "ai_generated": "yes" if body.get("aiType") == 2 else ("no" if body.get("aiType") == 1 else "unknown"),
            "base_model": "",
            "quality": bookmarks or long_edge,
            "visual_review": "pending",
            "collected_via": "windows_chrome_profile_copy",
            "screen": why,
            "user_id": str(body.get("userId") or ""),
        }
    )
    return row, "pass"


def iter_bookmark_works(
    fetch_json: FetchJson,
    user_id: str,
    *,
    rest: str,
    limit: int,
) -> list[dict]:
    if not str(user_id).isdigit():
        raise RuntimeError("Pixiv user id must be digits. Pass --user-id from your profile URL.")
    works: list[dict] = []
    offset = 0
    while len(works) < limit:
        payload = fetch_json(bookmark_url(user_id, offset, rest))
        if payload.get("error"):
            message = str(payload.get("message") or "bookmark request failed")
            raise RuntimeError(message)
        body = payload.get("body") or {}
        batch = body.get("works") or []
        if not batch:
            break
        works.extend(batch)
        offset += len(batch)
        total = int(body.get("total") or 0)
        if total and offset >= total:
            break
        if len(batch) < 48:
            break
    return works[:limit]


def iter_r18_search(
    fetch_json: FetchJson,
    queries: list[str],
    *,
    pages: int,
    limit: int,
) -> tuple[list[dict], int]:
    """Return restricted stubs and how many queries came back safe-mode only.

    Public Pixiv answers mode=r18 with xRestrict=0 unless the viewer is logged
    in. Those stand-ins are not an R-18 collection, so they are not kept.
    """
    validate_queries(queries)
    found: list[dict] = []
    seen: set[str] = set()
    masked_queries = 0
    for word in queries:
        for page in range(1, pages + 1):
            payload = fetch_json(search_page_url(word, page))
            if payload.get("error"):
                break
            data = ((payload.get("body") or {}).get("illust") or {}).get("data") or []
            if not data:
                break
            restricted_on_page = 0
            for item in data:
                if item.get("xRestrict") in (0, "0", None):
                    continue
                try:
                    if int(item.get("xRestrict") or 0) >= 2:
                        continue
                except (TypeError, ValueError):
                    continue
                restricted_on_page += 1
                artwork_id = str(item.get("id") or "")
                if not artwork_id or artwork_id in seen:
                    continue
                seen.add(artwork_id)
                found.append(item)
                if len(found) >= limit:
                    return found, masked_queries
            if restricted_on_page == 0:
                masked_queries += 1
                break
    return found, masked_queries


def collect_rows_from_stubs(
    stubs: list[dict],
    fetch_json: FetchJson,
    *,
    include_ai: bool,
    dropped: Counter | None = None,
    delay_s: float = 0,
) -> list[dict]:
    """Fetch illust details and keep rows that pass the age screen."""
    from fetch_pixiv import illust_url

    stats = dropped if dropped is not None else Counter()
    rows: list[dict] = []
    seen: set[str] = set()
    for stub in stubs:
        artwork_id = str(stub.get("id") or stub.get("illustId") or "")
        if not artwork_id.isdigit() or artwork_id in seen:
            continue
        seen.add(artwork_id)
        if delay_s:
            time.sleep(delay_s)
        try:
            detail = fetch_json(illust_url(artwork_id))
        except Exception:  # noqa: BLE001 - caller records a count, not the body
            stats["detail_fetch"] += 1
            continue
        body = detail.get("body") if isinstance(detail, dict) else None
        if not isinstance(body, dict):
            body = detail if isinstance(detail, dict) and detail.get("id") else None
        if not isinstance(body, dict):
            stats["detail_fetch"] += 1
            continue
        row, why = row_from_illust_body(body, include_ai=include_ai)
        if row is None:
            stats[why] += 1
            continue
        rows.append(row)
    return rows
