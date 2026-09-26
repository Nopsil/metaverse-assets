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
    if body.get("isMasked"):
        return "masked"
    try:
        if int(body.get("xRestrict") or 0) >= 2:
            return "r18g"
    except (TypeError, ValueError):
        return "bad_restrict"
    tags = illust_tags(body)
    title = str(body.get("title") or "")
    description = str(body.get("description") or body.get("illustComment") or "")
    alt = str(body.get("alt") or "")
    series_nav = body.get("seriesNavData") if isinstance(body.get("seriesNavData"), dict) else {}
    series = str((series_nav or {}).get("title") or "")
    blob = " ".join([title, description, alt, series, " ".join(tags)])
    ok, why = screen(blob, tags, lo_flag=bool(body.get("lo")))
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
        sizes: list[tuple[int, int]] = []
        for page in pages[:MAX_ORIGINAL_PAGES]:
            page = page or {}
            url = str((page.get("urls") or {}).get("original") or "")
            if not is_original_url(url):
                continue
            urls.append(url.split("?", 1)[0].split("#", 1)[0])
            sizes.append(_page_size(page))
        if not urls:
            return {"urls": [], "sizes": [], "skip": "no_original", "truncated": 0}
        extra = max(0, len(pages) - MAX_ORIGINAL_PAGES)
        return {"urls": urls, "sizes": sizes, "skip": "", "truncated": extra}
    url = str(((body.get("urls") or {}).get("original") or ""))
    if not is_original_url(url):
        return {"urls": [], "sizes": [], "skip": "no_original", "truncated": 0}
    clean = url.split("?", 1)[0].split("#", 1)[0]
    return {"urls": [clean], "sizes": [_page_size(body)], "skip": "", "truncated": 0}


def _page_size(body: dict) -> tuple[int, int]:
    try:
        return int(body.get("width") or 0), int(body.get("height") or 0)
    except (TypeError, ValueError):
        return 0, 0


def image_size(data: bytes) -> tuple[int, int] | None:
    """Pixel size from a JPEG, PNG, GIF, or WEBP header. None if it is not one of those."""
    if not data or data[:1] in (b"<", b"{", b"["):
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24 and data[12:16] == b"IHDR":
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        return int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")
    if data[:4] == b"RIFF" and len(data) >= 30 and data[8:12] == b"WEBP":
        if data[12:16] == b"VP8X":
            return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
        if data[12:16] == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
            return int.from_bytes(data[26:28], "little") & 0x3FFF, int.from_bytes(data[28:30], "little") & 0x3FFF
        return None
    if data[:2] != b"\xff\xd8":
        return None
    sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    i = 2
    while i + 8 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        while i < len(data) and data[i] == 0xFF:
            i += 1
        if i >= len(data):
            return None
        marker = data[i]
        i += 1
        if marker in (0xD8, 0xD9) or marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if i + 1 >= len(data):
            return None
        seglen = int.from_bytes(data[i : i + 2], "big")
        if seglen < 2 or i + seglen > len(data):
            return None
        if marker in sof and seglen >= 7:
            height = int.from_bytes(data[i + 3 : i + 5], "big")
            width = int.from_bytes(data[i + 5 : i + 7], "big")
            return width, height
        i += seglen
    return None


def bytes_match_original(data: bytes, expect_w: int, expect_h: int) -> str | None:
    """None when the bytes are the full original. A reason string when they are not."""
    size = image_size(data)
    if size is None:
        return "not_image"
    width, height = size
    if expect_w > 0 and expect_h > 0:
        if (width, height) != (expect_w, expect_h):
            return f"size_{width}x{height}_expected_{expect_w}x{expect_h}"
        return None
    if max(width, height) < 1024 or min(width, height) < 768:
        return "below_fullsize_floor"
    return None
