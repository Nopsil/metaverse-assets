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
from collections import Counter
from pathlib import Path

from chrome_profile import default_dedicated_profile, validate_proxy
from pixiv_browser import open_pixiv, require_windows
from pixiv_home import (
    ADULT_R18_QUERIES,
    collect_rows_from_stubs,
    iter_bookmark_works,
    iter_r18_search,
    pixiv_block_reason,
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
        status = int((result or {}).get("status") or 0)
        text = (result or {}).get("text") or ""
        reason = pixiv_block_reason(status, text)
        if reason:
            _exit(
                "Pixiv refused this network (" + reason + "). "
                "Run this on your home connection. A US datacenter IP is often blocked."
            )
        if status != 200:
            raise RuntimeError(f"Pixiv HTTP {status}")
        return json.loads(text)

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
            ADULT_R18_QUERIES,
            pages=args.pages,
            limit=args.limit,
        )
        notes["r18_stubs"] = len(found)
        notes["r18_masked_queries"] = masked
        stubs.extend(found)
    rows = collect_rows_from_stubs(
        stubs,
        fetch_json,
        include_ai=args.include_ai,
        dropped=dropped,
        delay_s=0.35,
    )
    notes["dropped"] = dict(dropped)
    notes["rows"] = len(rows)
    if notes.get("r18_masked_queries") and not notes.get("r18_stubs"):
        notes["r18_note"] = (
            "R-18 search returned no restricted works. The session is logged out, "
            "or Pixiv is still masking R-18. No safe-mode stand-ins were saved as R-18."
        )
    return rows, notes


def run_browser(profile: Path, proxy: str, args) -> tuple[list[dict], dict]:
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
    parser.add_argument("--mode", choices=("bookmarks", "r18", "both"), default="both")
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
        print(json.dumps({"self_check": "ok", "queries": len(ADULT_R18_QUERIES)}))
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
    try:
        rows, notes = run_browser(profile, proxy, args)
    except RuntimeError as exc:
        _exit(str(exc))
    write_export(rows, notes, args.out)
    print(json.dumps({"out": str(args.out), "dedicated_profile": str(profile), **notes}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
