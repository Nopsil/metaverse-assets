"""Fetch Civitai public model-showcase metadata for the anime style catalog.

Uses https://civitai.com/api/v1 only. No API token. Rate-limited and cached.
Does not download image binaries. Prints a JSONL candidate file.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from collections import Counter
from pathlib import Path

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
    {"types": "Checkpoint", "baseModels": "Illustrious", "sort": "Most Downloaded", "nsfw": "true", "limit": 12},
    {"types": "LORA", "query": "anime style", "baseModels": "Illustrious", "sort": "Highest Rated", "nsfw": "false", "limit": 10},
    {"types": "LORA", "query": "cel shading", "sort": "Highest Rated", "nsfw": "false", "limit": 8},
]

SKIP_MODEL = re.compile(
    r"(?i)\b(?:lolis?|shotas?|child|children|toddler|infant|teens?|schoolgirl|"
    r"furry|pony|photoreal|realism|celebrity|underage|3dcg)\b"
)

ID_RE = re.compile(r"/(\d+)\.(?:jpeg|jpg|png|webp)(?:\?|$)", re.I)
MAX_PER_MODEL = 6
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
            seen.add(mid)
            found.append(
                {
                    "model_id": mid,
                    "model_name": name,
                    "version_id": version.get("id"),
                    "base_model": base,
                    "model_nsfw": bool(item.get("nsfw")),
                }
            )
    return found


def candidates_from_version(model: dict, refresh: bool, dropped: Counter) -> list[dict]:
    vid = model.get("version_id")
    if not vid:
        return []
    try:
        payload = get_json(f"{API}/model-versions/{vid}", refresh=refresh)
    except Exception as exc:  # noqa: BLE001
        print(f"skip version {vid}: {exc}", file=sys.stderr)
        dropped["version_fetch"] += 1
        return []

    base = payload.get("baseModel") or model.get("base_model") or ""
    model_name = (payload.get("model") or {}).get("name") or model.get("model_name") or ""
    rows: list[dict] = []
    seen_prompt: set[str] = set()
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
            minor_flag=image.get("minor"),
            poi_flag=image.get("poi"),
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
        if len(rows) >= MAX_PER_MODEL:
            break
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=HERE.parent / "catalog" / "_civitai_candidates.jsonl",
    )
    parser.add_argument("--refresh", action="store_true")
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
    summary_path = args.out.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
