# Qwen Image 2.1 anime-style dataset catalog

Candidate pool for a **broad anime-style LoRA** (training track A) on the official Qwen Image 2.1 base. This folder is a catalog and fetch toolkit. It does not contain training images, captions for the rows, or checkpoints.

Nothing here trains a model. Other files in the assets repo are untouched.

## Safety

Zero minors. Rows must be clearly adult characters, or clean all-ages illustrations of adult-looking characters. School uniforms, child-coded series, stated ages under 21, chibi, and ambiguous age are out. If a picture is unclear, it does not belong in the set.

Metadata filters are not enough. 116 committed URLs had a thumbnail review on 2026-09-26. One later Civitai URL is metadata-only (`visual_review=pending`). **Every URL still needs a full-size look of the original file before training.** Thumbnail review did not see `img-original`.

## Layout

| Path | Role |
| --- | --- |
| `catalog/style_candidates.csv` | Style candidates (117 URLs: 116 thumbnail_pass, 1 pending). |
| `catalog/style_candidates.jsonl` | Same rows, plus fields used by the scripts. |
| `catalog/nsfw_anatomy_scaffold.csv` | Header only. Anatomy set is not populated. |
| `catalog/pixiv_r18_probe.json` | Public R-18 search does not return restricted works. |
| `catalog/pixiv_url_paste.example.txt` | Empty example for a home-exported URL list. |
| `docs/style-selection-criteria.md` | What “anime style” means here, and what is excluded. |
| `docs/nsfw-anatomy-scaffold.md` | Separate adult-anatomy track (B). No image URLs. |
| `captions/README.md` | Natural-language captions for Qwen Image 2.1. |
| `scripts/` | Civitai public API fetch, Pixiv public fetch, Windows home collector, merge. |
| `PLAN_REVISION.md` | Track A is broad style, not mouth-only. |
| `REPORT.md` | Counts and the next human review pass. |

`url` is the stable page (`https://civitai.com/images/{id}` or `https://www.pixiv.net/artworks/{id}`). Image bytes are not stored in git.

## Rating

`rating` is `all-ages` or `adult`.

- Pixiv rows in this snapshot are safe-mode illustrations (`all-ages`). R-18 needs a personal login on a home connection. See below and `scripts/collect_pixiv_windows.md`.
- Civitai `adult` rows are showcase images whose site rating is R or higher, or whose prompt is sexually explicit, and that still passed the age screen and thumbnail review.

## Pixiv: collect at home, not from a US cloud box

Pixiv blocks many US datacenter IPs. The remote box used for this catalog cannot finish an R-18 collection, and a Cursor cloud agent usually does not have your home IP or your logged-in Chrome either. Public `mode=r18` search, when it answers, returns safe-mode works only (`catalog/pixiv_r18_probe.json`).

Practical path:

1. Keep using the public catalog scripts here for Civitai, and for safe-mode Pixiv when that network answers.
2. On your Windows PC, log in once in a **dedicated** Chrome profile (not a copy of Chrome Default; those cookies do not transfer). Then run `scripts/collect_pixiv_windows.py` with `--dedicated-profile` and `--proxy`.
3. Download full-size `img-original` files with `scripts/download_pixiv_originals.py` into gitignored `catalog/_originals/`. The catalog rows themselves stay page URLs. Thumbs (`square1200`, `master1200`) are not the training files.
4. Or copy bookmark URLs into `catalog/pixiv_urls.txt` (gitignored) and merge them with `scripts/merge_exports.py`.

`scripts/collect_pixiv_windows.md` is the run order: log in, collect URLs, download originals, then dedupe.

## Rebuild

From `scripts/`:

```bash
python3 -m unittest test_safety.py test_home_collect.py
python3 fetch_civitai.py
python3 fetch_pixiv.py
python3 build_catalog.py
```

A fresh fetch changes the candidate pool. Do not replace `style_candidates.*` until the new rows have been reviewed. `fetch_civitai.py` also writes `catalog/civitai_adult_pending.*` (gitignored) for adult showcases that are not already in the reviewed catalog. The scripts cache JSON under `scripts/.cache/` (gitignored) and do not take API keys.
