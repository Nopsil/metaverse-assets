# Qwen Image 2.1 anime-style dataset catalog

Candidate pool for a **broad anime-style LoRA** (training track A) on the official Qwen Image 2.1 base. This folder is a catalog and fetch toolkit. It does not contain training images, captions for the rows, or checkpoints.

Nothing here trains a model. Other files in the assets repo are untouched.

## Safety

Zero minors. Rows must be clearly adult characters, or clean all-ages illustrations of adult-looking characters. School uniforms, child-coded series, stated ages under 21, chibi, and ambiguous age are out. If a picture is unclear, it does not belong in the set.

Metadata filters are not enough. Every kept URL had a thumbnail review on 2026-09-26, and **every URL still needs a full-size human look before download or training**.

## Layout

| Path | Role |
| --- | --- |
| `catalog/style_candidates.csv` | Reviewed style candidates (88 rows). |
| `catalog/style_candidates.jsonl` | Same rows, plus fields used by the scripts. |
| `catalog/nsfw_anatomy_scaffold.csv` | Header only. Anatomy set is not populated. |
| `catalog/pixiv_r18_probe.json` | Public R-18 search does not return restricted works. |
| `docs/style-selection-criteria.md` | What “anime style” means here, and what is excluded. |
| `docs/nsfw-anatomy-scaffold.md` | Separate adult-anatomy track (B). No image URLs. |
| `captions/README.md` | Natural-language captions for Qwen Image 2.1. |
| `scripts/` | Civitai public API fetch, Pixiv public fetch, safety screen. |
| `PLAN_REVISION.md` | Track A is broad style, not mouth-only. |
| `REPORT.md` | Counts and the next human review pass. |

`url` is the stable page (`https://civitai.com/images/{id}` or `https://www.pixiv.net/artworks/{id}`). Image bytes are not stored in git.

## Rating

`rating` is `all-ages` or `adult`.

- Pixiv rows in this snapshot are safe-mode illustrations (`all-ages`). R-18 needs a personal login; see `scripts/README.md`.
- Civitai `adult` rows are showcase images whose site rating is R or higher, or whose prompt is sexually explicit, and that still passed the age screen and thumbnail review.

## Rebuild

From `scripts/`:

```bash
python3 -m unittest test_safety.py
python3 fetch_civitai.py
python3 fetch_pixiv.py
python3 build_catalog.py
```

A fresh fetch changes the candidate pool. Do not replace `style_candidates.*` until the new rows have been reviewed. The scripts cache JSON under `scripts/.cache/` (gitignored) and do not take API keys.
