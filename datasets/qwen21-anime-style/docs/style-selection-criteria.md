# Style selection criteria

Track A is a **broad 二次元 style** LoRA: line, color, face construction, and costume rendering. Mouth shape and expression are one axis inside that style, not a separate mouth-only set.

The catalog is a candidate pool for later training on **official Qwen Image 2.1**. It is not the final training folder.

## What to keep

- 2D anime or illustration rendering: cel paint, thick digital paint, clean lineart, flat or limited color.
- A clearly adult character, or an all-ages illustration whose character reads as an adult.
- Long edge at least 1024 and short edge at least 768.
- Mix of framing (portrait, half-body, full-body) and costume (fantasy, wafuku, military, casual, witch, knight).
- Original characters preferred. Named adults are allowed when the design is unmistakably adult and the row is not a dump of one face.
- Pixiv: human or unlabeled illustrations. AI-labeled Pixiv works (`aiType == 2`) are skipped so the style target is not only model output. Civitai showcases are AI generations and are marked `ai_generated=yes`.

## What to drop

Hard drop, even if the picture is otherwise pretty:

- Any minor, underage, or ambiguous-age character. Stated age under 21. “Legal loli,” ロリババア, mesugaki, っ子.
- School cues: uniforms, serafuku, gym clothes, high-school / middle-school / elementary tags, JK/JS/JC.
- Child-coded or school-coded series and characters, including Vocaloid/Miku, Blue Archive, Precure, Touhou, Love Live, Jujutsu Kaisen, My Hero Academia, Evangelion, Madoka, Cardcaptor Sakura, Frieren, Genshin child designs, Violet Evergarden, Amiya, Tohsaka Rin, Umamusume, Kemono Friends, Medalist, Chainsaw Man, Konosuba, The Quintessential Quintuplets, Doki Doki Literature Club, Animal Crossing, and Shantae.
- Chibi, super-deformed, and Q-version proportions.
- Photoreal, DSLR, “ultra realistic,” furry, and My Little Pony / Pony Diffusion.
- 3D character renders (`3d style`, `3d render`, `3dcg`). They pull the style off 2D anime.
- Gore.
- Comics and tutorials (multi-panel pages, 講座).
- Civitai `minor` or `poi` flags. Pixiv `lo` flag.
- Empty prompts on Civitai (no tags to screen).

`美少女` is not an automatic drop. On Pixiv it is often used for adult women. Those rows still need a visual check. The exact tag `少女` is dropped.

`1girl` is a count tag, not an age tag.

## Rating

| `rating` | Meaning |
| --- | --- |
| `all-ages` | Safe or PG-13 source, no explicit sexual prompt, adult-looking character. |
| `adult` | Civitai R/X/XXX, or an explicit sexual prompt, after the same age screen. |

Suggestive costume on a Pixiv safe-mode page stays `all-ages`.

## Diversity caps

The builder keeps at most a few images per Pixiv artist and per Civitai model so one creator does not become the style. The reviewed snapshot is 116 rows (49 Pixiv, 67 Civitai; 72 all-ages, 44 adult).

Home-exported Pixiv URLs are merged with `scripts/merge_exports.py`. The same artwork id is one row. A `thumbnail_pass` row is not replaced by a later paste of that id. URL-only pastes stay `rating=unreviewed` and `visual_review=pending` until someone opens the full image. See `scripts/collect_pixiv_windows.md`.

## Human review

1. Metadata screen (`scripts/safety.py`).
2. Thumbnail pass (done for the committed snapshot; `visual_review=thumbnail_pass`).
3. Full-size pass before any download. Thumbnails miss small cues. If age is still unclear, delete the row.

## Not this catalog

- NSFW anatomy close-ups (track B) live in the scaffold, not in `style_candidates.*`.
- Character identity (track C) is later, and is not mixed into this style set.
- No training run, no image binaries, no secrets.
