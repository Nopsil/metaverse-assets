# Train-unready snapshot (poor aesthetic)

Moved out of the active catalog on 2026-09-27.

`style_candidates.jsonl` and `style_candidates.csv` in this folder are the earlier candidate table (bookmark export plus date-sorted search, plus the Civitai rows that shipped with it). Each row is `status=deprecated` and `visual_review=quarantine`. The matching full-size files, when present on this machine, are in `_originals/` next to this note. Those image files are gitignored. Leftover originals from later rejected downloads are under `catalog/quarantine/pre-hot-rerank/`.

Do not stage this folder. `train/scripts/stage_dataset.py` refuses `catalog/quarantine/` and the old `catalog/_originals` path. The active training originals are `catalog/_originals_hot/` after a popularity-ranked collect and a full-size review.

This copy is for audit only.
