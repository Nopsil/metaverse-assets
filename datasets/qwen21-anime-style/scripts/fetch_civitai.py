"""Fetch Civitai public model-showcase metadata for the anime style catalog.

Uses https://civitai.com/api/v1 only. No API token. Rate-limited and cached.
Does not download image binaries. Prints a JSONL candidate file.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.parse
from collections import Counter
from pathlib import Path

from build_catalog import write_outputs
from http_cache import get_json
from safety import has_person_signal, rating_for, screen, style_notes

API = "https://civitai.com/api/v1"
HERE = Path(__file__).resolve().parent

# Public model searches. NSFW showcases are included so the catalog can carry
# an adult rating bucket; the safety screen still drops minor-coded rows.
SEARCHES = [
    {"types": "Checkpoint", "baseModels": "Illustrious", "sort": "Highest Rated", "nsfw": "false", "limit": 20},
    {"types": "Checkpoint", "baseModels": "NoobAI", "sort": "Most Downloaded", "nsfw": "false", "limit": 12},
    {"types": "Checkpoint", "query": "animagine", "sort": "Highest Rated", "nsfw": "false", "limit": 6},
    {"types": "Checkpoint", "baseModels": "Anima", "sort": "Highest Rated", "nsfw": "false", "limit": 8},
    {"types": "Checkpoint", "query": "wai illustrious", "sort": "Highest Rated", "nsfw": "true", "limit": 8},
    {"types": "Checkpoint", "baseModels": "Illustrious", "sort": "Most Downloaded", "nsfw": "true", "limit": 18},
    {"types": "LORA", "query": "anime style", "baseModels": "Illustrious", "sort": "Highest Rated", "nsfw": "false", "limit": 10},
    {"types": "LORA", "query": "cel shading", "sort": "Highest Rated", "nsfw": "false", "limit": 8},
    # Adult anime showcases. Latest galleries are often safe, so the fetcher
    # also reads a second version and keeps adult rows ahead of all-ages ones.
    {"types": "Checkpoint", "baseModels": "Illustrious", "sort": "Highest Rated", "nsfw": "true", "limit": 8},
    {"types": "Checkpoint", "baseModels": "NoobAI", "sort": "Most Downloaded", "nsfw": "true", "limit": 8},
    {"types": "Checkpoint", "baseModels": "Anima", "sort": "Most Downloaded", "nsfw": "true", "limit": 6},
    {"types": "LORA", "baseModels": "Illustrious", "query": "style", "sort": "Most Downloaded", "nsfw": "true", "limit": 8},
]

SKIP_MODEL = re.compile(
    r"(?i)\b(?:lolis?|shotas?|child|children|toddler|infant|teens?|schoolgirl|"
    r"furry|yiff|pony|photoreal|realism|realistic|celebrity|underage|3dcg)\b"
)

ID_RE = re.compile(r"/(\d+)\.(?:jpeg|jpg|png|webp)(?:\?|$)", re.I)
ADULT_PER_MODEL = 4
ALL_AGES_PER_MODEL = 2
VERSIONS_PER_MODEL = 2
ADULT_PENDING_CAP = 48
ADULT_PENDING_PER_MODEL = 3
# Thumbnail pass on 2026-09-26. Text filters let these through; the pictures did not.
VISUAL_BLOCKLIST = {
    "120481381",  # feet-only crop; age not readable
    "40097834",  # Shantae; ambiguous age
    "143422745",  # explicit frame whose figures read as youthful
}
MIN_SHORT = 768
MIN_LONG = 1024


def prompt_tags(prompt: str) -> list[str]:
    tags: list[str] = []
    for raw in prompt.split(","):
        tag = re.sub(r":\s*\d+(?:\.\d+)?", "", raw)
        tag = tag.strip(" ()[]{}")
        tag = re.sub(r"\s+", " ", tag).strip()
        if not tag or len(tag) > 42:
            continue
        if tag.lower() in {
            "masterpiece",
            "best quality",
            "highres",
            "high quality",
            "absurdres",
            "newest",
            "recent",
            "commentary",
        }:
            continue
        tags.append(tag)
        if len(tags) >= 14:
            break
    return tags


def image_id(url: str) -> str | None:
    match = ID_RE.search(url or "")
    return match.group(1) if match else None


def long_short(width: int, height: int) -> tuple[int, int]:
    return max(width, height), min(width, height)


def flag_true(value) -> bool:
    if value is True:
        return True
    if isinstance(value, str) and value.strip().lower() == "true":
        return True
    return False


def cap_showcase_rows(
    rows: list[dict],
    *,
    adult_cap: int = ADULT_PER_MODEL,
    all_ages_cap: int = ALL_AGES_PER_MODEL,
) -> list[dict]:
    """Keep adult showcases first, then a few all-ages rows from the same model."""
    adult = [row for row in rows if row.get("rating") == "adult"]
    other = [row for row in rows if row.get("rating") != "adult"]
    return adult[:adult_cap] + other[:all_ages_cap]


def model_rows(refresh: bool) -> list[dict]:
    found: list[dict] = []
    seen: set[int] = set()
    for query in SEARCHES:
        params = {k: v for k, v in query.items() if v is not None}
        url = f"{API}/models?{urllib.parse.urlencode(params)}"
        try:
            payload = get_json(url, refresh=refresh)
        except Exception as exc:  # noqa: BLE001 - keep going across searches
            print(f"skip search {params}: {exc}", file=sys.stderr)
            continue
        for item in payload.get("items") or []:
            mid = item.get("id")
            if not mid or mid in seen:
                continue
            name = item.get("name") or ""
            tags = " ".join(
                t.get("name", "") if isinstance(t, dict) else str(t) for t in (item.get("tags") or [])
            )
            if SKIP_MODEL.search(f"{name} {tags}"):
                print(f"skip model {mid} {name}", file=sys.stderr)
                continue
            versions = item.get("modelVersions") or []
            if not versions:
                continue
            version = versions[0]
            base = version.get("baseModel") or ""
            if base.lower() in {"pony", "sd 1.5", "sd 2.1", "sd 2.1 768"}:
                # Pony/MLP and old SD1.5 showcases are a poor match for this pass.
                continue
            version_ids = [v.get("id") for v in versions[:VERSIONS_PER_MODEL] if v.get("id")]
            if not version_ids:
                continue
            seen.add(mid)
            found.append(
                {
                    "model_id": mid,
                    "model_name": name,
                    "version_id": version_ids[0],
                    "version_ids": version_ids,
                    "base_model": base,
                    "model_nsfw": bool(item.get("nsfw")),
                }
            )
    return found


def candidates_from_version(model: dict, refresh: bool, dropped: Counter) -> list[dict]:
    version_ids = list(model.get("version_ids") or [])
    if not version_ids and model.get("version_id"):
        version_ids = [model.get("version_id")]
    rows: list[dict] = []
    seen_prompt: set[str] = set()
    seen_ids: set[str] = set()
    for vid in version_ids:
        rows.extend(
            _rows_from_one_version(
                model,
                vid,
                refresh,
                dropped,
                seen_prompt,
                seen_ids,
            )
        )
    return cap_showcase_rows(rows)


def _rows_from_one_version(
    model: dict,
    vid: int,
    refresh: bool,
    dropped: Counter,
    seen_prompt: set[str],
    seen_ids: set[str],
) -> list[dict]:
    try:
        payload = get_json(f"{API}/model-versions/{vid}", refresh=refresh)
    except Exception as exc:  # noqa: BLE001
        print(f"skip version {vid}: {exc}", file=sys.stderr)
        dropped["version_fetch"] += 1
        return []

    base = payload.get("baseModel") or model.get("base_model") or ""
    if str(base).lower() in {"pony", "sd 1.5", "sd 2.1", "sd 2.1 768"}:
        dropped["base_skipped"] += 1
        return []
    model_name = (payload.get("model") or {}).get("name") or model.get("model_name") or ""
    if SKIP_MODEL.search(model_name):
        dropped["model_name"] += 1
        return []
    rows: list[dict] = []
    for image in payload.get("images") or []:
        if image.get("type") not in (None, "image"):
            dropped["not_image"] += 1
            continue
        if str(image.get("availability") or "Public") not in {"Public", "None"}:
            dropped["not_public"] += 1
            continue
        url = image.get("url") or ""
        iid = image_id(url)
        if not iid:
            dropped["no_id"] += 1
            continue
        if iid in seen_ids:
            dropped["dup_id"] += 1
            continue
        seen_ids.add(iid)
        width = int(image.get("width") or 0)
        height = int(image.get("height") or 0)
        long_edge, short_edge = long_short(width, height)
        if long_edge < MIN_LONG or short_edge < MIN_SHORT:
            dropped["small"] += 1
            continue
        meta = image.get("meta") or {}
        prompt = (meta.get("prompt") or "").strip()
        if len(prompt) < 8:
            dropped["no_prompt"] += 1
            continue
        tags = prompt_tags(prompt)
        ok, why = screen(
            prompt,
            tags,
            minor_flag=flag_true(image.get("minor")),
            poi_flag=flag_true(image.get("poi")),
        )
        if not ok:
            dropped[why] += 1
            continue
        if not has_person_signal(prompt, tags):
            dropped["no_person"] += 1
            continue
        key = prompt[:90].lower()
        if key in seen_prompt:
            dropped["dup_prompt"] += 1
            continue
        seen_prompt.add(key)
        rating = rating_for(image.get("nsfwLevel"), prompt)
        notes = style_notes(prompt, base_model=base, rating=rating)
        title = model_name.strip() or tags[0]
        rows.append(
            {
                "source": "civitai",
                "url": f"https://civitai.com/images/{iid}",
                "image_url": url,
                "id": iid,
                "title": title[:120],
                "tags": tags,
                "rating": rating,
                "style_notes": notes,
                "width": width,
                "height": height,
                "author": "",
                "nsfw_level": image.get("nsfwLevel"),
                "ai_generated": "yes",
                "base_model": base,
                "model_id": str(model.get("model_id") or ""),
                "model_name": model_name,
                "quality": long_edge,
                "screen": why,
            }
        )
    return rows


def load_catalog_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids: set[str] = set()
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("id"):
                ids.add(str(row["id"]))
    return ids


def adult_pending_rows(
    rows: list[dict],
    existing_ids: set[str],
    *,
    cap: int = ADULT_PENDING_CAP,
    per_model: int = ADULT_PENDING_PER_MODEL,
) -> list[dict]:
    """Adult rows that are not already in the reviewed catalog."""
    ordered = sorted(
        (
            row
            for row in rows
            if row.get("rating") == "adult" and str(row.get("id")) not in existing_ids
        ),
        key=lambda row: int(row.get("quality") or 0),
        reverse=True,
    )
    picked: list[dict] = []
    per: Counter = Counter()
    seen: set[str] = set()
    for row in ordered:
        image_id_value = str(row["id"])
        if image_id_value in seen or image_id_value in VISUAL_BLOCKLIST or image_id_value in existing_ids:
            continue
        model_id = str(row.get("model_id") or image_id_value)
        if per[model_id] >= per_model:
            continue
        seen.add(image_id_value)
        per[model_id] += 1
        item = dict(row)
        item["visual_review"] = "pending"
        item["collected_via"] = "civitai_public_api"
        item["keep_reason"] = (
            "Metadata screen only on a public Civitai model-version prompt. "
            "Not a thumbnail pass. Full-size human review is required before download or training. "
            f"civitai adult; {item.get('width')}x{item.get('height')}; "
            f"{item.get('model_name') or item.get('base_model') or 'civitai'}."
        )
        picked.append(item)
        if len(picked) >= cap:
            break
    return picked


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=HERE.parent / "catalog" / "_civitai_candidates.jsonl",
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument(
        "--adult-pending-jsonl",
        type=Path,
        default=HERE.parent / "catalog" / "civitai_adult_pending.jsonl",
    )
    parser.add_argument(
        "--adult-pending-csv",
        type=Path,
        default=HERE.parent / "catalog" / "civitai_adult_pending.csv",
    )
    parser.add_argument(
        "--existing-catalog",
        type=Path,
        default=HERE.parent / "catalog" / "style_candidates.csv",
    )
    args = parser.parse_args()

    dropped: Counter = Counter()
    models = model_rows(args.refresh)
    print(f"models {len(models)}", file=sys.stderr)
    rows: list[dict] = []
    seen_ids: set[str] = set()
    for model in models:
        for row in candidates_from_version(model, args.refresh, dropped):
            if row["id"] in seen_ids:
                continue
            seen_ids.add(row["id"])
            rows.append(row)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = {
        "source": "civitai",
        "models": len(models),
        "candidates": len(rows),
        "ratings": dict(Counter(r["rating"] for r in rows)),
        "dropped": dict(dropped),
    }
    existing_ids = load_catalog_ids(args.existing_catalog)
    pending = adult_pending_rows(rows, existing_ids)
    write_outputs(pending, args.adult_pending_jsonl, args.adult_pending_csv)
    summary["adult_pending"] = len(pending)
    summary["adult_pending_new"] = len(pending)
    summary_path = args.out.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
