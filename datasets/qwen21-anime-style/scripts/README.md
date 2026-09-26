# Fetch scripts

Public metadata only. No API keys, cookies, or refresh tokens. Cache is `scripts/.cache/` and is gitignored.

```bash
cd datasets/qwen21-anime-style/scripts
python3 -m unittest test_safety.py
python3 fetch_civitai.py          # catalog/_civitai_candidates.jsonl
python3 fetch_pixiv.py            # catalog/_pixiv_candidates.jsonl
python3 build_catalog.py          # catalog/style_candidates.csv and .jsonl
python3 contact_sheet.py --jsonl ../catalog/style_candidates.jsonl --outdir /tmp/qwen21-review
```

`fetch_*.py --refresh` ignores the cache. `build_catalog.py --allowlist ids.txt` keeps only reviewed ids and marks `visual_review=thumbnail_pass`.

Scratch `catalog/_*.jsonl` files are gitignored. Replace `style_candidates.*` only after a visual pass.

## Civitai

`fetch_civitai.py` uses `https://civitai.com/api/v1` (models, then model-version showcases, which include prompts and the `minor` / `poi` flags). Requests sleep about 0.45s and back off on HTTP 429. Image files are not downloaded.

## Pixiv

`fetch_pixiv.py` uses the public illustration search and `https://www.pixiv.net/ajax/illust/{id}` for safe-mode works. It also reads the monthly illustration ranking and keeps original works.

**R-18 is a stub.** A probe of `mode=r18` returned works with `xRestrict=0` only. Restricted metadata needs the viewer’s own login. Do not paste a cookie or `PIXIV_REFRESH_TOKEN` into the repo. When a local session exists, filter title, tags, and description with `safety.py` before any id is written into `catalog/nsfw_anatomy_scaffold.csv`.

## Safety screen

`safety.py` is the shared denylist (ages under 21, loli/shota, school, child-coded series, chibi, photoreal, furry). `test_safety.py` locks the examples. Passing the screen is not a visual approval.
