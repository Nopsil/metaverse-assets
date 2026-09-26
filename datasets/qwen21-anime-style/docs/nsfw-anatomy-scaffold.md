# NSFW anatomy scaffold (track B)

Separate from the style catalog. Do not merge these images into track A.

This scaffold has **no image URLs**. Pixiv R-18 search from a US datacenter does not return restricted works (`catalog/pixiv_r18_probe.json`). Pixiv also blocks many of those IPs outright. Collect R-18 on a home Windows Chrome profile (`scripts/collect_pixiv_windows.md`), then screen and review before any URL is added here. Civitai adult showcases that passed review were kept on the **style** list when they were full illustrations of adult characters, not genital close-ups.

## Purpose

Teach clean adult anatomy that official Qwen Image 2.1 currently misses: join, limb separation, nipple count, fluids. Train it as its own LoRA on the official 2.1 weights. Do not fold it into the style LoRA.

## Who may be depicted

Only characters who are unmistakably adults. The same denylist as `scripts/safety.py` applies, plus a full-size review of every file. Ambiguous age is a drop, including “adult” tags on a childlike body.

Out: minors, school settings, gore, and a pile of lookalike faces (that is track C).

## Pose buckets to fill later

Align with existing pose references when a human collects files:

- reverse cowgirl, cowgirl, doggy, missionary, mating press, spooning, wall with one leg
- clear vaginal join, including three-quarter rear views
- fluids at more than one intensity (not one pasted white texture)
- correct anatomy: two nipples, separable limbs, an erect inserted penis rather than a fused or floating one

Anal-focused images stay out of v1 so the concept does not take over.

Suggested size after review: about 150–300 images. Under 80 is too small for this concept. Close-ups can be roughly a third; the rest should keep full or half-body composition.

## Files

`catalog/nsfw_anatomy_scaffold.csv` is a header. Columns:

`source,url,id,title,tags,rating,pose_bucket,style_notes,keep_reason,safety_status`

`rating` must be `adult`. `safety_status` stays `unreviewed` until a person has opened the full image. `pose_bucket` is one of the names above.

## How to add rows later

1. Do not commit cookies, refresh tokens, or API keys. Do not collect Pixiv from a US cloud VM.
2. Fetch with the public Civitai client, or run `scripts/collect_pixiv_windows.py` on your own PC, or paste URLs and run `scripts/merge_exports.py`.
3. Run `scripts/safety.py` on title, tags, and prompt.
4. Review full size. Drop anything youthful.
5. Append CSV/JSONL rows. Keep binaries out of git.
6. Caption using `captions/README.md`, with anatomy words and without a character name.
