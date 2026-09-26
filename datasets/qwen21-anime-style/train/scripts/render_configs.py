"""Fill dataset and output paths into the committed AI-Toolkit configs.

Writes gitignored train/rendered/*.yaml. Does not start training.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from common import CONFIG_DIR, DATA_DIR, DATASET_TOKEN, OUTPUT_DIR, OUTPUT_TOKEN, RENDER_DIR


KINDS = {
    "style": {
        "train": "style_lora.yaml",
        "caption": "caption_style.yaml",
    },
    "anatomy": {
        "train": "anatomy_lora.yaml",
        "caption": "caption_anatomy.yaml",
    },
}


def render(track: str, kind: str = "train", out_dir: Path | None = None) -> Path:
    if track not in KINDS or kind not in KINDS[track]:
        raise SystemExit(f"Unknown config {track} {kind}")
    name = KINDS[track][kind]
    template = (CONFIG_DIR / name).read_text(encoding="utf-8")
    dataset = (DATA_DIR / track).resolve().as_posix()
    output = OUTPUT_DIR.resolve().as_posix()
    rendered = template.replace(DATASET_TOKEN, dataset).replace(OUTPUT_TOKEN, output)
    if DATASET_TOKEN in rendered or OUTPUT_TOKEN in rendered:
        raise SystemExit(f"{name} still has an unreplaced path token")
    dest_dir = out_dir or RENDER_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name
    dest.write_text(rendered, encoding="utf-8")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    for track, kinds in KINDS.items():
        for kind in kinds:
            path = render(track, kind, args.out)
            print(path)


if __name__ == "__main__":
    main()
