# Fetch scripts

Public metadata only. No API keys, cookies, or refresh tokens in git. Cache is `scripts/.cache/` and is gitignored.

```bash
cd datasets/qwen21-anime-style/scripts
python3 -m unittest test_safety.py test_home_collect.py
python3 fetch_civitai.py          # catalog/_civitai_candidates.jsonl and civitai_adult_pending.*
python3 fetch_pixiv.py            # catalog/_pixiv_candidates.jsonl  (safe-mode only)
python3 build_catalog.py          # catalog/style_candidates.csv and .jsonl
python3 contact_sheet.py --jsonl ../catalog/style_candidates.jsonl --outdir /tmp/qwen21-review
```

`fetch_*.py --refresh` ignores the cache. `build_catalog.py --allowlist ids.txt` keeps only reviewed ids and marks `visual_review=thumbnail_pass`.

Scratch `catalog/_*.jsonl` files and `catalog/civitai_adult_pending.*` are gitignored. Replace `style_candidates.*` only after a visual pass.

## Civitai

`fetch_civitai.py` uses `https://civitai.com/api/v1` (models, then up to two model-versions, which include prompts and the `minor` / `poi` flags). Adult showcases are kept ahead of all-ages ones, still through `safety.py`. Requests sleep about 0.45s and back off on HTTP 429. Image files are not downloaded.

The run also writes `catalog/civitai_adult_pending.csv` for adult rows that are not already in `style_candidates`. That file is scratch. The 2026-09-26 snapshot already folded the thumbnail-passed adult additions into `style_candidates`.

## Pixiv from this repo

`fetch_pixiv.py` uses the public illustration search and `https://www.pixiv.net/ajax/illust/{id}` for safe-mode works. It also reads the monthly illustration ranking and keeps original works.

**Do not collect R-18 here, and do not download Pixiv originals here.** A probe of `mode=r18` returned works with `xRestrict=0` only. Pixiv blocks many US datacenter IPs. Do not paste a cookie or `PIXIV_REFRESH_TOKEN` into the repo. Do not copy Chrome Default; ABE v20 cookies do not stay logged in.

## Pixiv on your Windows PC

`collect_pixiv_windows.py` and `download_pixiv_originals.py` use a dedicated Playwright profile and `--proxy`. `--login` is once. The collector writes page URLs. The downloader saves `img-original` files under gitignored `catalog/_originals/`, skips ugoira, and keeps the first 3 stills of a multi-page work. The run order is `collect_pixiv_windows.md`.

```bat
py -3 collect_pixiv_windows.py --login --dedicated-profile C:\Users\nopsi\temp\pixiv-collector-chrome --proxy http://127.0.0.1:7890
py -3 collect_pixiv_windows.py --mode both --limit 60 --dedicated-profile C:\Users\nopsi\temp\pixiv-collector-chrome --proxy http://127.0.0.1:7890
py -3 download_pixiv_originals.py --catalog ../catalog/style_candidates.jsonl --dedicated-profile C:\Users\nopsi\temp\pixiv-collector-chrome --proxy http://127.0.0.1:7890
```

`--self-check` only validates the adult search words. On Linux or macOS both scripts exit without opening a browser.

## Merge and dedupe

```bash
python3 merge_exports.py \
  --import ../catalog/_pixiv_windows_export.jsonl \
  --import ../catalog/pixiv_urls.txt \
  --import ../catalog/civitai_adult_pending.jsonl
```

That writes gitignored `catalog/_merged_preview.jsonl` and prints added, dropped, and duplicate counts. It does not change `style_candidates` until you pass `--apply`. A row with `visual_review=thumbnail_pass` wins over a later import of the same id. Details are in `collect_pixiv_windows.md`.

## Safety screen

`safety.py` is the shared denylist (ages under 21, loli/shota, school, child-coded series, chibi, photoreal, furry, 3D). A cute face or stylized body is not a drop by itself. Petite, slim, and flat-chested adults stay. つるぺた still drops. Child-coded characters stay out even when drawn looking older. Backslashes in booru tags are stripped before matching, so `suomi_\(girls'_frontline\)` still drops. `test_safety.py` and `test_home_collect.py` lock the examples. Passing the screen is not a visual approval.

## After the files are on disk

Caption and training are `../train/README.md`. `train/scripts/stage_dataset.py` copies full-size images into gitignored `train/data/`. `caption_originals.py` and `run_train.py` do not start a cloud instance. `run_train.py` without `--check` is the H100 training command, and it exits if no GPU is visible.
