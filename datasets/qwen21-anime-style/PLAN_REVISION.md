# Plan revision — 2026-09-26

The parent note split training into a mouth LoRA (A), an NSFW anatomy LoRA (B), and a later character LoRA (C), on official Qwen Image 2.1.

## What changed

**A is a broad anime-style LoRA, not a mouth-only LoRA.** Mouth shape, teeth, and expression stay in the data and in the captions, as part of face and rendering. The set also needs bodies, costumes, and more than one camera distance so the LoRA does not collapse to lip crops.

**B stays a separate anatomy LoRA.** It is scaffolded only (`docs/nsfw-anatomy-scaffold.md`). No anatomy URLs are in the repo yet.

**C stays later.** Do not mix a character identity into A or B. Keep using the existing identity card at inference until A and B are stable.

**Train on official Qwen Image 2.1** (BF16 / Diffusers weights; AI-Toolkit may load INT8 ConvRot). Noct remains an inference comparison, not the training base. Do not start from older Qwen or 2512 LoRAs and expect them to transfer.

## What did not change

- Two LoRAs, not one mixed anime+NSFW file.
- Text encoder frozen for v1.
- Fixed eval seed `26092755` when training eventually runs.
- This revision does not train anything and does not use the GPU.

## Data shape

Style candidates live in `catalog/style_candidates.csv` (117 URLs on this branch: 116 thumbnail-passed, 1 metadata-only pending). After a full-size pass of the downloaded originals, train on a diverse slice of that pool rather than on mouth crops alone. Anatomy still wants its own 150–300 reviewed adults before a B run. Caption rules are in `captions/README.md`.

Pixiv R-18 page URLs and `img-original` files are collected on a home Windows Chrome profile (`scripts/collect_pixiv_windows.md`), not on a US cloud VM. Do not copy Chrome Default. Do not commit cookies or image bytes.
