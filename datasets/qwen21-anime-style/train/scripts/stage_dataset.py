"""Copy reviewed full-size images into the gitignored training folders.

Does not download, caption, or train. New Pixiv originals live in
catalog/_originals_hot/ after download_pixiv_originals.py. The old
catalog/_originals/ tree and catalog/quarantine/ are train-unready.
Civitai full-size files and anatomy stills are separate folders you pass with --src.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from common import DATA_DIR, DATASET, IMAGE_EXTS, assert_data_dest, image_size, iter_images


def assert_trainable_source(source: Path) -> None:
    """The previous aesthetic snapshot stays on disk and out of the train copy."""
    parts = [part.lower() for part in source.resolve().parts]
    if "quarantine" in parts or "_originals_quarantine" in parts:
        raise SystemExit(f"Refusing train-unready quarantine: {source}")
    if "_originals" in parts:
        raise SystemExit(
            f"Refusing deprecated catalog/_originals: {source}. Stage catalog/_originals_hot after review."
        )


def stage(
    sources: list[Path],
    dest: Path,
    *,
    min_long: int = 1024,
    min_short: int = 768,
) -> dict:
    for source in sources:
        assert_trainable_source(source)
    assert_data_dest(dest)
    dest.mkdir(parents=True, exist_ok=True)
    copied = 0
    skipped: list[str] = []
    seen: set[str] = set()
    for source in sources:
        if not source.is_dir():
            skipped.append(f"missing_src:{source}")
            continue
        for image in iter_images(source):
            if image.name in seen:
                skipped.append(f"duplicate_name:{image.name}")
                continue
            seen.add(image.name)
            size = image_size(image)
            if size is None:
                skipped.append(f"unknown_size:{image.name}")
                continue
            width, height = size
            long_edge = max(width, height)
            short_edge = min(width, height)
            if long_edge < min_long or short_edge < min_short:
                skipped.append(f"small:{image.name}:{width}x{height}")
                continue
            if image.suffix.lower() not in IMAGE_EXTS:
                continue
            target = dest / image.name
            if target.exists() and target.stat().st_size == image.stat().st_size:
                skipped.append(f"exists:{image.name}")
                continue
            replaced = target.exists()
            shutil.copy2(image, target)
            if replaced:
                sidecar = target.with_suffix(".txt")
                if sidecar.exists():
                    sidecar.unlink()
                skipped.append(f"replaced_cleared_caption:{image.name}")
            copied += 1
    return {"copied": copied, "skipped": skipped, "dest": str(dest)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", choices=("style", "anatomy"), default="style")
    parser.add_argument(
        "--src",
        type=Path,
        action="append",
        default=None,
        help="Folder of full-size images. Repeat for more than one folder.",
    )
    parser.add_argument("--dest", type=Path, default=None)
    parser.add_argument("--min-long", type=int, default=1024)
    parser.add_argument("--min-short", type=int, default=768)
    args = parser.parse_args()
    if args.src:
        sources = args.src
    elif args.track == "style":
        sources = [DATASET / "catalog" / "_originals_hot", DATASET / "catalog" / "_originals_civitai"]
    else:
        sources = [DATASET / "catalog" / "_originals_anatomy"]
    dest = args.dest or (DATA_DIR / args.track)
    result = stage(sources, dest, min_long=args.min_long, min_short=args.min_short)
    print(
        f"copied {result['copied']} -> {result['dest']}\n"
        f"skipped {len(result['skipped'])}"
    )
    for line in result["skipped"]:
        print(line, file=sys.stderr)


if __name__ == "__main__":
    main()
