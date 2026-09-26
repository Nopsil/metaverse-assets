# Report — anime style catalog

Collected 2026-09-26. No training. No image binaries in git. No cookies.

## Snapshot

| | Count |
| --- | --- |
| Reviewed style URLs | **116** |
| Pixiv (all-ages pages) | 49 |
| Civitai | 67 |
| `all-ages` | 72 |
| `adult` | 44 |
| Pixiv marked human (`ai_generated=no`) | 16 |
| Pixiv unlabeled (`unknown`, older posts) | 33 |
| Civitai AI showcases | 67 |
| Distinct Pixiv artists | 40 |
| Distinct Civitai models | 27 |
| Short-edge minimum | 832 |

Page URLs are the artwork or image page, not a CDN file. `visual_review` on every committed row is `thumbnail_pass` only. Full-size review is still required.

Bases in the Civitai slice: Illustrious 46, NoobAI 11, SDXL 1.0 (Animagine-family) 6, Anima 4. Pixiv rows have no checkpoint base. The extra 28 Civitai rows are adult showcases added on this pass (`collected_via=civitai_public_api`).

## How they were chosen

1. **Civitai public API** (`/api/v1/models`, `/api/v1/model-versions/{id}`), no token. Anime checkpoints and style LoRAs after skipping realism, furry, pony, and yiff. The age screen drops `minor=true`, school uniforms, stated ages under 21, and child-coded series. A second pass on 2026-09-26 read a second model version per checkpoint and preferred adult showcases. Escaped booru tags (`name_\(series\)`) are normalized before the screen. Thumbnail review then removed a feet-only crop whose age could not be read, a Shantae image, and an explicit frame whose figures read as youthful. Those URLs are not in the catalog.
2. **Pixiv public ajax + monthly ranking**, no login. Safe-mode illustrations only. AI-labeled works and non-original ranking fanart were skipped. R-18 mode returned hits and **0** with `xRestrict > 0`. See `catalog/pixiv_r18_probe.json`.
3. The first thumbnail pass (88 rows) is unchanged. This pass appended 28 adult Civitai rows that survived the screen and a contact-sheet review.

## Pixiv R-18 is a home-machine job

Grok Bot's remote box cannot use Pixiv: the IP is a US datacenter address, and Pixiv blocks those. A Cursor cloud agent also does not have your home IP or your logged-in Chrome. Public `mode=r18` does not return restricted works.

On your Windows PC:

1. Log into Pixiv in Chrome. Close Chrome.
2. From `datasets/qwen21-anime-style/scripts`, run `py -3 collect_pixiv_windows.py --mode both --limit 60`.
3. The script copies login files to a temp folder (not passwords, not history), scrapes artwork **page URLs**, and deletes the temp copy. Output is gitignored `catalog/_pixiv_windows_export.jsonl`.
4. Or paste bookmark URLs into gitignored `catalog/pixiv_urls.txt`. Format: `scripts/collect_pixiv_windows.md` and `catalog/pixiv_url_paste.example.txt`.
5. Preview a merge, then apply only after you have looked at the preview:

```bash
python3 merge_exports.py --import ../catalog/_pixiv_windows_export.jsonl --import ../catalog/pixiv_urls.txt
python3 merge_exports.py --import ../catalog/_pixiv_windows_export.jsonl --import ../catalog/pixiv_urls.txt --apply
```

Dedupe is by source and numeric id. An existing `thumbnail_pass` row is kept if you import that id again. The screen drops school, age under 21, and child-coded series. A URL with no title and no tags stays `unreviewed` until you open it.

## Next human steps

1. Open all 116 pages at full size. Delete any row that looks underage, school-aged, chibi, or simply unclear. Thumbnail review is not the last gate.
2. Run the Windows collector or paste Pixiv bookmark URLs. Do not commit cookies, the temp Chrome folder, or image files.
3. Merge, then full-size review of every new Pixiv row before it counts as kept.
4. Prefer human Pixiv drawings when a Civitai showcase and a Pixiv piece teach the same costume. Keep some Civitai rows if you want the style to survive AI-ish linework.
5. Write `.txt` captions from `captions/README.md`. Do not train on booru tags alone.
6. Anatomy (track B) is still an empty scaffold. Sort true join close-ups into `catalog/nsfw_anatomy_scaffold.csv` only after the same age screen and a full-size look. R-18 illustrations of adult characters can stay on the style list.
7. Only then, on official Qwen Image 2.1, train style (A) and anatomy (B) as two LoRAs. Character LoRA (C) waits.

## Not done

- No training, no GPU job, no weights.
- No NSFW anatomy URLs.
- No Pixiv R-18 URLs. That collection waits on a home Windows session.
- No claim that every thumbnail-passed face will survive a full-size review.
