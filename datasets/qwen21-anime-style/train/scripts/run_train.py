"""Train one Qwen Image 2.1 LoRA on the current machine.

--check only looks at images and captions. It does not touch the GPU.

Without --check, this starts AI-Toolkit on the GPU that is already
visible (the OneThing H100, after you have started that instance
yourself). It does not call a cloud API.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from common import DATA_DIR, SHUTDOWN_NOTE, dataset_problems
from render_configs import render


def check(track: str, folder: Path | None = None) -> int:
    folder = folder or (DATA_DIR / track)
    errors, warnings = dataset_problems(folder, track)
    for line in warnings:
        print("warning:", line, file=sys.stderr)
    if errors:
        print(f"{track}: {len(errors)} problem(s)", file=sys.stderr)
        for line in errors[:40]:
            print(line, file=sys.stderr)
        return 2
    print(f"{track}: captions ok in {folder} ({len(list(folder.glob('*.txt')))} txt files)")
    return 0


def launch(track: str) -> int:
    code = check(track)
    if code != 0:
        return code
    toolkit = os.environ.get("AI_TOOLKIT_ROOT", "").strip()
    run_py = Path(toolkit) / "run.py" if toolkit else None
    if run_py is None or not run_py.is_file():
        print(
            "Set AI_TOOLKIT_ROOT to a clone of https://github.com/ostris/ai-toolkit "
            "on current main (arch qwen_image_2). Training was not started.",
            file=sys.stderr,
        )
        return 2
    if shutil.which("nvidia-smi") is None:
        print("nvidia-smi is not on this machine. Training was not started.", file=sys.stderr)
        return 2
    probe = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True)
    if probe.returncode != 0:
        print(probe.stderr or probe.stdout, file=sys.stderr)
        print("No GPU visible. Training was not started.", file=sys.stderr)
        return 2
    yaml_path = render(track, "train")
    cmd = [sys.executable, str(run_py), str(yaml_path)]
    print("Running:", " ".join(cmd))
    print("HF tokens stay in the shell environment. Do not write them into this repo.")
    try:
        return subprocess.call(cmd, cwd=toolkit)
    finally:
        print(SHUTDOWN_NOTE)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("track", choices=("style", "anatomy", "both"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    tracks = ["style", "anatomy"] if args.track == "both" else [args.track]
    exit_code = 0
    for track in tracks:
        if args.check:
            exit_code = check(track) or exit_code
        else:
            code = launch(track)
            if code != 0:
                raise SystemExit(code)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
