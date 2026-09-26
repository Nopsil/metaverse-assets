"""Download Pixiv img-original files on Windows. Never thumbnails.

Uses the same dedicated Chrome profile and local proxy as
collect_pixiv_windows.py. Opens each artwork page, reads the original URL
from Pixiv, and saves bytes under catalog/_originals/ (gitignored).

Ugoira is skipped. Multi-page works save the first 3 stills. This does not
run from a US cloud agent: Pixiv blocks those IPs, and this script exits
unless it is on Windows.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from chrome_profile import default_dedicated_profile, validate_proxy
from pixiv_browser import open_pixiv, require_windows
from pixiv_home import pixiv_block_reason
from pixiv_originals import MAX_ORIGINAL_PAGES, file_name, originals_for_illust
from pixiv_urls import parse_artwork_url

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
DEFAULT_OUT = HERE.parent / "catalog" / "_originals"


def _exit(message: str, code: int = 2) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def assert_originals_dir(path: Path) -> None:
    resolved = path.resolve()
    allowed = (
        (HERE.parent / "catalog" / "_originals").resolve(),
        (HERE.parent / "images").resolve(),
    )
    if any(resolved == root or root in resolved.parents for root in allowed):
        return
    repo = REPO_ROOT.resolve()
    if resolved == repo or repo in resolved.parents:
        _exit("Refusing to save originals inside the repo except catalog/_originals or images/.")


def load_rows(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if path.suffix.lower() == ".jsonl" or stripped.startswith("{"):
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                rows.append(json.loads(line))
        return rows
    import csv

    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def pixiv_targets(rows: list[dict]) -> list[dict]:
    targets = []
    seen: set[str] = set()
    for row in rows:
        source = str(row.get("source") or "")
        url = str(row.get("url") or "")
        ref = parse_artwork_url(url)
        if source and source != "pixiv" and ref is None:
            continue
        if ref is not None and ref.source != "pixiv":
            continue
        artwork_id = str(row.get("id") or (ref.id if ref else ""))
        if not artwork_id.isdigit() or artwork_id in seen:
            continue
        if ref is None and source != "pixiv":
            continue
        seen.add(artwork_id)
        targets.append({"id": artwork_id, "url": f"https://www.pixiv.net/artworks/{artwork_id}"})
    return targets


def browser_json(page, url: str) -> dict:
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
        _exit("Pixiv refused this network (" + reason + "). Use the home proxy, not a US datacenter IP.")
    if status != 200:
        raise RuntimeError(f"Pixiv HTTP {status}")
    return json.loads(text)


def save_original(page, url: str, dest: Path) -> str | None:
    if dest.exists() and dest.stat().st_size > 0:
        return None
    response = page.request.get(url, headers={"Referer": "https://www.pixiv.net/"}, timeout=120000)
    if response.status != 200:
        return f"http_{response.status}"
    ctype = (response.headers.get("content-type") or "").lower()
    data = response.body()
    if "image/" not in ctype or data[:20].lstrip().lower().startswith(b"<"):
        return "not_image"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return None


def download_one(page, target: dict, out_dir: Path) -> dict:
    artwork_id = target["id"]
    page.goto(target["url"], wait_until="domcontentloaded", timeout=60000)
    detail = browser_json(page, f"https://www.pixiv.net/ajax/illust/{artwork_id}")
    body = detail.get("body") if isinstance(detail, dict) else None
    if not isinstance(body, dict):
        return {"id": artwork_id, "skip": "no_detail", "files": []}
    pages_body = None
    try:
        page_count = int(body.get("pageCount") or 1)
    except (TypeError, ValueError):
        page_count = 1
    if page_count > 1:
        pages = browser_json(page, f"https://www.pixiv.net/ajax/illust/{artwork_id}/pages")
        raw_pages = pages.get("body") if isinstance(pages, dict) else None
        pages_body = raw_pages if isinstance(raw_pages, list) else []
    plan = originals_for_illust(body, pages_body)
    if plan["skip"]:
        return {"id": artwork_id, "skip": plan["skip"], "files": []}
    saved: list[str] = []
    for index, url in enumerate(plan["urls"]):
        dest = out_dir / file_name(artwork_id, index, url)
        error = save_original(page, url, dest)
        if error:
            return {"id": artwork_id, "skip": error, "files": saved}
        saved.append(dest.name)
    record = {"id": artwork_id, "skip": "", "files": saved}
    if plan["truncated"]:
        record["truncated_pages"] = plan["truncated"]
        record["kept_pages"] = MAX_ORIGINAL_PAGES
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=HERE.parent / "catalog" / "style_candidates.jsonl")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--dedicated-profile", type=Path, default=None)
    parser.add_argument("--proxy", default="")
    parser.add_argument("--limit", type=int, default=0, help="Stop after this many Pixiv rows. 0 means all.")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    require_windows("Pixiv original download")
    assert_originals_dir(args.out)
    profile = args.dedicated_profile or default_dedicated_profile()
    try:
        proxy = validate_proxy(args.proxy)
    except RuntimeError as exc:
        _exit(str(exc))
    if not args.catalog.exists():
        _exit(f"Catalog not found: {args.catalog}")
    targets = pixiv_targets(load_rows(args.catalog))
    if args.limit > 0:
        targets = targets[: args.limit]
    args.out.mkdir(parents=True, exist_ok=True)
    playwright, context = open_pixiv(profile, proxy, REPO_ROOT, headless=args.headless)
    page = context.pages[0] if context.pages else context.new_page()
    manifest: list[dict] = []
    try:
        for target in targets:
            try:
                record = download_one(page, target, args.out)
            except Exception as exc:  # noqa: BLE001 - keep going across artworks
                record = {"id": target["id"], "skip": "error", "files": [], "error": type(exc).__name__}
            manifest.append(record)
            print(json.dumps(record, ensure_ascii=False), file=sys.stderr)
            time.sleep(0.45)
    finally:
        context.close()
        playwright.stop()
    manifest_path = args.out / "manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8") as handle:
        for record in manifest:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    saved = sum(len(record.get("files") or []) for record in manifest)
    skipped = sum(1 for record in manifest if record.get("skip"))
    print(json.dumps({"saved_files": saved, "skipped_rows": skipped, "out": str(args.out)}, indent=2))


if __name__ == "__main__":
    main()
