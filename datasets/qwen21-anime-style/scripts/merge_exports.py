"""Merge home-exported Pixiv URLs into the style catalog without losing reviewed rows.

Accepts JSONL from collect_pixiv_windows.py, a text file with one artwork URL
per line, or a CSV with a url column. Dedupes on (source, id). A row already
marked visual_review=thumbnail_pass is kept as-is when the same id is imported
again. New rows stay visual_review=pending.

The default write is catalog/_merged_preview.jsonl (gitignored). Pass --apply
to replace catalog/style_candidates.jsonl and .csv with the merged table.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from build_catalog import CSV_FIELDS, write_outputs
from pixiv_home import quarantine_low_bookmark_pixiv
from pixiv_urls import parse_artwork_url, refs_from_text
from safety import has_person_signal, screen

HERE = Path(__file__).resolve().parent
CATALOG = HERE.parent / "catalog"


def split_tags(value: str) -> list[str]:
    if "|" in value:
        return [part for part in value.split("|") if part]
    return [part.strip() for part in value.split(",") if part.strip()]


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))
    return rows


def _stub(source: str, artwork_id: str, url: str, *, title: str = "", tags: list[str] | None = None, extra: dict | None = None) -> dict:
    row = {
        "source": source,
        "url": url,
        "id": artwork_id,
        "title": title,
        "tags": tags or [],
        "rating": "unreviewed",
        "style_notes": "Imported URL. Full-size human review is required.",
        "keep_reason": (
            "User-exported URL. Full-size human review is required before download or training."
        ),
        "width": "",
        "height": "",
        "author": "",
        "nsfw_level": "",
        "ai_generated": "unknown",
        "base_model": "",
        "quality": 0,
        "visual_review": "pending",
        "collected_via": "url_paste",
    }
    if extra:
        for key in (
            "title",
            "tags",
            "rating",
            "style_notes",
            "width",
            "height",
            "author",
            "nsfw_level",
            "ai_generated",
            "base_model",
            "quality",
            "image_url",
            "model_id",
            "model_name",
            "collected_via",
            "user_id",
            "create_date",
            "bookmark_count",
            "body_bucket",
            "pool",
        ):
            if extra.get(key) not in (None, "", []):
                row[key] = extra[key]
    return row


def screen_incoming(row: dict) -> tuple[dict | None, str]:
    """Screen title and tags only. keep_reason text is not a prompt."""
    url = str(row.get("url") or "")
    ref = parse_artwork_url(url)
    source = str(row.get("source") or (ref.source if ref else ""))
    artwork_id = str(row.get("id") or (ref.id if ref else ""))
    if ref is None and source in {"pixiv", "civitai"} and artwork_id.isdigit():
        if source == "pixiv":
            ref_url = f"https://www.pixiv.net/artworks/{artwork_id}"
        else:
            ref_url = f"https://civitai.com/images/{artwork_id}"
        canonical = ref_url
    elif ref is not None:
        source, artwork_id, canonical = ref.source, ref.id, ref.url
    else:
        return None, "unparsed_url"

    tags = row.get("tags") or []
    if isinstance(tags, str):
        tags = split_tags(tags)
    title = str(row.get("title") or "").strip()
    if not title and not tags:
        stub = _stub(source, artwork_id, canonical, extra=row)
        stub["visual_review"] = "pending"
        return stub, "url_only"

    tag_list = [str(tag) for tag in tags]
    blob = f"{title} {' '.join(tag_list)}"
    ok, why = screen(blob, tag_list)
    if not ok:
        return None, why
    # Rows already screened against a full prompt can have a short stored tag
    # list that no longer repeats the person word. Do not drop those.
    already_screened = str(row.get("screen") or "") == "pass"
    if not has_person_signal(blob, tag_list) and not already_screened:
        return None, "no_person"
    if isinstance(tags, str):
        tag_list = split_tags(tags)
    merged = _stub(source, artwork_id, canonical, title=title[:120], tags=tag_list[:16], extra=row)
    if isinstance(merged.get("tags"), str):
        merged["tags"] = split_tags(merged["tags"])
    merged["screen"] = why
    merged["visual_review"] = "pending"
    if merged.get("rating") not in {"all-ages", "adult"}:
        merged["rating"] = "unreviewed"
    hot_reason = str(row.get("keep_reason") or "")
    if str(row.get("collected_via") or "") == "pixiv_popular_date_window" and hot_reason:
        merged["keep_reason"] = hot_reason[:500]
    else:
        merged["keep_reason"] = (
            "Imported export passed the metadata screen. "
            "Full-size human review is required before download or training."
        )
    return merged, "pass"


def load_export(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if not stripped:
        return []
    suffix = path.suffix.lower()
    if suffix == ".jsonl" or stripped.startswith("{"):
        return load_jsonl(path)
    if suffix == ".csv" or stripped.lower().startswith("url,") or stripped.lower().startswith("source,"):
        rows = []
        with path.open(encoding="utf-8", newline="") as handle:
            for raw in csv.DictReader(handle):
                rows.append(dict(raw))
        return rows
    return [
        {"source": ref.source, "url": ref.url, "id": ref.id, "title": "", "tags": []}
        for ref in refs_from_text(text)
    ]


def dedupe_key(row: dict) -> tuple[str, str]:
    return (str(row.get("source") or ""), str(row.get("id") or ""))


def richness(row: dict) -> int:
    tags = row.get("tags") or []
    score = len(tags) if isinstance(tags, list) else 0
    if row.get("title"):
        score += 2
    if row.get("width"):
        score += 1
    return score


def is_train_unready(row: dict) -> bool:
    """The pre-hot catalog stays on disk and must not re-enter the active list."""
    status = str(row.get("status") or "").lower()
    review = str(row.get("visual_review") or "")
    pool = str(row.get("pool") or "")
    return status == "deprecated" or review in {"quarantine", "rejected"} or pool == "quarantine"


def rejected_review_ids(path: Path | None = None) -> set[str]:
    """Artwork ids that failed a full-size look. They stay out of the active list."""
    path = path or (CATALOG / "quarantine" / "failed-review" / "rejected.jsonl")
    if not path.exists():
        return set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
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


def merge_rows(
    base: list[dict],
    incoming: list[dict],
    rejected: set[str] | None = None,
) -> tuple[list[dict], Counter]:
    stats: Counter = Counter()
    blocked = rejected or set()
    ordered: list[dict] = []
    index: dict[tuple[str, str], int] = {}
    for row in base:
        if str(row.get("id") or "") in blocked or is_train_unready(row):
            stats["deprecated_skipped"] += 1
            continue
        key = dedupe_key(row)
        if not key[1]:
            stats["base_skipped"] += 1
            continue
        if key in index:
            stats["base_duplicate"] += 1
            continue
        index[key] = len(ordered)
        ordered.append(row)
        stats["base"] += 1

    for raw in incoming:
        if str(raw.get("id") or "") in blocked or is_train_unready(raw):
            stats["deprecated_skipped"] += 1
            continue
        screened, reason = screen_incoming(raw)
        if screened is None:
            stats[f"dropped:{reason}"] += 1
            continue
        key = dedupe_key(screened)
        if key in index:
            prev = ordered[index[key]]
            if prev.get("visual_review") == "thumbnail_pass":
                stats["duplicate_kept_reviewed"] += 1
                continue
            if richness(screened) > richness(prev):
                ordered[index[key]] = screened
                stats["duplicate_upgraded"] += 1
            else:
                stats["duplicate_skipped"] += 1
            continue
        index[key] = len(ordered)
        ordered.append(screened)
        stats["added"] += 1
        stats[f"added:{reason}"] += 1
    return ordered, stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=CATALOG / "style_candidates.jsonl")
    parser.add_argument("--import", dest="imports", action="append", default=[], type=Path)
    parser.add_argument("--out", type=Path, default=CATALOG / "_merged_preview.jsonl")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Also write catalog/style_candidates.jsonl and style_candidates.csv.",
    )
    parser.add_argument(
        "--quarantine-pixiv-below",
        type=int,
        default=0,
        help="Mark older Pixiv rows under this bookmark count as visual_review=quarantine.",
    )
    parser.add_argument("--originals", type=Path, default=CATALOG / "_originals")
    parser.add_argument("--quarantine-dir", type=Path, default=CATALOG / "_originals_quarantine")
    args = parser.parse_args()
    if not args.imports:
        parser.error("Pass at least one --import file (jsonl, csv, or a URL list).")

    base = load_jsonl(args.catalog) if args.catalog.exists() else []
    incoming: list[dict] = []
    for path in args.imports:
        incoming.extend(load_export(path))
    merged, stats = merge_rows(base, incoming, rejected_review_ids())
    quarantine_stats = {}
    if args.quarantine_pixiv_below:
        quarantine_stats = dict(
            quarantine_low_bookmark_pixiv(
                merged,
                min_bookmarks=args.quarantine_pixiv_below,
                originals_dir=args.originals if args.originals.exists() else None,
                quarantine_dir=args.quarantine_dir,
            )
        )
    csv_path = args.out.with_suffix(".csv")
    write_outputs(merged, args.out, csv_path)
    if args.apply:
        write_outputs(merged, CATALOG / "style_candidates.jsonl", CATALOG / "style_candidates.csv")
    summary = {
        "rows": len(merged),
        "preview_jsonl": str(args.out),
        "preview_csv": str(csv_path),
        "applied": bool(args.apply),
        "by_review": dict(Counter(str(row.get("visual_review") or "") for row in merged)),
        "by_source": dict(Counter(str(row.get("source") or "") for row in merged)),
        "by_rating": dict(Counter(str(row.get("rating") or "") for row in merged)),
        "stats": dict(stats),
        "quarantine": quarantine_stats,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
