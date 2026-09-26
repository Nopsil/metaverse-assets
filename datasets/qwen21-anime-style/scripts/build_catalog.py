"""Merge fetcher JSONL into the curated catalog tables.

Caps per artist and per Civitai model so one creator does not dominate.
This does not replace visual review. Pass --allowlist after a human pass
to keep only reviewed ids and rewrite keep_reason.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from safety import style_notes

HERE = Path(__file__).resolve().parent
CATALOG = HERE.parent / "catalog"

CSV_FIELDS = [
    "source",
    "url",
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
    "create_date",
    "body_bucket",
    "pool",
]


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def keep_reason(row: dict, *, reviewed: bool) -> str:
    who = row.get("author") or row.get("model_name") or row["source"]
    quality = row.get("quality") or 0
    quality_bit = (
        f"{quality} bookmarks" if row["source"] == "pixiv" else f"showcase long-edge {quality}"
    )
    screen = (
        "Thumbnail review kept an adult-looking character with no school, chibi, or child cue. "
        if reviewed
        else "Metadata screen only; full-size human review still required. "
    )
    return (
        f"{screen}"
        f"{row['source']} {row['rating']}; {quality_bit}; {row['width']}x{row['height']}; "
        f"from {who}. Style: {row.get('style_notes') or 'anime illustration'}."
    )


def select(rows: list[dict], *, all_ages_target: int, adult_target: int) -> list[dict]:
    rows = sorted(rows, key=lambda row: int(row.get("quality") or 0), reverse=True)
    picked: list[dict] = []
    seen: set[tuple[str, str]] = set()
    by_author: Counter = Counter()
    by_model: Counter = Counter()

    def try_add(row: dict, *, rating: str | None, author_cap: int, model_cap: int) -> bool:
        if rating and row.get("rating") != rating:
            return False
        key = (row["source"], str(row["id"]))
        if key in seen:
            return False
        author = (row.get("author") or row.get("user_id") or row.get("model_id") or row["id"]).strip()
        model = (row.get("model_id") or "").strip()
        if by_author[author] >= author_cap:
            return False
        if model and by_model[model] >= model_cap:
            return False
        seen.add(key)
        by_author[author] += 1
        if model:
            by_model[model] += 1
        picked.append(row)
        return True

    for row in rows:
        if sum(1 for item in picked if item["rating"] == "adult") >= adult_target:
            break
        try_add(row, rating="adult", author_cap=2, model_cap=3)
    for row in rows:
        if sum(1 for item in picked if item["rating"] == "all-ages") >= all_ages_target:
            break
        try_add(row, rating="all-ages", author_cap=3, model_cap=4)
    return picked


def write_outputs(rows: list[dict], jsonl_path: Path, csv_path: Path) -> None:
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            flat = dict(row)
            tags = row.get("tags") or []
            flat["tags"] = "|".join(tags) if isinstance(tags, list) else str(tags)
            writer.writerow(flat)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pixiv", type=Path, default=CATALOG / "_pixiv_candidates.jsonl")
    parser.add_argument("--civitai", type=Path, default=CATALOG / "_civitai_candidates.jsonl")
    parser.add_argument("--allowlist", type=Path, default=None)
    parser.add_argument("--all-ages", type=int, default=90)
    parser.add_argument("--adult", type=int, default=30)
    parser.add_argument("--jsonl", type=Path, default=CATALOG / "style_candidates.jsonl")
    parser.add_argument("--csv", type=Path, default=CATALOG / "style_candidates.csv")
    args = parser.parse_args()

    rows = load_jsonl(args.pixiv) + load_jsonl(args.civitai)
    for row in rows:
        blob = " ".join(row.get("tags") or [])
        blob = f"{blob} {row.get('title') or ''}"
        row["style_notes"] = style_notes(
            blob,
            base_model=row.get("base_model") or "",
            rating=row.get("rating") or "",
        )
    if args.allowlist and args.allowlist.exists():
        allowed = {
            line.strip()
            for line in args.allowlist.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }
        rows = [row for row in rows if str(row["id"]) in allowed]
        for row in rows:
            row["keep_reason"] = keep_reason(row, reviewed=True)
            row["visual_review"] = "thumbnail_pass"
        # Allowlist order is the review order; do not re-cap.
        chosen = rows
    else:
        chosen = select(rows, all_ages_target=args.all_ages, adult_target=args.adult)
        for row in chosen:
            row["keep_reason"] = keep_reason(row, reviewed=False)
            row["visual_review"] = "pending"

    write_outputs(chosen, args.jsonl, args.csv)
    summary = {
        "rows": len(chosen),
        "by_source": dict(Counter(row["source"] for row in chosen)),
        "by_rating": dict(Counter(row["rating"] for row in chosen)),
        "by_ai": dict(Counter(row.get("ai_generated") or "" for row in chosen)),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
