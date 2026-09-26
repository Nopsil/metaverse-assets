# Report — anime style catalog

Collected 2026-09-26. No training. No image binaries in git.

## Snapshot

| | Count |
| --- | --- |
| Reviewed style URLs | **88** |
| Pixiv (all-ages pages) | 49 |
| Civitai | 39 |
| `all-ages` | 72 |
| `adult` | 16 |
| Pixiv marked human (`ai_generated=no`) | 16 |
| Pixiv unlabeled (`unknown`, older posts) | 33 |
| Civitai AI showcases | 39 |
| Distinct Pixiv artists | 40 |
| Distinct Civitai models | 23 |
| Short-edge minimum / median | 832 / 1536 |

Page URLs were checked for a sample of Pixiv and Civitai rows (HTTP 200). `url` is the artwork or image page, not a CDN file.

Bases in the Civitai slice: Illustrious 24, NoobAI 8, SDXL 1.0 (Animagine-family) 6, Anima 1. Pixiv rows have no checkpoint base.

## How the 88 were chosen

1. **Civitai public API** (`/api/v1/models`, `/api/v1/model-versions/{id}`), no token, cached and delayed. 50 anime checkpoints/LoRAs after skipping realism, furry, and pony. Showcase images with prompts: **147** passed the age screen (123 all-ages, 24 adult). The screen dropped Civitai `minor=true` (7), Miku/Vocaloid, Blue Archive, school uniforms, Frieren, chibi, photoreal, and similar.
2. **Pixiv public ajax + monthly ranking**, no login. 645 stubs, **163** safe-mode illustrations passed the screen. AI-labeled works (276) and non-original ranking fanart were skipped. R-18 mode returned 60 hits and **0** with `xRestrict > 0` (login wall). See `catalog/pixiv_r18_probe.json`.
3. Builder caps produced 116 mixed rows (21 adult, 95 all-ages).
4. **Thumbnail review** removed 28 of those 116: childlike proportions, school or canonically underage characters, a comic page, a 3D render, and previews that failed to download (age could not be checked). Those URLs are not listed here.

`visual_review` on the committed rows is `thumbnail_pass` only.

## Next human steps

1. Open all 88 pages at full size. Delete any row that looks underage, school-aged, chibi, or simply unclear. Thumbnail review is not the last gate.
2. Prefer human Pixiv drawings when a Civitai showcase and a Pixiv piece teach the same costume. Keep some Civitai rows if you want the style to survive AI-ish linework.
3. Do not commit the image files. Download locally, outside git, after the full-size pass.
4. Write `.txt` captions from `captions/README.md`. Do not train on booru tags alone.
5. Pixiv R-18 and the anatomy scaffold are still empty. A logged-in session can collect **adult** anatomy later; run `scripts/safety.py` and a full-size review before adding URLs. Do not put cookies in this repo.
6. Only then, on official Qwen Image 2.1, train style (A) and anatomy (B) as two LoRAs. Character LoRA (C) waits.

## Not done

- No training, no GPU job, no weights.
- No NSFW anatomy URLs.
- No claim that every thumbnail-passed face will survive a full-size review.
