# Style selection criteria

Track A is a **broad 二次元 style** LoRA: line, color, face construction, and costume rendering. Mouth shape and expression are one axis inside that style, not a separate mouth-only set.

The catalog is a candidate pool for later training on **official Qwen Image 2.1**. It is not the final training folder.

## What to keep

- 2D anime or illustration rendering: cel paint, thick digital paint, clean lineart, flat or limited color.
- A clearly adult character, or an all-ages illustration whose character reads as an adult.
- Long edge at least 1024 and short edge at least 768.
- Mix of framing (portrait, half-body, full-body) and costume (fantasy, wafuku, military, casual, witch, knight).
- Original characters preferred. Named adults are allowed when the design is unmistakably adult and the row is not a dump of one face.
- Adult body diversity. Keep petite, slim, and flat-chested characters when the setting is adult. Do not fill the pool with only tall, mature, or voluptuous figures. A petite adult is not a minor.
- The previous `style_candidates` snapshot and its `_originals` files are train-unready. The table is `catalog/quarantine/poor-aesthetic-20260927/` with `status=deprecated`. Leftover originals are `catalog/quarantine/pre-hot-rerank/`. `stage_dataset.py` refuses both. They are not merged back into the active list.
- New Pixiv picks use membership popularity order (`order=popular_d`) and a high bookmark floor. April–October 2026 was only an example span. The collector widens through 7, 30, 90, 180, and 365 days until each adult body bucket has a deep pool. Slim, petite, and flat rows also need an adult-setting tag. Child-coded popular pages are not used to fill a thin bucket.
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

## How age is judged

Do not mark someone a minor from body proportions, a large-eyed face, or a cute costume by themselves. Use the series, the named character, and the setting the artist states. There is no blanket override that treats a child-coded or underage-coded fictional character as an adult.

- A child-coded or school-coded character is out even when the drawing looks grown.
- A clearly adult character (canonical adult, お姉さん, 人妻, 熟女, stated age 21 or older) stays in the pool when the only issue is a cute style. 貧乳, スレンダー, 細身, and 華奢 stay too. つるぺた still drops: it is the child-coded undeveloped tag, not an adult petite build.
- When the series and the author are silent and the picture is still unclear at full size, delete the row.

## Rating

| `rating` | Meaning |
| --- | --- |
| `all-ages` | Safe or PG-13 source, no explicit sexual prompt, adult-looking character. |
| `adult` | Civitai R/X/XXX, or an explicit sexual prompt, after the same age screen. |

Suggestive costume on a Pixiv safe-mode page stays `all-ages`.

## Diversity caps

The builder keeps at most a few images per Pixiv artist and per Civitai model so one creator does not become the style. The cloud snapshot is 117 URLs (49 Pixiv, 68 Civitai; 72 all-ages, 45 adult). 116 of those had a thumbnail pass. One newer Civitai adult URL is `visual_review=pending` (metadata screen only).

Home-exported Pixiv URLs are merged with `scripts/merge_exports.py`. The same artwork id is one row. A `thumbnail_pass` row is not replaced by a later paste of that id. URL-only pastes stay `rating=unreviewed` and `visual_review=pending` until someone opens the full image. See `scripts/collect_pixiv_windows.md`.

## Human review

1. Metadata screen (`scripts/safety.py`): series, character, school, stated age.
2. Thumbnail pass on the committed cloud snapshot (`visual_review=thumbnail_pass`). That pass saw thumbs only, not `img-original`.
3. On Windows, download originals with `scripts/download_pixiv_originals.py`, then review those files. Delete the row if the series, character, or setting is child-coded. Do not delete a clearly adult character for cute proportions.

## Not this catalog

- NSFW anatomy close-ups (track B) live in the scaffold, not in `style_candidates.*`.
- Character identity (track C) is later, and is not mixed into this style set.
- No training run, no image binaries, no secrets.
