"""Collect Pixiv artwork URLs on a Windows PC using a copy of your Chrome profile.

Pixiv blocks many US datacenter IPs, and a cloud agent does not have your home
IP or your logged-in Chrome. Run this on your own machine.

The script copies Chrome's login files to a temp folder, opens that copy, and
writes artwork page URLs. It does not read cookie values, does not copy
passwords or history, and does not write cookies into the git repo. The temp
copy is deleted when the script exits.

Setup and the manual URL-paste path are in collect_pixiv_windows.md.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

from chrome_profile import (
    assert_outside_repo,
    copy_chrome_profile_for_pixiv,
    default_chrome_user_data,
)
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


def run_browser(user_data_dir: Path, args) -> tuple[list[dict], dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _exit(
            "Install Playwright on this Windows PC: py -3 -m pip install playwright\n"
            "Use the Chrome already installed on the PC. Do not switch the script to "
            "Playwright's bundled Chromium; Windows will not decrypt the copied login there."
        )
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(user_data_dir),
            channel="chrome",
            headless=args.headless,
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            return scrape(page, args)
        finally:
            context.close()


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
    parser.add_argument("--dry-run", action="store_true", help="Copy the profile to temp, delete it, do not open Pixiv.")
    parser.add_argument("--user-data", type=Path, default=None, help="Chrome User Data directory.")
    parser.add_argument("--profile", default="Default", help="Chrome profile folder name, e.g. Default or Profile 1.")
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

    if sys.platform != "win32":
        _exit(
            "This collector runs on Windows with your logged-in Chrome. "
            "A cloud agent cannot use your home IP or your Chrome profile. "
            "Paste artwork URLs instead and run merge_exports.py. "
            "See collect_pixiv_windows.md."
        )

    if args.out.name in {"style_candidates.jsonl", "style_candidates.csv"}:
        _exit("Refusing to overwrite style_candidates. Write the gitignored export, then run merge_exports.py.")

    user_data = args.user_data or default_chrome_user_data()
    temp_dir = Path(tempfile.mkdtemp(prefix="pixiv-chrome-copy-"))
    try:
        assert_outside_repo(temp_dir, REPO_ROOT)
        try:
            copied = copy_chrome_profile_for_pixiv(user_data, args.profile, temp_dir)
        except PermissionError:
            _exit(
                "Could not copy the Chrome profile because a file is locked. "
                "Close Chrome completely, including the tray icon, and rerun. "
                "The script will not read the live profile in place."
            )
        except FileNotFoundError as exc:
            _exit(str(exc))
        print(
            f"copied {len(copied['copied_files'])} login files into a temp profile",
            file=sys.stderr,
        )
        if args.dry_run:
            print(json.dumps({"dry_run": "ok", "copied_files": copied["copied_files"]}))
            return
        rows, notes = run_browser(temp_dir, args)
        # The export path is a gitignored catalog scratch file, not the Chrome copy.
        write_export(rows, notes, args.out)
        print(json.dumps({"out": str(args.out), **notes}, ensure_ascii=False, indent=2))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
