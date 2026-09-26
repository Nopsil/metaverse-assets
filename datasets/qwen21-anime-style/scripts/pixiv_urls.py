"""Parse Pixiv and Civitai page URLs. No network and no cookies."""

from __future__ import annotations

import re
from dataclasses import dataclass

PIXIV_RE = re.compile(
    r"(?:https?://)?(?:www\.)?pixiv\.net/(?:[a-z]{2}/)?(?:artworks|i)/(\d+)\b",
    re.I,
)
CIVITAI_RE = re.compile(
    r"(?:https?://)?(?:www\.)?civitai\.com/images/(\d+)\b",
    re.I,
)


@dataclass(frozen=True)
class ArtworkRef:
    source: str
    id: str
    url: str


def parse_artwork_url(text: str) -> ArtworkRef | None:
    raw = (text or "").strip()
    if not raw or raw.startswith("#"):
        return None
    pixiv = PIXIV_RE.search(raw)
    if pixiv:
        artwork_id = pixiv.group(1)
        return ArtworkRef("pixiv", artwork_id, f"https://www.pixiv.net/artworks/{artwork_id}")
    civitai = CIVITAI_RE.search(raw)
    if civitai:
        image_id = civitai.group(1)
        return ArtworkRef("civitai", image_id, f"https://civitai.com/images/{image_id}")
    return None


def refs_from_text(text: str) -> list[ArtworkRef]:
    found: list[ArtworkRef] = []
    seen: set[tuple[str, str]] = set()
    for line in text.splitlines():
        # A line may mention more than one URL.
        matches = list(PIXIV_RE.finditer(line)) + list(CIVITAI_RE.finditer(line))
        if not matches:
            continue
        for match in matches:
            ref = parse_artwork_url(match.group(0))
            if ref is None:
                continue
            key = (ref.source, ref.id)
            if key in seen:
                continue
            seen.add(key)
            found.append(ref)
    return found
