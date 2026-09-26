# Train-unready originals from before the hot rerank

These image folders are an audit copy. They are not a training source.

- `_originals_apr_oct/` is the April–October popularity download that was replaced when the date span was widened.
- `_originals_hold/` holds files that missed the bookmark floor.

The candidate table for the older bookmark and date-sorted batch is `catalog/quarantine/poor-aesthetic-20260927/`. Every row there has `status=deprecated` and `visual_review=quarantine`. Do not merge that table back into `catalog/style_candidates.*`.

`train/scripts/stage_dataset.py` refuses this folder. The only style originals it will copy are `catalog/_originals_hot/` after a full-size review.
