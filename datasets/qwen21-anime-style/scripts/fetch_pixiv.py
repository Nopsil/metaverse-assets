"""Fetch public Pixiv illustration metadata for the all-ages style catalog.

The ajax search and illust endpoints used here respond without a login for
safe-mode works. R-18 results are login-gated; this script probes that once
and records a TODO instead of inventing URLs. No cookies, tokens, or secrets.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from collections import Counter
from pathlib import Path

from http_cache import get_json
from safety import has_person_signal, rating_for, screen, style_notes

HERE = Path(__file__).resolve().parent
PIXIV_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.pixiv.net/",
}

# (word, pages). Popular-original tags first; style tags second.
SEARCHES = [
    ("オリジナル1000users入り 女性", 3),
    ("厚塗り オリジナル1000users入り", 2),
    ("お姉さん オリジナル1000users入り", 2),
    ("ギャル オリジナル1000users入り", 2),
    ("ファンタジー 女性 オリジナル1000users入り", 2),
    ("アニメ塗り オリジナル", 2),
    ("清楚 お姉さん オリジナル", 1),
    ("着物 女性 オリジナル", 1),
    ("騎士 女性 オリジナル", 1),
    ("魔女 女性 オリジナル", 1),
    ("ミリタリー 女性 オリジナル", 1),
    ("長身 女性 オリジナル", 1),
]

DROP_TAGS = {"漫画", "講座", "メイキング", "tutorial", "making of", "4コマ", "漫画用"}
MIN_SHORT = 768
MIN_LONG = 1024
MAX_PAGES = 3


def search_url(
    word: str,
    page: int,
    mode: str,
    *,
    order: str = "date_d",
    start_date: str = "",
    end_date: str = "",
    artwork_type: str = "illustrations",
    min_bookmarks: int = 0,
    exclude_ai: bool = False,
    min_width: int = 1024,
) -> str:
    """Ajax illustration search. Defaults stay the public safe-mode call.

    Hot R-18 collection passes order=popular_d, type=illust, scd/ecd, and blt.
    """
    params = {
        "word": word,
        "order": order,
        "mode": mode,
        "p": page,
        "csw": 0,
        "s_mode": "s_tag",
        "type": artwork_type,
        "lang": "en",
        "wlt": min_width,
    }
    if start_date:
        params["scd"] = start_date
    if end_date:
        params["ecd"] = end_date
    if min_bookmarks > 0:
        params["blt"] = min_bookmarks
    # Pixiv ai_type=1 is "exclude AI-generated works". Human art stays.
    if exclude_ai:
        params["ai_type"] = 1
    return (
        "https://www.pixiv.net/ajax/search/illustrations/"
        f"{urllib.parse.quote(word)}?{urllib.parse.urlencode(params)}"
    )


def ranking_url(page: int) -> str:
    return (
        "https://www.pixiv.net/ranking.php?mode=monthly&content=illust"
        f"&p={page}&format=json"
    )


def illust_url(illust_id: str) -> str:
    return f"https://www.pixiv.net/ajax/illust/{illust_id}"


def long_short(width: int, height: int) -> tuple[int, int]:
    return max(width, height), min(width, height)


def collect_search(refresh: bool, dropped: Counter) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for word, pages in SEARCHES:
        for page in range(1, pages + 1):
            try:
                payload = get_json(search_url(word, page, "safe"), headers=PIXIV_HEADERS, refresh=refresh)
            except Exception as exc:  # noqa: BLE001
                print(f"skip search {word} p{page}: {exc}", file=sys.stderr)
                dropped["search_fetch"] += 1
                continue
            illust = (payload.get("body") or {}).get("illust") or {}
            for item in illust.get("data") or []:
                iid = str(item.get("id") or "")
                if not iid or iid in found:
                    continue
                if item.get("isMasked") or item.get("xRestrict") not in (0, "0", None):
                    dropped["masked_or_r18"] += 1
                    continue
                if item.get("aiType") == 2:
                    dropped["ai_generated"] += 1
                    continue
                if int(item.get("illustType") or 0) != 0:
                    dropped["not_illust"] += 1
                    continue
                found[iid] = item
    for page in range(1, 4):
        try:
            payload = get_json(ranking_url(page), headers=PIXIV_HEADERS, refresh=refresh)
        except Exception as exc:  # noqa: BLE001
            print(f"skip ranking p{page}: {exc}", file=sys.stderr)
            continue
        for item in payload.get("contents") or []:
            content = item.get("illust_content_type") or {}
            if content.get("lo") or content.get("furry") or content.get("grotesque"):
                dropped["ranking_flagged"] += 1
                continue
            if not content.get("original"):
                dropped["ranking_not_original"] += 1
                continue
            iid = str(item.get("illust_id") or "")
            if not iid or iid in found:
                continue
            found[iid] = {
                "id": iid,
                "title": item.get("title") or "",
                "tags": item.get("tags") or [],
                "width": item.get("width"),
                "height": item.get("height"),
                "userName": item.get("user_name") or "",
                "userId": item.get("user_id") or "",
                "aiType": 0,
                "xRestrict": 0,
                "pageCount": item.get("illust_page_count") or 1,
                "url": item.get("url") or "",
                "_from_ranking": True,
                "_rating_count": item.get("rating_count") or 0,
            }
    return found


def probe_r18(refresh: bool) -> dict:
    """Document that public R-18 search does not return restricted works."""
    url = search_url("お姉さん オリジナル", 1, "r18")
    try:
        payload = get_json(url, headers=PIXIV_HEADERS, refresh=refresh)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "todo": "Retry with the artist's own login. Do not commit cookies."}
    data = ((payload.get("body") or {}).get("illust") or {}).get("data") or []
    restricted = [row for row in data if row.get("xRestrict") not in (0, "0", None)]
    return {
        "ok": True,
        "queried": "お姉さん オリジナル",
        "mode": "r18",
        "returned": len(data),
        "xrestrict_positive": len(restricted),
        "login_required": len(restricted) == 0,
        "todo": (
            "Do not collect Pixiv R-18 from a US cloud VM. Public mode=r18 omits "
            "restricted works, and Pixiv blocks many datacenter IPs. On a home Windows "
            "PC run scripts/collect_pixiv_windows.py, or paste artwork URLs and run "
            "scripts/merge_exports.py. Do not commit cookies."
        ),
    }


def row_from_detail(stub: dict, detail: dict, dropped: Counter) -> dict | None:
    body = detail.get("body") or {}
    if not body or body.get("isMasked"):
        dropped["detail_masked"] += 1
        return None
    if body.get("xRestrict") not in (0, "0", None):
        dropped["detail_r18"] += 1
        return None
    if body.get("aiType") == 2:
        dropped["ai_generated"] += 1
        return None
    tags = [t.get("tag") for t in ((body.get("tags") or {}).get("tags") or []) if t.get("tag")]
    if not tags:
        tags = list(stub.get("tags") or [])
    if any(tag.lower() in DROP_TAGS or tag in DROP_TAGS for tag in tags):
        dropped["comic_or_tutorial"] += 1
        return None
    pages = int(body.get("pageCount") or stub.get("pageCount") or 1)
    if pages > MAX_PAGES:
        dropped["multi_page"] += 1
        return None
    width = int(body.get("width") or stub.get("width") or 0)
    height = int(body.get("height") or stub.get("height") or 0)
    long_edge, short_edge = long_short(width, height)
    if long_edge < MIN_LONG or short_edge < MIN_SHORT:
        dropped["small"] += 1
        return None
    title = body.get("title") or stub.get("title") or ""
    description = body.get("description") or body.get("illustComment") or ""
    # Tags and title are the safety text. Descriptions quote user prose and
    # often mention unrelated words; a match there still counts.
    blob = " ".join([title, description, " ".join(tags)])
    ok, why = screen(blob, tags, lo_flag=False)
    if not ok:
        dropped[why] += 1
        return None
    if not has_person_signal(blob, tags):
        dropped["no_person"] += 1
        return None
    bookmarks = int(body.get("bookmarkCount") or stub.get("_rating_count") or 0)
    if bookmarks < 200 and "1000users入り" not in "".join(tags) and "1000users入り" not in " ".join(tags):
        # Popular-original tag is not always spelled as its own token.
        popular = any("1000users" in tag or "users入り" in tag for tag in tags)
        if not popular and bookmarks < 200:
            dropped["low_bookmarks"] += 1
            return None
    rating = rating_for(0, blob)
    # Safe-mode Pixiv rows in this pass are all-ages even if a tag is suggestive.
    if body.get("xRestrict") in (0, "0", None):
        rating = "all-ages"
    notes = style_notes(" ".join(tags + [title]), rating=rating)
    author = body.get("userName") or stub.get("userName") or ""
    urls = body.get("urls") or {}
    return {
        "source": "pixiv",
        "url": f"https://www.pixiv.net/artworks/{body.get('id') or stub.get('id')}",
        "image_url": urls.get("small") or urls.get("regular") or stub.get("url") or "",
        "id": str(body.get("id") or stub.get("id")),
        "title": str(title)[:120],
        "tags": tags[:16],
        "rating": rating,
        "style_notes": notes,
        "width": width,
        "height": height,
        "author": author,
        "nsfw_level": "None",
        "ai_generated": "no" if body.get("aiType") == 1 else "unknown",
        "base_model": "",
        "model_id": "",
        "model_name": "",
        "quality": bookmarks or long_edge,
        "screen": why,
        "user_id": str(body.get("userId") or stub.get("userId") or ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=HERE.parent / "catalog" / "_pixiv_candidates.jsonl",
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--limit-details", type=int, default=220)
    args = parser.parse_args()

    dropped: Counter = Counter()
    stubs = collect_search(args.refresh, dropped)
    print(f"pixiv stubs {len(stubs)}", file=sys.stderr)
    # Prefer tagged popular works, then ranking originals.
    ordered = sorted(
        stubs.values(),
        key=lambda row: (
            0 if any("1000users" in str(t) for t in (row.get("tags") or [])) else 1,
            -int(row.get("_rating_count") or 0),
        ),
    )
    rows: list[dict] = []
    for stub in ordered[: args.limit_details]:
        iid = str(stub.get("id"))
        try:
            detail = get_json(illust_url(iid), headers=PIXIV_HEADERS, refresh=args.refresh, delay_s=0.35)
        except Exception as exc:  # noqa: BLE001
            print(f"skip illust {iid}: {exc}", file=sys.stderr)
            dropped["detail_fetch"] += 1
            continue
        row = row_from_detail(stub, detail, dropped)
        if row:
            rows.append(row)

    r18 = probe_r18(args.refresh)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = {
        "source": "pixiv",
        "stubs": len(stubs),
        "candidates": len(rows),
        "ratings": dict(Counter(r["rating"] for r in rows)),
        "dropped": dict(dropped),
        "r18_probe": r18,
    }
    summary_path = args.out.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
