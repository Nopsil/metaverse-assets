# Failed full-size review

These artwork ids were in the popularity candidate list and failed a full-size look. They are not training candidates. Do not merge them back into `catalog/style_candidates.*`.

`rejected.jsonl` is the skip list. The collector and `merge_exports.py` both read it. Image files, when present on this machine, are under `_originals/` and are gitignored. `stage_dataset.py` refuses this folder.

| id | note |
| --- | --- |
| `142269340` | Failed review. Dropped from the active catalog. |
