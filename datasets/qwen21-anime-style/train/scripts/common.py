"""Shared paths and caption checks for the Qwen Image 2.1 LoRA scaffold.

No network, no model load, no GPU. Training and caption launch live in
run_train.py and caption_originals.py and only run when those commands
are invoked on a machine that already has the weights.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

DATASET = Path(__file__).resolve().parents[2]
REPO_ROOT = DATASET.parents[1]
SCRIPTS = DATASET / "scripts"
CONFIG_DIR = DATASET / "train" / "configs"
RENDER_DIR = DATASET / "train" / "rendered"
DATA_DIR = DATASET / "train" / "data"
OUTPUT_DIR = DATASET / "train" / "output"
REJECT_DIR = DATASET / "train" / "rejected"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
SKIP_NAME_MARKERS = ("master1200", "square1200", "img-master", "custom-thumb")

STYLE_ANCHOR = "anime style, cel shading, clean lineart"
ANATOMY_ANCHOR = "anime cel shading, clean genital join"
ANCHORS = {"style": STYLE_ANCHOR, "anatomy": ANATOMY_ANCHOR}

# One or two sentences. The .txt file is what Qwen Image 2.1 trains on.
# Trigger words are not used: cached text embeddings ignore trigger_word.
CAPTION_PROMPTS = {
    "style": (
        "Write one or two natural English sentences a person would type as an image prompt. "
        "Describe the adult subject's pose, camera distance, expression, how open the mouth is, "
        "costume, lighting, and background. Say that the subject is an adult woman or an adult man. "
        "Do not name a character, series, artist, or age. Do not use a booru tag list. "
        "Do not mention school, uniforms, or children. "
        "If the picture is not a clearly adult person, reply with only the word SKIP."
    ),
    "anatomy": (
        "Write one or two natural English sentences. Every person in the picture is an adult. "
        "Describe the pose, the camera distance, and the visible adult anatomy in plain words, "
        "including the join, limb separation, nipples, and fluids if they are visible. "
        "Do not name a character, series, artist, or age. Do not mention school or children. "
        "If anyone in the picture is not a clearly adult person, reply with only the word SKIP."
    ),
}

DATASET_TOKEN = "__DATASET_DIR__"
OUTPUT_TOKEN = "__OUTPUT_DIR__"

SHUTDOWN_NOTE = (
    "Copy the .safetensors files off this machine, then stop the OneThing H100 "
    "in the provider console. This repo does not start or stop the instance."
)


def ensure_safety_path() -> None:
    import sys

    folder = str(SCRIPTS)
    if folder not in sys.path:
        sys.path.insert(0, folder)


def screen_text(text: str) -> tuple[bool, str]:
    ensure_safety_path()
    from safety import screen

    return screen(text)


def finish_caption(text: str, track: str) -> tuple[str, str]:
    """Return (status, caption). status is 'ok' or a reject reason."""
    if track not in ANCHORS:
        raise ValueError(f"track must be style or anatomy, got {track}")
    raw = " ".join((text or "").split())
    if not raw or raw.upper() == "SKIP":
        return "empty_or_skip", ""
    ok, why = screen_text(raw)
    if not ok:
        return why, ""
    anchor = ANCHORS[track]
    if anchor.lower() not in raw.lower():
        raw = raw.rstrip(" .") + ". " + anchor
    return "ok", raw


def image_size(path: Path) -> tuple[int, int] | None:
    """Width, height for PNG, JPEG, and WebP. None if the header is unknown."""
    try:
        # JPEG SOF can sit past a large EXIF/ICC block. PNG and WebP sizes
        # are in the first 32 bytes; the extra read is for JPEG only.
        with path.open("rb") as handle:
            data = handle.read(8_000_000)
    except OSError:
        return None
    for reader in (_png_size, _jpeg_size, _webp_size):
        size = reader(data)
        if size is not None:
            return size
    return None


def _png_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    if width <= 0 or height <= 0:
        return None
    return width, height


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None
    index = 2
    sof = {0xC0, 0xC1, 0xC2}
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        while index < len(data) and data[index] == 0xFF:
            index += 1
        if index >= len(data):
            return None
        marker = data[index]
        index += 1
        if marker in (0xD8, 0xD9):
            continue
        if marker == 0xDA:
            return None
        if index + 2 > len(data):
            return None
        seglen = int.from_bytes(data[index : index + 2], "big")
        if seglen < 2 or index + seglen > len(data):
            return None
        if marker in sof and seglen >= 7:
            height = int.from_bytes(data[index + 3 : index + 5], "big")
            width = int.from_bytes(data[index + 5 : index + 7], "big")
            if width > 0 and height > 0:
                return width, height
        index += seglen
    return None


def _webp_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    chunk = data[12:16]
    if chunk == b"VP8X":
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height
    if chunk == b"VP8L":
        b0, b1, b2, b3 = data[21:25]
        width = 1 + (((b1 & 0x3F) << 8) | b0)
        height = 1 + (((b3 & 0x0F) << 10) | (b2 << 2) | ((b1 & 0xC0) >> 6))
        return width, height
    if chunk == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
        width = int.from_bytes(data[26:28], "little") & 0x3FFF
        height = int.from_bytes(data[28:30], "little") & 0x3FFF
        if width > 0 and height > 0:
            return width, height
    return None


def iter_images(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in IMAGE_EXTS:
            continue
        if path.name.startswith("."):
            continue
        lower = path.name.lower()
        if any(marker in lower for marker in SKIP_NAME_MARKERS):
            continue
        if any(part.startswith(".") or part.startswith("_") for part in path.relative_to(folder).parts[:-1]):
            continue
        found.append(path)
    return found


def assert_data_dest(dest: Path) -> None:
    """Images may land in train/data, or outside the git repo. Nowhere else."""
    resolved = dest.resolve()
    data = DATA_DIR.resolve()
    if resolved == data or data in resolved.parents:
        return
    repo = REPO_ROOT.resolve()
    if resolved == repo or repo in resolved.parents:
        raise SystemExit(
            "Refusing to write images inside the repo except datasets/qwen21-anime-style/train/data/."
        )


def png_bytes(width: int, height: int) -> bytes:
    """Tiny valid PNG used by tests. Not a training image."""

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + (b"\x00\x00\x00" * width) for _ in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def dataset_problems(folder: Path, track: str) -> tuple[list[str], list[str]]:
    """Hard errors, then warnings. Does not read the GPU."""
    errors: list[str] = []
    warnings: list[str] = []
    if track not in ANCHORS:
        return [f"unknown track {track}"], []
    if not folder.is_dir():
        return [f"missing dataset folder {folder}"], []
    images = iter_images(folder)
    if not images:
        return [f"no images in {folder}"], []
    anchor = ANCHORS[track]
    for image in images:
        caption_path = image.with_suffix(".txt")
        if not caption_path.is_file():
            errors.append(f"missing caption {caption_path.name}")
            continue
        text = caption_path.read_text(encoding="utf-8").strip()
        status, _ = finish_caption(text, track)
        if status != "ok":
            errors.append(f"{caption_path.name}: {status}")
            continue
        if anchor.lower() not in text.lower():
            errors.append(f"{caption_path.name}: missing anchor (run caption_originals.py --apply)")
    floor = 40 if track == "style" else 80
    if len(images) < floor:
        warnings.append(
            f"{track} has {len(images)} images. The plan wants a diverse style slice, "
            f"and about 150-300 anatomy images (under {floor} is small)."
        )
    return errors, warnings
