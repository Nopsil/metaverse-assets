# Report — anime style catalog

Collected 2026-09-26. No training. No image binaries in git. No cookies.

## Snapshot

| | Count |
| --- | --- |
| Catalog URLs | **117** |
| `thumbnail_pass` (thumb only, not original) | 116 |
| `pending` (metadata screen, no thumb pass) | 1 |
| Pixiv (all-ages pages) | 49 |
| Civitai | 68 |
| `all-ages` | 72 |
| `adult` | 45 |
| Pixiv marked human (`ai_generated=no`) | 16 |
| Pixiv unlabeled (`unknown`, older posts) | 33 |
| Civitai AI showcases | 67 |
| Distinct Pixiv artists | 40 |
| Distinct Civitai models | 27 |
| Short-edge minimum | 832 |

Page URLs are the artwork or image page, not a CDN file. The committed snapshot has no image bytes. `visual_review=thumbnail_pass` means a cloud thumbnail look, not an `img-original` review. Full-size files are downloaded on Windows into gitignored `catalog/_originals/`.

Bases in the Civitai slice: Illustrious 47, NoobAI 11, SDXL 1.0 (Animagine-family) 6, Anima 4. Pixiv rows have no checkpoint base. Twenty-eight Civitai adult rows were thumbnail-passed earlier (`collected_via=civitai_public_api`). One more Illustrious adult showcase (`127746621`, Hyphoria) is in the catalog as `pending` only. It was not thumb-reviewed and is not an original download.

A home PC merge added 13 Pixiv rows locally (129 URLs) and those commits were not on this branch. Pull, then re-run `merge_exports.py` from `catalog/_pixiv_windows_export.jsonl` so those 13 stay. This commit does not invent them.

## How they were chosen

1. **Civitai public API** (`/api/v1/models`, `/api/v1/model-versions/{id}`), no token. Anime checkpoints and style LoRAs after skipping realism, furry, pony, and yiff. The age screen drops `minor=true`, school uniforms, stated ages under 21, and child-coded series. A second pass on 2026-09-26 read a second model version per checkpoint and preferred adult showcases. Escaped booru tags (`name_\(series\)`) are normalized before the screen. Thumbnail review then removed a feet-only crop whose age could not be read, a Shantae image, and an explicit frame whose figures read as youthful. Those URLs are not in the catalog.
2. **Pixiv public ajax + monthly ranking**, no login. Safe-mode illustrations only. AI-labeled works and non-original ranking fanart were skipped. R-18 mode returned hits and **0** with `xRestrict > 0`. See `catalog/pixiv_r18_probe.json`.
3. The first thumbnail pass (88 rows) is unchanged. This pass appended 28 adult Civitai rows that survived the screen and a contact-sheet review.

## Pixiv R-18 originals are a home-machine job

Grok Bot's remote box cannot use Pixiv: the IP is a US datacenter address, and Pixiv blocks those. A Cursor cloud agent also does not have your home IP or your logged-in Chrome. Public `mode=r18` does not return restricted works. This pass did not download any Pixiv originals.

Chrome Default cannot be copied. Its cookies use app-bound encryption (ABE v20), and a copy does not stay logged in. Use the dedicated profile that already works, `C:\Users\nopsi\temp\pixiv-collector-chrome`, and the local proxy `http://127.0.0.1:7890`.

On your Windows PC, from `datasets/qwen21-anime-style/scripts`:

```bat
py -3 collect_pixiv_windows.py --login --dedicated-profile C:\Users\nopsi\temp\pixiv-collector-chrome --proxy http://127.0.0.1:7890
py -3 collect_pixiv_windows.py --mode both --limit 60 --dedicated-profile C:\Users\nopsi\temp\pixiv-collector-chrome --proxy http://127.0.0.1:7890
py -3 download_pixiv_originals.py --catalog ../catalog/style_candidates.jsonl --dedicated-profile C:\Users\nopsi\temp\pixiv-collector-chrome --proxy http://127.0.0.1:7890
```

1. `--login` opens that profile. Log in, open one R-18 page, press Enter. The profile stays on disk and is not committed.
2. The collector writes gitignored `catalog/_pixiv_windows_export.jsonl` (page URLs only).
3. The downloader saves `img-original` files under gitignored `catalog/_originals/`. It skips ugoira and keeps the first 3 stills of a multi-page work. It refuses `master1200` and `square1200`.
4. Or paste bookmark URLs into gitignored `catalog/pixiv_urls.txt`. See `scripts/collect_pixiv_windows.md`.
5. Preview a merge, then apply:

```bash
python3 merge_exports.py --import ../catalog/_pixiv_windows_export.jsonl --import ../catalog/pixiv_urls.txt
python3 merge_exports.py --import ../catalog/_pixiv_windows_export.jsonl --import ../catalog/pixiv_urls.txt --apply
```

Dedupe is by source and numeric id. An existing `thumbnail_pass` row is kept if you import that id again. The screen drops school, age under 21, and child-coded series. It does not drop a clearly adult character for a cute style, and it does not keep a child-coded character who is drawn looking older. A URL with no title and no tags stays `unreviewed` until you open the original.

## Next human steps

1. Pull this branch on the home PC. Re-merge the local 13 Pixiv URLs if they are only in `catalog/_pixiv_windows_export.jsonl`.
2. Run the three commands above. Review `catalog/_originals/` at full size. Delete a row when the series, character, or setting is child-coded. Do not commit the image files or the Chrome profile.
3. Prefer human Pixiv drawings when a Civitai showcase and a Pixiv piece teach the same costume.
4. Write `.txt` captions from `captions/README.md`. Do not train on booru tags alone.
5. Anatomy (track B) is still an empty scaffold. Sort true join close-ups into `catalog/nsfw_anatomy_scaffold.csv` only after the same age screen and a full-size look.
6. Only then, on official Qwen Image 2.1, train style (A) and anatomy (B) as two LoRAs. Character LoRA (C) waits.

## Not done

- No training, no GPU job, no weights.
- No NSFW anatomy URLs.
- No Pixiv R-18 originals in git. The cloud environment did not download them.
- No claim that a thumbnail pass is a full-size review.

