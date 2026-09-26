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
from pathlib import Path

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

# Adult petite / slim / flat originals. Not a child search: each line still
# has to pass safety.py, and ロリ / school / series terms are refused.
PETITE_ADULT_QUERIES = [
    "スレンダー 女性 オリジナル",
    "細身 女性 オリジナル",
    "華奢 お姉さん オリジナル",
    "貧乳 お姉さん オリジナル",
]


def queries_for_body(which: str) -> list[str]:
    """mature keeps the older allowlist. petite is the underrepresented adult set."""
    if which == "mature":
        return list(ADULT_R18_QUERIES)
    if which == "petite":
        return list(PETITE_ADULT_QUERIES)
    if which == "all":
        return list(ADULT_R18_QUERIES) + list(PETITE_ADULT_QUERIES)
    raise RuntimeError(f"Unknown body set {which!r}")


# 2026-04-01..2026-10-31 is only an example window. Hot collection widens
# 7 / 30 / 90 / 180 / 365 days when a shorter span is too thin.
# Child-coded, school, and under-21 words are not searched.
HOT_KEEP_START = "2026-04-01"
HOT_KEEP_END = "2026-10-31"
HOT_BODY_QUERIES = (
    ("curvy", "巨乳 女性 オリジナル"),
    ("average", "お姉さん オリジナル"),
    ("average", "普通体型 女性 オリジナル"),
    ("slim", "スレンダー お姉さん"),
    ("slim", "スレンダー 人妻"),
    ("slim", "スレンダー 熟女"),
    ("petite", "細身 お姉さん"),
    ("petite", "華奢 お姉さん"),
    ("flat", "貧乳 お姉さん"),
    ("flat", "微乳 お姉さん"),
)
HOT_BUCKETS = ("curvy", "average", "slim", "petite", "flat")
THIN_BUCKETS = ("slim", "petite", "flat")
ADULT_SETTING_MARKERS = ("お姉さん", "人妻", "熟女", "成人", "女上司", "未亡人")
_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def hot_query_texts() -> list[str]:
    return [word for _bucket, word in HOT_BODY_QUERIES]


def queries_for_buckets(buckets: list[str] | None) -> tuple[tuple[str, str], ...]:
    if not buckets:
        return HOT_BODY_QUERIES
    wanted = set(buckets)
    unknown = wanted.difference(HOT_BUCKETS)
    if unknown:
        raise RuntimeError(f"Unknown body bucket {sorted(unknown)}")
    return tuple(item for item in HOT_BODY_QUERIES if item[0] in wanted)


def has_adult_setting(tags: list[str], title: str = "") -> bool:
    """Adult-setting words. Used so a slim or flat popular page cannot keep child-coded hits."""
    blob = " ".join([title, *tags])
    if any(marker in blob for marker in ADULT_SETTING_MARKERS):
        return True
    return any(str(tag).strip().upper() == "OL" for tag in tags)


def thin_bucket_allowed(bucket: str, tags: list[str], title: str = "") -> bool:
    if bucket not in THIN_BUCKETS:
        return True
    return has_adult_setting(tags, title)


def canonical_order(order: str) -> str:
    """Map the UI word popular / 人気 to Pixiv's popularity sort."""
    key = (order or "").strip().lower()
    if key in {"popular", "人気", "popular_d"}:
        return "popular_d"
    if key == "date_d":
        return "date_d"
    raise RuntimeError(f"Unsupported Pixiv order {order!r}")


def require_day(value: str) -> str:
    text = (value or "").strip()
    if not _DAY_RE.match(text):
        raise RuntimeError(f"Date must be YYYY-MM-DD, got {value!r}")
    return text


