"""Build local contact sheets for human age review. Not committed.

Reads catalog JSONL, downloads small previews into /tmp, writes PNG sheets.
Requires Pillow. Pixiv CDN needs a Referer header.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def thumb_url(row: dict) -> str:
    image_url = row.get("image_url") or ""
    if "image.civitai.com" in image_url and "/original=true/" in image_url:
        return image_url.replace("/original=true/", "/width=480/")
    return image_url


def fetch(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.pixiv.net/" if "pximg.net" in url else "https://civitai.com/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            dest.write_bytes(resp.read())
        return dest.stat().st_size > 0
    except Exception:
        return False


def sheet(paths: list[tuple[Path, str]], dest: Path, cols: int = 4) -> None:
    cell_w, cell_h, label_h = 280, 280, 36
    rows = (len(paths) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * cell_w, rows * (cell_h + label_h)), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for index, (path, label) in enumerate(paths):
        col = index % cols
        row = index // cols
        x = col * cell_w
        y = row * (cell_h + label_h)
        try:
            img = Image.open(path).convert("RGB")
            img.thumbnail((cell_w - 8, cell_h - 8))
            canvas.paste(img, (x + 4, y + 4))
        except Exception:
            draw.rectangle((x + 4, y + 4, x + cell_w - 4, y + cell_h - 4), outline="red")
        draw.text((x + 6, y + cell_h), label[:42], fill="black", font=font)
    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, default=Path("/tmp/qwen21-review"))
    parser.add_argument("--per-sheet", type=int, default=12)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    thumb_dir = args.outdir / "thumbs"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    batch: list[tuple[Path, str]] = []
    sheet_index = 0
    for row in rows:
        url = thumb_url(row)
        dest = thumb_dir / f"{row['source']}_{row['id']}.jpg"
        ok = bool(url) and fetch(url, dest)
        label = f"{row['source'][:3]} {row['id']} {row['rating'][:5]}"
        batch.append((dest if ok else Path("/nonexistent"), label))
        if len(batch) == args.per_sheet:
            sheet(batch, args.outdir / f"sheet_{sheet_index:02d}.png")
            sheet_index += 1
            batch = []
    if batch:
        sheet(batch, args.outdir / f"sheet_{sheet_index:02d}.png")
    print(f"sheets {sheet_index + (1 if batch else 0)} from {len(rows)} rows -> {args.outdir}")


if __name__ == "__main__":
    main()
