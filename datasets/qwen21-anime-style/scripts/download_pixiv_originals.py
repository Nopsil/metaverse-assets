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
from pixiv_pace import pause
from pixiv_home import pixiv_block_reason
from pixiv_originals import MAX_ORIGINAL_PAGES, bytes_match_original, file_name, originals_for_illust
from pixiv_urls import parse_artwork_url

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
DEFAULT_OUT = HERE.parent / "catalog" / "_originals_hot"


def _exit(message: str, code: int = 2) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def assert_originals_dir(path: Path) -> None:
    resolved = path.resolve()
    parts = [part.lower() for part in resolved.parts]
    if "quarantine" in parts:
        _exit("Refusing to save originals into the train-unready quarantine.")
    allowed = (
        (HERE.parent / "catalog" / "_originals_hot").resolve(),
        (HERE.parent / "catalog" / "_originals").resolve(),
        (HERE.parent / "images").resolve(),
    )
    if any(resolved == root or root in resolved.parents for root in allowed):
        return
    repo = REPO_ROOT.resolve()
    if resolved == repo or repo in resolved.parents:
        _exit("Refusing to save originals inside the repo except catalog/_originals_hot, catalog/_originals, or images/.")


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
        if str(row.get("visual_review") or "") in {"quarantine", "rejected"}:
            continue
        if str(row.get("status") or "").lower() == "deprecated":
            continue
        if str(row.get("pool") or "") == "quarantine":
            continue
        if ref is None and source != "pixiv":
            continue
        seen.add(artwork_id)
        targets.append(
            {
                "id": artwork_id,
                "url": f"https://www.pixiv.net/artworks/{artwork_id}",
                "visual_review": str(row.get("visual_review") or ""),
            }
        )
    targets.sort(key=lambda item: 0 if item.get("visual_review") == "pending" else 1)
    return targets


def profile_in_use(profile: Path) -> bool:
    """True when another Chrome already has this dedicated profile open.

    A stale lock file is not enough: the user's main Chrome must stay up, and
    a leftover SingletonLock must not block a free dedicated profile.
    """
    marker = str(profile).lower()
    try:
        import subprocess

        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name = 'chrome.exe'\" | "
                "Select-Object -ExpandProperty CommandLine",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except Exception:
        return any((profile / name).exists() for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"))
    return marker in (out or "").lower()


def wait_for_profile(profile: Path, timeout_s: int = 900) -> None:
    """Wait if another agent has the dedicated profile. Do not kill Chrome."""
    started = time.time()
    announced = False
    while profile_in_use(profile):
        if not announced:
            print(
                "Dedicated Pixiv Chrome profile is already open. Waiting. Not closing any Chrome window.",
                file=sys.stderr,
            )
            announced = True
        if time.time() - started > timeout_s:
            _exit("Dedicated profile is still open. Left that Chrome window alone.", code=3)
        time.sleep(15)


def browser_json(page, url: str) -> dict:
    status = 0
    text = ""
    for _attempt in range(4):
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
        status = int((result or {}).get("status") or 0)
        text = (result or {}).get("text") or ""
        reason = pixiv_block_reason(status, text)
        if reason and reason != "http_429":
            _exit("Pixiv refused this network (" + reason + "). Use the home proxy, not a US datacenter IP.")
        if status == 200:
            return json.loads(text)
        if status in {429, 500, 502, 503} and _attempt < 3:
            continue
        break
    raise RuntimeError(f"Pixiv HTTP {status}")


def _fetch_image(page, url: str) -> tuple[int, bytes]:
    response = page.request.get(
        url,
        headers={"Referer": "https://www.pixiv.net/", "Accept": "image/*,*/*"},
        timeout=120000,
    )
    data = response.body()
    final_url = str(response.url or "")
    if response.status == 200 and bytes_match_original(data, 0, 0) is None and "/img-original/" in (final_url or url):
        return response.status, data
    if response.status == 200 and data[:2] == b"\xff\xd8":
        return response.status, data
    if response.status == 200 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return response.status, data
    pause("file")
    result = page.evaluate(
        """async (url) => {
            const res = await fetch(url, {
                credentials: "include",
                referrer: location.href,
                headers: { "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8" }
            });
            const buf = new Uint8Array(await res.arrayBuffer());
            const chunks = [];
            const size = 8192;
            for (let i = 0; i < buf.length; i += size) {
                const slice = buf.subarray(i, Math.min(i + size, buf.length));
                chunks.push(btoa(String.fromCharCode.apply(null, slice)));
            }
            return { status: res.status, chunks: chunks, finalUrl: res.url };
        }""",
        url,
    )
    import base64

    status = int((result or {}).get("status") or 0)
    final_url = str((result or {}).get("finalUrl") or "")
    if "/img-original/" not in final_url and "/img-original/" not in url:
        return status, b""
    raw = b"".join(base64.b64decode(part) for part in ((result or {}).get("chunks") or []))
    return status, raw


def save_original(page, url: str, dest: Path, expect_w: int = 0, expect_h: int = 0) -> str | None:
    if "/img-original/" not in (url or ""):
        return "not_img_original"
    if dest.exists() and dest.stat().st_size > 0:
        if bytes_match_original(dest.read_bytes(), expect_w, expect_h) is None:
            return None
        dest.unlink()
    status, data = _fetch_image(page, url)
    if status != 200:
        return f"http_{status}"
    reason = bytes_match_original(data, expect_w, expect_h)
    if reason:
        return reason
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")
    partial.write_bytes(data)
    partial.replace(dest)
    return None


def already_saved(out_dir: Path, artwork_id: str) -> list[str]:
    names: list[str] = []
    for path in sorted(out_dir.glob(f"{artwork_id}_p*")):
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
            continue
        if path.stat().st_size > 0:
            names.append(path.name)
    return names


def download_one(page, target: dict, out_dir: Path) -> dict:
    artwork_id = target["id"]
    existing = already_saved(out_dir, artwork_id)
    if existing:
        return {"id": artwork_id, "skip": "", "files": existing}
    pause("page")
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
    sizes = plan.get("sizes") or []
    for index, url in enumerate(plan["urls"]):
        pause("file")
        expect_w, expect_h = sizes[index] if index < len(sizes) else (0, 0)
        dest = out_dir / file_name(artwork_id, index, url)
        error = save_original(page, url, dest, expect_w, expect_h)
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
    parser.add_argument("--proxy", default="http://127.0.0.1:7890")
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
    wait_for_profile(profile)
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
                record = {"id": target["id"], "skip": "error", "files": [], "error": str(exc)[:160]}
            manifest.append(record)
            print(json.dumps(record, ensure_ascii=False), file=sys.stderr)
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
