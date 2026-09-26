"""Choose Pixiv img-original URLs. No browser and no file writes.

Ugoira is skipped: it is an animation, not a still plate. Multi-page works
keep the first few stills so a long comic does not flood the folder.
Square and master thumbnails are never accepted.
"""

from __future__ import annotations

from pixiv_home import illust_tags
from safety import screen

MAX_ORIGINAL_PAGES = 3

_THUMB_MARKERS = (
    "img-master",
    "master1200",
    "square1200",
    "custom-thumb",
    "/c/",
)


def is_original_url(url: str) -> bool:
    text = (url or "").strip()
    if not text or "i.pximg.net" not in text.lower():
        return False
    lower = text.lower()
    if "/img-original/" not in lower:
        return False
    return not any(marker in lower for marker in _THUMB_MARKERS)


def extension_for(url: str) -> str:
    path = url.split("?", 1)[0].lower()
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return ".jpg"


def file_name(artwork_id: str, index: int, url: str) -> str:
    return f"{artwork_id}_p{index}{extension_for(url)}"


def safety_skip(body: dict) -> str | None:
    """Series, character, tags, and stated age. Not body proportions."""
    tags = illust_tags(body)
    title = str(body.get("title") or "")
    description = str(body.get("description") or body.get("illustComment") or "")
    ok, why = screen(f"{title} {description} {' '.join(tags)}", tags, lo_flag=bool(body.get("lo")))
    if not ok:
        return why
    return None


def originals_for_illust(body: dict, pages_body: list | None = None) -> dict:
    """Return original URLs or a skip reason.

    ``truncated`` is how many pages past MAX_ORIGINAL_PAGES were not taken.
    """
    if not isinstance(body, dict) or not body:
        return {"urls": [], "skip": "no_detail", "truncated": 0}
    try:
        illust_type = int(body.get("illustType") or 0)
    except (TypeError, ValueError):
        illust_type = 0
    if illust_type == 2:
        return {"urls": [], "skip": "ugoira", "truncated": 0}
    why = safety_skip(body)
    if why:
        return {"urls": [], "skip": why, "truncated": 0}
    try:
        page_count = int(body.get("pageCount") or 1)
    except (TypeError, ValueError):
        page_count = 1
    if page_count > 1:
        pages = list(pages_body or [])
        urls: list[str] = []
        for page in pages[:MAX_ORIGINAL_PAGES]:
            url = str(((page or {}).get("urls") or {}).get("original") or "")
            if is_original_url(url):
                urls.append(url)
        if not urls:
            return {"urls": [], "skip": "no_original", "truncated": 0}
        extra = max(0, len(pages) - MAX_ORIGINAL_PAGES)
        return {"urls": urls, "skip": "", "truncated": extra}
    url = str(((body.get("urls") or {}).get("original") or ""))
    if not is_original_url(url):
        return {"urls": [], "skip": "no_original", "truncated": 0}
    return {"urls": [url], "skip": "", "truncated": 0}