def create_day(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 10 and _DAY_RE.match(text[:10]):
        return text[:10]
    return ""


def request_bounds(start_date: str, end_date: str) -> tuple[str, str]:
    """Pad one day. Pixiv scd/ecd are after/before, and the keep window is inclusive."""
    from datetime import date, timedelta

    start = date.fromisoformat(require_day(start_date)) - timedelta(days=1)
    end = date.fromisoformat(require_day(end_date)) + timedelta(days=1)
    return start.isoformat(), end.isoformat()


def in_date_window(day: str, start_date: str, end_date: str) -> bool:
    if not day or not _DAY_RE.match(day):
        return False
    return require_day(start_date) <= day <= require_day(end_date)


# Shortest span that still fills the hot list. 7 days through 1 year.
FLEXIBLE_WINDOW_DAYS = (7, 30, 90, 180, 365)


def parse_date_windows(text: str) -> tuple[int, ...]:
    """Comma-separated day spans, shortest first, each between 7 and 366."""
    days = tuple(int(part.strip()) for part in (text or "").split(",") if part.strip())
    if not days:
        raise RuntimeError("Pass --date-windows like 7,30,90,180,365")
    if any(day < 7 or day > 366 for day in days):
        raise RuntimeError("Each date window must be 7–366 days")
    if list(days) != sorted(days):
        raise RuntimeError("Date windows must be shortest first")
    return days


def flexible_keep_windows(today, days_list: tuple[int, ...] = FLEXIBLE_WINDOW_DAYS) -> list[tuple[int, str, str]]:
    """(span_days, inclusive start, inclusive end) ending on today, shortest first."""
    from datetime import timedelta

    windows = []
    for days in parse_date_windows(",".join(str(day) for day in days_list)):
        start = today - timedelta(days=days)
        windows.append((days, start.isoformat(), today.isoformat()))
    return windows


def choose_window_days(stub_counts: dict[int, int], target: int, windows: tuple[int, ...]) -> int:
    """Shortest span whose search stubs can fill the list. Else the longest."""
    chosen = windows[-1]
    for days in windows:
        chosen = days
        if int(stub_counts.get(days) or 0) >= target:
            return days
    return chosen


def bookmark_count(item: dict) -> int | None:
    for key in ("bookmarkCount", "bookmark_count", "totalBookmarks"):
        raw = item.get(key)
        if raw in (None, ""):
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None


def is_rough_work(tags: list[str], title: str = "") -> bool:
    """Drop sketches and tagged broken drawings before they enter the hot set."""
    blobs = [str(title or "")]
    blobs.extend(str(tag or "") for tag in tags)
    for blob in blobs:
        token = blob.strip()
        if not token:
            continue
        if token in {"落書き", "下描き", "下書き", "練習", "練習絵", "作画崩壊"}:
            return True
        if "落書き" in token or "下描き" in token or "下書き" in token or "作画崩壊" in token:
            return True
        if token == "ラフ" or token.startswith("ラフ"):
            return True
    return False


def hot_search_url(
    word: str,
    page: int,
    *,
    start_date: str,
    end_date: str,
    order: str = "popular",
    min_bookmarks: int = 0,
) -> str:
    from fetch_pixiv import search_url

    req_start, req_end = request_bounds(start_date, end_date)
    return search_url(
        word,
        page,
        "r18",
        order=canonical_order(order),
        start_date=req_start,
        end_date=req_end,
        artwork_type="illust",
        min_bookmarks=min_bookmarks,
    )

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
    "create_date",
    "bookmark_count",
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
            "bookmark_count": bookmarks,
            "create_date": create_day(str(body.get("createDate") or "")),
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


def _search_data(payload: dict) -> list[dict]:
    data = ((payload.get("body") or {}).get("illust") or {}).get("data") or []
    return data if isinstance(data, list) else []


def _restricted_illust(item: dict) -> bool:
    if not isinstance(item, dict) or item.get("isMasked"):
        return False
    try:
        restrict = int(item.get("xRestrict") or 0)
        illust_type = int(item.get("illustType") or 0)
    except (TypeError, ValueError):
        return False
    return restrict == 1 and illust_type == 0


def iter_hot_r18_search(
    fetch_json: FetchJson,
    *,
    pages: int,
    start_date: str,
    end_date: str,
    order: str = "popular",
    min_bookmarks: int = 1000,
    queries: tuple[tuple[str, str], ...] | None = None,
) -> tuple[dict[str, list[dict]], dict]:
    """Popularity-sorted R-18 stubs inside the keep window, grouped by body bucket.

    The request uses order=popular_d. scd/ecd are padded by one day because
    Pixiv treats them as after/before. Rows outside the inclusive keep window
    are dropped here when the stub has a create date. Slim, petite, and flat
    stubs also need an adult-setting tag.
    """
    chosen = queries if queries is not None else HOT_BODY_QUERIES
    validate_queries([word for _bucket, word in chosen])
    require_day(start_date)
    require_day(end_date)
    sent_order = canonical_order(order)
    groups: dict[str, list[dict]] = {bucket: [] for bucket in HOT_BUCKETS}
    seen: set[str] = set()
    req_start, req_end = request_bounds(start_date, end_date)
    notes: dict = {
        "order_arg": order,
        "order_sent": sent_order,
        "keep_start": start_date,
        "keep_end": end_date,
        "request_start": req_start,
        "request_end": req_end,
        "queries": [word for _bucket, word in chosen],
        "min_bookmarks": min_bookmarks,
        "search_bookmarks": [],
        "masked_queries": 0,
        "per_query": {},
    }
    for bucket, word in chosen:
        kept_for_query = 0
        for page in range(1, pages + 1):
            payload = _fetch_hot_page(
                fetch_json,
                word,
                page,
                start_date=start_date,
                end_date=end_date,
                order=sent_order,
                min_bookmarks=min_bookmarks,
                notes=notes,
            )
            data = _search_data(payload)
            if not data:
                break
            restricted_on_page = 0
            for item in data:
                if not _restricted_illust(item):
                    continue
                restricted_on_page += 1
                artwork_id = str(item.get("id") or "")
                if not artwork_id or artwork_id in seen:
                    continue
                tags = item.get("tags") or []
                if isinstance(tags, str):
                    tags = [tags]
                tag_list = []
                for tag in tags:
                    if isinstance(tag, dict):
                        tag_list.append(str(tag.get("tag") or ""))
                    elif tag:
                        tag_list.append(str(tag))
                tag_list = [tag for tag in tag_list if tag]
                title = str(item.get("title") or "")
                if is_rough_work(tag_list, title):
                    continue
                ok, _why = screen(" ".join([title, *tag_list]), tag_list)
                if not ok:
                    continue
                if not thin_bucket_allowed(bucket, tag_list, title):
                    continue
                day = create_day(str(item.get("createDate") or ""))
                if day and not in_date_window(day, start_date, end_date):
                    continue
                counted = bookmark_count(item)
                if counted is not None:
                    notes["search_bookmarks"].append(counted)
                    if counted < min_bookmarks:
                        continue
                seen.add(artwork_id)
                stub = dict(item)
                stub["_body_bucket"] = bucket
                groups[bucket].append(stub)
                kept_for_query += 1
            if restricted_on_page == 0:
                notes["masked_queries"] += 1
                break
        notes["per_query"][word] = kept_for_query
    notes["stub_counts"] = {bucket: len(items) for bucket, items in groups.items()}
    notes["search_bookmark_summary"] = bookmark_summary(notes["search_bookmarks"])
    return groups, notes


def _fetch_hot_page(
    fetch_json: FetchJson,
    word: str,
    page: int,
    *,
    start_date: str,
    end_date: str,
    order: str,
    min_bookmarks: int,
    notes: dict,
) -> dict:
    use_floor = 0 if notes.get("blt_disabled") else min_bookmarks
    url = hot_search_url(
        word,
        page,
        start_date=start_date,
        end_date=end_date,
        order=order,
        min_bookmarks=use_floor,
    )
    payload = fetch_json(url)
    if not payload.get("error"):
        return payload
    message = str(payload.get("message") or "search failed")
    if min_bookmarks and not notes.get("blt_disabled"):
        notes["blt_disabled"] = True
        notes["blt_retry"] = message
        url = hot_search_url(
            word,
            page,
            start_date=start_date,
            end_date=end_date,
            order=order,
            min_bookmarks=0,
        )
        payload = fetch_json(url)
        if not payload.get("error"):
            return payload
    raise RuntimeError(f"Pixiv search failed for {word!r}: {message}")


def select_hot_rows(
    rows: list[dict],
    *,
    limit: int,
    per_bucket: int,
    author_cap: int = 4,
) -> list[dict]:
    """Round-robin body buckets, then fill leftover slots by bookmarks."""
    by_bucket: dict[str, list[dict]] = {bucket: [] for bucket in HOT_BUCKETS}
    for row in rows:
        bucket = str(row.get("body_bucket") or "")
        if bucket not in by_bucket:
            continue
        by_bucket[bucket].append(row)
    for bucket in by_bucket:
        by_bucket[bucket].sort(key=lambda row: int(row.get("bookmark_count") or 0), reverse=True)
    picked: list[dict] = []
    seen: set[str] = set()
    authors: Counter = Counter()

    def add(row: dict) -> bool:
        artwork_id = str(row.get("id") or "")
        if not artwork_id or artwork_id in seen or len(picked) >= limit:
            return False
        author = str(row.get("user_id") or row.get("author") or "")
        if author and authors[author] >= author_cap:
            return False
        seen.add(artwork_id)
        if author:
            authors[author] += 1
        picked.append(row)
        return True

    index = {bucket: 0 for bucket in HOT_BUCKETS}
    while len(picked) < limit:
        progressed = False
        for bucket in HOT_BUCKETS:
            items = by_bucket[bucket]
            cursor = index[bucket]
            if cursor >= per_bucket or cursor >= len(items):
                continue
            index[bucket] = cursor + 1
            if add(items[cursor]):
                progressed = True
        if not progressed:
            break
    leftovers = sorted(rows, key=lambda row: int(row.get("bookmark_count") or 0), reverse=True)
    for row in leftovers:
        if len(picked) >= limit:
            break
        add(row)
    return picked


def bookmark_summary(values: list[int]) -> dict:
    if not values:
        return {"n": 0, "min": None, "p50": None, "max": None}
    ordered = sorted(int(value) for value in values)
    return {
        "n": len(ordered),
        "min": ordered[0],
        "p50": ordered[len(ordered) // 2],
        "max": ordered[-1],
        "at_least_1000": sum(1 for value in ordered if value >= 1000),
        "at_least_3000": sum(1 for value in ordered if value >= 3000),
    }


def quarantine_low_bookmark_pixiv(
    rows: list[dict],
    *,
    min_bookmarks: int,
    originals_dir: Path | None = None,
    quarantine_dir: Path | None = None,
) -> Counter:
    """Mark older low-bookmark Pixiv rows so they are not treated as train-ready.

    Rows collected in the hot window (pool=hot) stay. Image files, when present,
    move to quarantine_dir. This does not delete catalog rows.
    """
    import shutil

    stats: Counter = Counter()
    if quarantine_dir is not None:
        quarantine_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        if str(row.get("source") or "") != "pixiv":
            continue
        if str(row.get("pool") or "") == "hot":
            stats["hot_kept"] += 1
            continue
        if str(row.get("visual_review") or "") == "quarantine":
            stats["already_quarantine"] += 1
            continue
        counted = bookmark_count(row)
        if counted is None:
            try:
                counted = int(row.get("quality") or 0)
            except (TypeError, ValueError):
                counted = 0
        if counted >= min_bookmarks:
            stats["strong_kept"] += 1
            continue
        row["visual_review"] = "quarantine"
        row["pool"] = "quarantine"
        reason = str(row.get("keep_reason") or "")
        if not reason.startswith("Quarantined:"):
            row["keep_reason"] = (
                f"Quarantined: {counted} Pixiv bookmarks are below the hot floor "
                f"{min_bookmarks}. Not train-ready. {reason}"
            )[:500]
        stats["quarantined"] += 1
        artwork_id = str(row.get("id") or "")
        if originals_dir is None or quarantine_dir is None or not artwork_id.isdigit():
            continue
        for path in sorted(originals_dir.glob(f"{artwork_id}_p*")):
            if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
                continue
            dest = quarantine_dir / path.name
            if dest.exists():
                stats["file_already_moved"] += 1
                continue
            shutil.move(str(path), str(dest))
            stats["files_moved"] += 1
    return stats


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
