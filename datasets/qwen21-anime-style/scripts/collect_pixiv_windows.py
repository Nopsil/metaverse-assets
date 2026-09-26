"""Collect Pixiv artwork URLs on Windows with a dedicated Chrome profile.

Do not copy the system Chrome Default profile. Those cookies use app-bound
encryption and a copy does not stay logged in. Log in once with --login in a
separate user-data directory, then reuse it with --proxy.

This script writes artwork page URLs only. It does not download images and
does not read cookies. Originals are a later step: download_pixiv_originals.py.
Setup is in collect_pixiv_windows.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

from chrome_profile import default_dedicated_profile, validate_proxy
from download_pixiv_originals import wait_for_profile
from pixiv_browser import open_pixiv, require_windows
from pixiv_pace import pause
from pixiv_home import (
    ADULT_R18_QUERIES,
    HOT_BODY_QUERIES,
    HOT_BUCKETS,
    HOT_KEEP_END,
    HOT_KEEP_START,
    PETITE_ADULT_QUERIES,
    bookmark_count,
    bookmark_summary,
    collect_rows_from_stubs,
    create_day,
    flexible_keep_windows,
    hot_query_texts,
    in_date_window,
    iter_bookmark_works,
    iter_hot_r18_search,
    iter_r18_search,
    parse_date_windows,
    pixiv_block_reason,
    queries_for_body,
    queries_for_buckets,
    select_hot_rows,
    validate_queries,
)

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]


def _exit(message: str, code: int = 2) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def prepare_page(page) -> None:
    page.goto("https://www.pixiv.net/", wait_until="domcontentloaded", timeout=60000)
    html = page.content()
    reason = pixiv_block_reason(200, html)
    if reason:
        _exit(
            "Pixiv refused this network (" + reason + "). "
            "Run this on your home connection. A US datacenter IP is often blocked."
        )
    if "accounts.pixiv.net" in page.url or "/login" in page.url:
        _exit(
            "This Chrome profile is not logged into Pixiv. "
            "Log in with Chrome on this PC, close Chrome, and rerun."
        )


def detect_user_id(page) -> str:
    detected = page.evaluate(
        """() => {
            const html = document.documentElement.innerHTML;
            let match = html.match(/"userId"\\s*:\\s*"(\\d+)"/);
            if (match) return match[1];
            match = html.match(/\\/users\\/(\\d+)/);
            return match ? match[1] : "";
        }"""
    )
    return str(detected or "")


def make_fetch(page):
    def fetch_json(url: str) -> dict:
        last_status = 0
        for attempt in range(5):
            if attempt == 0:
                pause("page")
            result = page.evaluate(
                """async (url) => {
                    const res = await fetch(url, {
                        credentials: "include",
                        headers: { "Accept": "application/json" }
                    });
                    const text = await res.text();
                    return { status: res.status, text: text.slice(0, 1500000) };
                }""",
                url,
            )
            last_status = int((result or {}).get("status") or 0)
            text = (result or {}).get("text") or ""
            reason = pixiv_block_reason(last_status, text)
            if reason:
                _exit(
                    "Pixiv refused this network (" + reason + "). "
                    "Run this on your home connection. A US datacenter IP is often blocked."
                )
            if last_status == 200:
                return json.loads(text)
            if last_status not in {429, 500, 502, 503} or attempt == 4:
                break
            pause("page")
        raise RuntimeError(f"Pixiv HTTP {last_status}")

    return fetch_json


def scrape(page, args) -> tuple[list[dict], dict]:
    prepare_page(page)
    fetch_json = make_fetch(page)
    dropped: Counter = Counter()
    stubs: list[dict] = []
    notes: dict = {"mode": args.mode}
    if args.mode in {"bookmarks", "both"}:
        user_id = args.user_id or detect_user_id(page)
        if not user_id:
            _exit("Could not see a Pixiv user id. Pass --user-id from https://www.pixiv.net/users/YOUR_ID")
        notes["bookmarks"] = "show"
        stubs.extend(
            iter_bookmark_works(fetch_json, user_id, rest="show", limit=args.limit)
        )
        if args.include_private:
            notes["bookmarks"] = "show+hide"
            stubs.extend(
                iter_bookmark_works(fetch_json, user_id, rest="hide", limit=args.limit)
            )
    if args.mode in {"r18", "both"}:
        found, masked = iter_r18_search(
            fetch_json,
            queries_for_body(getattr(args, "body", "all")),
            pages=args.pages,
            limit=args.limit,
        )
        notes["r18_stubs"] = len(found)
        notes["r18_masked_queries"] = masked
        stubs.extend(found)
    if args.mode == "hot":
        if getattr(args, "date_windows", ""):
            return _scrape_flexible_hot(fetch_json, args, dropped, notes)
        groups, search_notes = iter_hot_r18_search(
            fetch_json,
            pages=args.pages,
            start_date=args.start_date,
            end_date=args.end_date,
            order=args.order,
            min_bookmarks=args.min_bookmarks,
        )
        notes.update(search_notes)
        stubs = _hot_detail_stubs(groups, detail_limit=max(args.limit * 4, args.limit))
        notes["detail_stubs"] = len(stubs)
    rows = collect_rows_from_stubs(
        stubs,
        fetch_json,
        include_ai=args.include_ai,
        dropped=dropped,
        delay_s=0,
    )
    if args.mode == "hot":
        rows = _finish_hot_rows(rows, stubs, args, dropped, notes)
    notes["dropped"] = dict(dropped)
    notes["rows"] = len(rows)
    if notes.get("r18_masked_queries") and not notes.get("r18_stubs"):
        notes["r18_note"] = (
            "R-18 search returned no restricted works. The session is logged out, "
            "or Pixiv is still masking R-18. No safe-mode stand-ins were saved as R-18."
        )
    return rows, notes


def _scrape_flexible_hot(fetch_json, args, dropped: Counter, notes: dict) -> tuple[list[dict], dict]:
    """Popularity rank inside the shortest window that fills --limit.

    Tries 7 days, then 30, 90, 180, and 365 (or whatever --date-windows lists).
    A shorter window is searched only for stubs. Detail pages are fetched once
    the stub count can fill the list, or on the longest window.
    """
    spans = parse_date_windows(args.date_windows)
    windows = flexible_keep_windows(date.today(), spans)
    bucket_names = [part.strip() for part in str(getattr(args, "buckets", "") or "").split(",") if part.strip()]
    queries = queries_for_buckets(bucket_names or None)
    wanted = bucket_names or list(HOT_BUCKETS)
    per_bucket = max(4, args.limit // max(len(wanted), 1))
    notes["order"] = "popular_d"
    notes["strategy"] = (
        "popular_d membership rank; widen 7/30/90/180/365 days until each "
        "adult body bucket has a high-bookmark pool"
    )
    notes["window_attempts"] = []
    notes["per_bucket_target"] = per_bucket
    excluded = _excluded_ids(getattr(args, "exclude", None))
    chosen: list[dict] = []
    for days, start, end in windows:
        groups, search_notes = iter_hot_r18_search(
            fetch_json,
            pages=args.pages,
            start_date=start,
            end_date=end,
            order=args.order,
            min_bookmarks=args.min_bookmarks,
            queries=queries,
        )
        stub_count = sum(len(items) for items in groups.values())
        attempt = {
            "days": days,
            "start": start,
            "end": end,
            "stubs": stub_count,
            "stub_counts": search_notes.get("stub_counts"),
            "bookmark_floor": args.min_bookmarks,
            "order_sent": search_notes.get("order_sent"),
        }
        notes["window_attempts"].append(attempt)
        ready = all(len(groups.get(bucket) or []) >= per_bucket for bucket in wanted)
        if not ready and days != spans[-1]:
            continue
        args.start_date = start
        args.end_date = end
        notes.update(search_notes)
        stubs = _hot_detail_stubs(groups, detail_limit=max(args.limit * 4, args.limit))
        notes["detail_stubs"] = len(stubs)
        rows = collect_rows_from_stubs(
            stubs,
            fetch_json,
            include_ai=args.include_ai,
            dropped=dropped,
            delay_s=0,
        )
        rows = _finish_hot_rows(rows, stubs, args, dropped, notes)
        if excluded:
            before = len(rows)
            rows = [row for row in rows if str(row.get("id") or "") not in excluded]
            dropped["excluded_previous"] += before - len(rows)
        chosen = rows
        notes["date_window_days"] = days
        notes["date_start"] = start
        notes["date_end"] = end
        if len(chosen) >= args.limit:
            break
    notes["dropped"] = dict(dropped)
    notes["rows"] = len(chosen)
    notes["bookmark_strategy"] = (
        f"order=popular_d with bookmark floor {args.min_bookmarks}; "
        f"not the user bookmark list; window {notes.get('date_window_days')} days "
        f"({notes.get('date_start')}..{notes.get('date_end')})"
    )
    return chosen, notes


def _excluded_ids(path: Path | None) -> set[str]:
    if path is None or not Path(path).exists():
        return set()
    ids: set[str] = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        artwork_id = str(row.get("id") or "")
        if artwork_id.isdigit():
            ids.add(artwork_id)
    return ids


def _hot_detail_stubs(groups: dict[str, list[dict]], *, detail_limit: int) -> list[dict]:
    ordered = {
        bucket: sorted(items, key=lambda item: bookmark_count(item) or 0, reverse=True)
        for bucket, items in groups.items()
    }
    picked: list[dict] = []
    seen: set[str] = set()
    index = {bucket: 0 for bucket in ordered}
    while len(picked) < detail_limit:
        progressed = False
        for bucket, items in ordered.items():
            cursor = index[bucket]
            if cursor >= len(items):
                continue
            index[bucket] = cursor + 1
            item = items[cursor]
            artwork_id = str(item.get("id") or "")
            if not artwork_id or artwork_id in seen:
                continue
            seen.add(artwork_id)
            picked.append(item)
            progressed = True
            if len(picked) >= detail_limit:
                break
        if not progressed:
            break
    return picked


def _finish_hot_rows(rows, stubs, args, dropped: Counter, notes: dict) -> list[dict]:
    meta = {str(stub.get("id") or ""): stub for stub in stubs}
    for row in rows:
        stub = meta.get(str(row.get("id") or ""), {})
        row["body_bucket"] = str(stub.get("_body_bucket") or "")
        row["pool"] = "hot"
        row["collected_via"] = "pixiv_popular_date_window"
        if not row.get("create_date"):
            row["create_date"] = create_day(str(stub.get("createDate") or ""))
        counted = int(row.get("bookmark_count") or 0)
        stub_count = bookmark_count(stub) or 0
        if stub_count > counted:
            row["bookmark_count"] = stub_count
            row["quality"] = stub_count
        row["keep_reason"] = (
            f"Popular R-18 search {args.start_date}..{args.end_date} "
            f"({row.get('body_bucket')}, {row.get('bookmark_count')} bookmarks). "
            "Metadata screen passed. Full-size review is still required before training."
        )
    notes["detail_bookmark_summary"] = bookmark_summary(
        [int(row.get("bookmark_count") or 0) for row in rows]
    )
    filtered = []
    for row in rows:
        day = str(row.get("create_date") or "")
        if not in_date_window(day, args.start_date, args.end_date):
            dropped["outside_date"] += 1
            continue
        if row.get("rating") != "adult":
            dropped["not_adult"] += 1
            continue
        if int(row.get("bookmark_count") or 0) < args.min_bookmarks:
            dropped["low_bookmarks"] += 1
            continue
        filtered.append(row)
    per_bucket = max(6, args.limit // 5)
    chosen = select_hot_rows(filtered, limit=args.limit, per_bucket=per_bucket)
    notes["kept_bookmarks"] = bookmark_summary(
        [int(row.get("bookmark_count") or 0) for row in chosen]
    )
    notes["kept_buckets"] = dict(Counter(str(row.get("body_bucket") or "") for row in chosen))
    notes["sample_ids"] = [
        {
            "id": row.get("id"),
            "bookmarks": row.get("bookmark_count"),
            "bucket": row.get("body_bucket"),
            "create_date": row.get("create_date"),
        }
        for row in chosen[:8]
    ]
    return chosen


def run_browser(profile: Path, proxy: str, args) -> tuple[list[dict], dict]:
    wait_for_profile(profile)
    playwright, context = open_pixiv(profile, proxy, REPO_ROOT, headless=args.headless)
    page = context.pages[0] if context.pages else context.new_page()
    try:
        return scrape(page, args)
    finally:
        context.close()
        playwright.stop()


def run_login(profile: Path, proxy: str) -> None:
    playwright, context = open_pixiv(profile, proxy, REPO_ROOT, headless=False)
    page = context.pages[0] if context.pages else context.new_page()
    try:
        page.goto("https://www.pixiv.net/", wait_until="domcontentloaded", timeout=60000)
        print(
            "Log into Pixiv in this window and open one R-18 artwork so the session is real.\n"
            "This profile is kept on disk. Do not commit it. Press Enter here when you are done.",
            file=sys.stderr,
        )
        input()
    finally:
        context.close()
        playwright.stop()


def write_export(rows: list[dict], notes: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary_path = out.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true", help="Validate queries and exit. No browser.")
    parser.add_argument("--login", action="store_true", help="Open the dedicated profile so you can log in once.")
    parser.add_argument(
        "--dedicated-profile",
        type=Path,
        default=None,
        help="Persistent Chrome user-data dir. Not the system Chrome profile.",
    )
    parser.add_argument("--proxy", default="", help="Local proxy, for example http://127.0.0.1:7890.")
    parser.add_argument("--user-id", default="", help="Pixiv numeric user id, if the page does not show one.")
    parser.add_argument("--mode", choices=("bookmarks", "r18", "both", "hot"), default="both")
    parser.add_argument(
        "--body",
        choices=("all", "mature", "petite"),
        default="all",
        help="R-18 search set. petite is slim/flat adult originals. mature is the older tall/voluptuous allowlist.",
    )
    parser.add_argument(
        "--order",
        default="popular",
        help="Hot mode sort. popular and 人気 are sent as Pixiv order=popular_d.",
    )
    parser.add_argument("--start-date", default=HOT_KEEP_START, help="Inclusive keep-window start, YYYY-MM-DD.")
    parser.add_argument("--end-date", default=HOT_KEEP_END, help="Inclusive keep-window end, YYYY-MM-DD.")
    parser.add_argument(
        "--date-windows",
        default="",
        help="Hot mode: shortest-first day spans, for example 7,30,90,180,365. Overrides --start-date.",
    )
    parser.add_argument(
        "--exclude",
        type=Path,
        default=None,
        help="JSONL of artwork ids to skip, such as the quarantined catalog.",
    )
    parser.add_argument(
        "--min-bookmarks",
        type=int,
        default=1000,
        help="Hot mode bookmark floor. Sent as blt when Pixiv accepts it.",
    )
    parser.add_argument(
        "--buckets",
        default="",
        help="Hot body buckets to search, comma-separated: curvy,average,slim,petite,flat. Empty means all.",
    )
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--pages", type=int, default=2, help="R-18 search pages per query.")
    parser.add_argument("--include-private", action="store_true", help="Also read private bookmarks (rest=hide).")
    parser.add_argument("--include-ai", action="store_true", help="Keep Pixiv works labeled as AI.")
    parser.add_argument("--headless", action="store_true", help="Headless Chrome. A visible window is more reliable.")
    parser.add_argument(
        "--out",
        type=Path,
        default=HERE.parent / "catalog" / "_pixiv_windows_export.jsonl",
    )
    args = parser.parse_args()

    if args.self_check:
        validate_queries(ADULT_R18_QUERIES)
        validate_queries(PETITE_ADULT_QUERIES)
        validate_queries(hot_query_texts())
        print(json.dumps({
            "self_check": "ok",
            "mature_queries": len(ADULT_R18_QUERIES),
            "petite_queries": len(PETITE_ADULT_QUERIES),
            "hot_queries": len(HOT_BODY_QUERIES),
            "hot_keep": [HOT_KEEP_START, HOT_KEEP_END],
            "hot_order": "popular_d",
        }))
        return

    require_windows("Pixiv URL collection")

    if args.out.name in {"style_candidates.jsonl", "style_candidates.csv"}:
        _exit("Refusing to overwrite style_candidates. Write the gitignored export, then run merge_exports.py.")

    profile = args.dedicated_profile or default_dedicated_profile()
    try:
        proxy = validate_proxy(args.proxy)
    except RuntimeError as exc:
        _exit(str(exc))
    if args.login:
        try:
            run_login(profile, proxy)
        except RuntimeError as exc:
            _exit(str(exc))
        print(json.dumps({"login": "closed", "dedicated_profile": str(profile)}))
        return
    rows = None
    notes = None
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            rows, notes = run_browser(profile, proxy, args)
            last_error = None
            break
        except RuntimeError as exc:
            _exit(str(exc))
        except Exception as exc:  # noqa: BLE001 - one retry when Chrome closes mid-search
            last_error = exc
            if attempt == 0 and "closed" in str(exc).lower():
                print("Dedicated Chrome closed mid-search. Retrying once. Not touching any other Chrome.", file=sys.stderr)
                time.sleep(3)
                continue
            raise
    if last_error is not None or rows is None or notes is None:
        _exit("Pixiv collect failed: " + str(last_error))
    write_export(rows, notes, args.out)
    print(json.dumps({"out": str(args.out), "dedicated_profile": str(profile), **notes}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
