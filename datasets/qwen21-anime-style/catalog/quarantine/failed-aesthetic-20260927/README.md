# User-rejected hot catalog (2026-09-27)

The active `catalog/style_candidates.jsonl` (62 Pixiv rows) was moved here after review. The user rejected it as low finish, cluttered, and comic-like next to the gold-reference plates.

Those plates stay where they are. This folder does not replace `catalog/_gold_refs_notes.md` or `catalog/_originals_hot/gold_refs/`.

Counts before the move: average 23, flat 22, curvy 16, slim 1, petite 0. Every row was `visual_review=pending`. Rows in this copy are `status=deprecated`, `visual_review=quarantine`, and `pool=quarantine`. Do not merge them back into the active list.

`train/scripts/stage_dataset.py` already refuses `catalog/quarantine/`.
