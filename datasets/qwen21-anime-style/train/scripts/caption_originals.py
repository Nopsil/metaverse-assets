"""Caption the gitignored training folder, then screen the .txt files.

Default mode only reports. It does not load a model.

  --launch   run the AI-Toolkit Qwen3-VL captioner (uses the GPU)
  --apply    rewrite passing captions with the track anchor, and move
             failures to train/rejected/

--launch is for the H100 (or a home GPU) after the images are in
train/data/<track>/. This file does not start a cloud instance.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from common import (
    ANCHORS,
    CAPTION_PROMPTS,
    DATA_DIR,
    REJECT_DIR,
    finish_caption,
    iter_images,
)
from render_configs import render


def screen_folder(folder: Path, track: str, *, apply: bool, reject_dir: Path | None = None) -> dict:
    images = iter_images(folder)
    kept = 0
    rejected: list[dict] = []
    missing = 0
    for image in images:
        caption_path = image.with_suffix(".txt")
        if not caption_path.is_file() or not caption_path.read_text(encoding="utf-8").strip():
            missing += 1
            rejected.append({"file": image.name, "reason": "missing_caption"})
            continue
        status, cleaned = finish_caption(caption_path.read_text(encoding="utf-8"), track)
        if status != "ok":
            rejected.append({"file": image.name, "reason": status})
            if apply:
                _quarantine(image, caption_path, track, status, reject_dir or REJECT_DIR)
            continue
        kept += 1
        if apply:
            caption_path.write_text(cleaned + "\n", encoding="utf-8")
    return {"kept": kept, "missing": missing, "rejected": rejected, "anchor": ANCHORS[track]}


def _quarantine(image: Path, caption_path: Path, track: str, reason: str, reject_root: Path) -> None:
    dest = reject_root / track
    dest.mkdir(parents=True, exist_ok=True)
    for path in (image, caption_path):
        target = dest / path.name
        if target.exists():
            target.unlink()
        shutil.move(str(path), str(target))
    log = dest / "rejected.jsonl"
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"file": image.name, "reason": reason}, ensure_ascii=False) + "\n")


def launch_toolkit(track: str) -> int:
    toolkit = os.environ.get("AI_TOOLKIT_ROOT", "").strip()
    run_py = Path(toolkit) / "run.py" if toolkit else None
    if run_py is None or not run_py.is_file():
        print(
            "Set AI_TOOLKIT_ROOT to a clone of https://github.com/ostris/ai-toolkit "
            "(current main, with arch qwen_image_2). --launch was not started.",
            file=sys.stderr,
        )
        return 2
    if shutil.which("nvidia-smi") is None:
        print("nvidia-smi is not on this machine. Caption launch was not started.", file=sys.stderr)
        return 2
    probe = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True)
    if probe.returncode != 0:
        print(probe.stderr or probe.stdout, file=sys.stderr)
        print("No GPU visible. Caption launch was not started.", file=sys.stderr)
        return 2
    yaml_path = render(track=track, kind="caption")
    cmd = [sys.executable, str(run_py), str(yaml_path)]
    print("Caption prompt for this track:")
    print(CAPTION_PROMPTS[track])
    print("Running:", " ".join(cmd))
    try:
        return subprocess.call(cmd, cwd=toolkit)
    finally:
        print(
            "Caption step returned. Next is run_train.py --check, then run_train.py. "
            "Stop the OneThing H100 only after the LoRA has been copied off."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", choices=("style", "anatomy"), required=True)
    parser.add_argument("--images", type=Path, default=None)
    parser.add_argument("--apply", action="store_true", help="Rewrite captions and quarantine failures.")
    parser.add_argument("--launch", action="store_true", help="Run the AI-Toolkit captioner on the GPU.")
    parser.add_argument(
        "--run-transformers",
        action="store_true",
        help="Caption with transformers Qwen3-VL on this GPU instead of AI-Toolkit.",
    )
    args = parser.parse_args()
    folder = args.images or (DATA_DIR / args.track)
    if args.launch or args.run_transformers:
        code = launch_toolkit(args.track) if args.launch else caption_with_transformers(folder, args.track)
        if code != 0:
            raise SystemExit(code)
    if not folder.is_dir() or not iter_images(folder):
        print(f"No images in {folder}", file=sys.stderr)
        raise SystemExit(2)
    result = screen_folder(folder, args.track, apply=args.apply)
    print(
        f"kept {result['kept']}  missing {result['missing']}  "
        f"rejected {len(result['rejected'])}  anchor: {result['anchor']}"
    )
    for row in result["rejected"]:
        print(f"{row['reason']}\t{row['file']}", file=sys.stderr)
    if result["missing"] or result["rejected"]:
        raise SystemExit(2)


def caption_with_transformers(folder: Path, track: str) -> int:
    """Optional local captioner. Imports torch only after this function is called."""
    if shutil.which("nvidia-smi") is None:
        print("nvidia-smi is not on this machine. Transformers caption was not started.", file=sys.stderr)
        return 2
    try:
        import torch
        from PIL import Image
        from transformers import AutoModelForImageTextToText, AutoProcessor
    except ImportError as exc:
        print(
            "transformers, torch, and pillow are not installed in this environment. "
            f"Use --launch with AI-Toolkit instead ({exc}).",
            file=sys.stderr,
        )
        return 2
    model_id = os.environ.get("QWEN_VL_MODEL", "Qwen/Qwen3-VL-8B-Instruct")
    print(f"Loading {model_id} in bf16. This downloads weights on first use.")
    model = AutoModelForImageTextToText.from_pretrained(model_id, dtype=torch.bfloat16, device_map="cuda")
    processor = AutoProcessor.from_pretrained(model_id)
    prompt = CAPTION_PROMPTS[track]
    pending = []
    for image in iter_images(folder):
        caption_path = image.with_suffix(".txt")
        if caption_path.is_file() and caption_path.read_text(encoding="utf-8").strip():
            continue
        pending.append(image)
    print(f"{len(pending)} images need a caption")
    for image_path in pending:
        picture = Image.open(image_path).convert("RGB")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": picture},
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        inputs = processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        )
        inputs = inputs.to(model.device)
        generated = model.generate(**inputs, max_new_tokens=192)
        trimmed = [out[len(inp) :] for inp, out in zip(inputs.input_ids, generated)]
        text = processor.batch_decode(trimmed, skip_special_tokens=True)[0].strip()
        if "</think>" in text:
            text = text.split("</think>")[-1].strip()
        image_path.with_suffix(".txt").write_text(text + "\n", encoding="utf-8")
        print(image_path.name)
    return 0


if __name__ == "__main__":
    main()
