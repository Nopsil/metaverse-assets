# Captions for Qwen Image 2.1

Write a natural-language English sentence plus a few concrete tags. Do not use a pure booru list, and do not invent a nonsense trigger (`TOK`, `sks`).

Qwen Image 2.1 follows descriptive text. The caption should look like the prompt you will type at inference time.

One `.txt` file per image, same stem. AI-Toolkit reads `caption_ext: txt`. DiffSynth can use a `prompt` column in `metadata.csv`.

## Style LoRA (track A)

Describe what changes from picture to picture: pose, camera, expression, how open the mouth is, costume, light, background.

Let the LoRA absorb the rendering. You can anchor it with a short style phrase such as `anime style, cel shading, clean lineart`. Do not pin a specific character’s face, hair brand, or series name as the thing to learn.

Mouth and teeth are one part of the sentence (`slightly open mouth, stylized lips, no realistic gums`), not the whole caption.

Examples:

```text
Anime illustration of an adult woman in three-quarter view, black armor and a red cloak, wind in her hair, calm expression, closed mouth, cel shading, clean lineart, dusk sky behind her.

Half-body anime portrait of an adult woman in a dark dress, looking at the viewer, small smile, soft rim light, thick painterly color, plain warm background.

Full-body anime illustration of an adult witch in a black gown, standing in profile, one hand raised, neutral mouth, high-contrast cel paint, night interior.
```

## Anatomy LoRA (track B)

Do not name the character. Describe pose and anatomy. Example:

```text
Side view of two adults, woman straddling in reverse cowgirl, clear vaginal penetration, erect penis inserted, two nipples, limbs separate, a little fluid at the join, anime cel shading, simple bedroom background. clean genital join
```

Use the same anchors across the set (`clean genital join` or `qwen_nsfw_join`) and vary the pose words. Do not caption Grok-card identity into A or B.

## Do not write

- Ages, school, or “young girl.”
- A trigger that is only on the mouth crops if this LoRA is the broad style model.
- Artist names, unless you are deliberately studying one living artist’s style and have the right to train on it.
