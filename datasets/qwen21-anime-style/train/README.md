# Train Qwen Image 2.1 LoRAs

Style first, anatomy second, on the official `Qwen/Qwen-Image-2.1` base (`arch: qwen_image_2`). Two configs, two folders, two output files. Nothing in this folder starts a cloud instance or a GPU by itself.

AI-Toolkit main (checked 2026-09-26) has the loader at `extensions_built_in/diffusion_models/qwen_image_2` and no `config/examples` file for it yet. These YAMLs follow `config/examples/train_lora_qwen_image_24gb.yaml` plus that loader. `arch: qwen_image` is the older 20B model. Do not use it. If Ostris later ships a `qwen_image_2` example, use that file's rank and learning rate.

The text encoder stays frozen. Captions are natural English sentences (see `captions/README.md`). There is no trigger word: text embeddings are cached, and a trigger is ignored when they are.

## H100 defaults

| | Style (A) | Anatomy (B) |
| --- | --- | --- |
| Config | `train/configs/style_lora.yaml` | `train/configs/anatomy_lora.yaml` |
| Rank / alpha | 32 / 32 | 16 / 16 |
| Learning rate | `1e-4` | `1e-4` |
| Optimizer | adamw8bit | adamw8bit |
| Steps | 2000 | 2500 |
| Batch | 1 | 1 |
| Grad accum | 2 | 2 |
| Resolution buckets | 1024, 1280, 1536 | same |
| Weights | official Diffusers BF16 | same |
| Sample | 1024, guidance 1.0, seed `26092755` | same |

2000 steps is the middle of the toolkit note (500–4000) on the older Qwen-Image example. Rank 16 there was for the 20B model and for characters. A broad style on the 7B 2.1 DiT starts at 32. Anatomy stays at 16 unless joins stay mushy. Do not raise the learning rate above `1e-4` to go faster. `timestep_type: sigmoid` is the toolkit default. A 12GB writeup used `shift`; try that only if samples look washed out.

`guidance_scale: 1.0` matches the Qwen Image 2.1 pipeline (CFG off). Do not copy guidance 3 from the older Qwen-Image example. Official T2I cards use about 40 inference steps; samples here use 28 so the sheet does not dominate the rental. Set `sample_steps: 40` if the sheet looks under-cooked.

Batch stays 1. Three resolutions share one process. `num_workers: 0` and `cache_latents_num_workers: 2` keep the cache from spawning a pile of workers. `gradient_checkpointing` stays on.

If step 1 runs out of memory, in this order:

1. Keep `batch_size: 1` and `gradient_checkpointing: true`.
2. Remove `1536` from `resolution`.
3. Set `quantize: true`, `qtype: convrot8`, `quantize_te: true`, `qtype_te: convrot8`, and `model_kwargs.use_comfy_weights: true`. The loader can then attach the Comfy-Org int8 ConvRot file instead of quantizing BF16 in memory. That is the toolkit's own low-VRAM path, not a different base model.
4. Set `disable_sampling: true` if the failure is in the sample pass. Decoding above 1 megapixel is tiled; samples are 1024 so they should fit.
5. Leave `layer_offloading` off on an 80GB H100. Offloading is the 12GB path and makes the hour slower.

`use_comfy_weights: false` with `quantize: false` is what loads official Diffusers BF16 from `Qwen/Qwen-Image-2.1`. The text encoder, VAE, and processor come from that repo either way.

## Checklist

Do the Windows steps before you open the OneThing instance. Start the H100 only when `train/data/` is ready to upload. Caption and both trains happen in that same session, then you copy the LoRAs off and shut the instance down.

### 1. Download originals (Windows, no training GPU)

From `datasets/qwen21-anime-style/scripts`. Profile and proxy are the ones already used on the home PC. Details: `scripts/collect_pixiv_windows.md`.

```bat
py -3 collect_pixiv_windows.py --login --dedicated-profile C:\Users\nopsi\temp\pixiv-collector-chrome --proxy http://127.0.0.1:7890
py -3 collect_pixiv_windows.py --mode hot --limit 48 --order popular --date-windows 7,30,90,180,365 --min-bookmarks 1000 --dedicated-profile C:\Users\nopsi\temp\pixiv-collector-chrome --proxy http://127.0.0.1:7890 --out ..\catalog\_pixiv_hot_export.jsonl
py -3 download_pixiv_originals.py --catalog ../catalog/_pixiv_hot_export.jsonl --out ../catalog/_originals_hot --dedicated-profile C:\Users\nopsi\temp\pixiv-collector-chrome --proxy http://127.0.0.1:7890
```

New Pixiv files land in gitignored `catalog/_originals_hot/`. The previous originals under `catalog/quarantine/poor-aesthetic-20260927/_originals/` and `catalog/_originals/` are train-unready and are not staged. Put Civitai full-size files in gitignored `catalog/_originals_civitai/`. Put anatomy stills in gitignored `catalog/_originals_anatomy/`. Thumbs (`square1200`, `master1200`) are not training files.

Review every file at full size. Delete a file when the series, character, or setting is child-coded. Do not commit images, cookies, or the Chrome profile.

### 2. Stage folders (Windows or Linux)

From `datasets/qwen21-anime-style/train/scripts`. Long edge at least 1024, short edge at least 768. Closer anatomy crops can pass `--min-long 768`.

```bat
py -3 stage_dataset.py --track style
py -3 stage_dataset.py --track anatomy
```

```bash
python3 stage_dataset.py --track style
python3 stage_dataset.py --track anatomy
```

Images are copied into gitignored `train/data/style` and `train/data/anatomy`. Existing files are left in place so a second stage does not wipe captions.

### 3. Caption

On the H100, after the data folder is uploaded (next section), or on a home GPU if you have one. From `train/scripts`, with `AI_TOOLKIT_ROOT` set to a current ai-toolkit checkout:

```bash
python3 caption_originals.py --track style --launch --apply
python3 caption_originals.py --track anatomy --launch --apply
```

`--launch` runs `Qwen/Qwen3-VL-8B-Instruct` through AI-Toolkit (`train/configs/caption_style.yaml` and `caption_anatomy.yaml`) and writes a `.txt` next to each image. `--apply` appends the anchor (`anime style, cel shading, clean lineart` or `anime cel shading, clean genital join`) and moves captions that fail `scripts/safety.py` into gitignored `train/rejected/`. A `SKIP` from the captioner is a reject.

Without a toolkit checkout, on a machine that already has torch and transformers:

```bash
python3 caption_originals.py --track style --run-transformers --apply
```

Hand-written captions are fine. Same `--apply` pass. Rules stay in `captions/README.md`. Read a sample of the `.txt` files before training. Metadata screening does not see the picture.

### 4. Train on the H100, then shut it down

Start the OneThing H100 yourself when steps 1–2 are done (and step 3, if you captioned at home). Upload `train/data/`. Clone this repo and ai-toolkit on the instance. Do not put `HF_TOKEN` or any other secret in the repo. Export it in the shell if a download asks for it.

```bash
git clone https://github.com/ostris/ai-toolkit.git
cd ai-toolkit
python3 -m venv .venv && source .venv/bin/activate
# PyTorch CUDA build from pytorch.org, then:
pip install -r requirements.txt
export AI_TOOLKIT_ROOT="$PWD"
cd /path/to/metaverse-assets/datasets/qwen21-anime-style/train/scripts
```

If `run.py` reports an unknown arch, `git pull` ai-toolkit. You want `qwen_image_2`.

```bash
python3 run_train.py --check style
python3 run_train.py style
python3 run_train.py --check anatomy
python3 run_train.py anatomy
```

`run_train.py` without `--check` is the training command. It refuses to start when captions are missing, the safety screen fails, `AI_TOOLKIT_ROOT` is unset, or `nvidia-smi` sees no GPU. Style and anatomy are separate runs. Skip anatomy when that folder is still empty. `python3 run_train.py both` runs style, then anatomy.

Weights land in gitignored `train/output/qwen21_anime_style_v1/` and `train/output/qwen21_anatomy_v1/`. Samples are in each run's `samples/` folder. Pick the step that holds the style without melted faces. Copy the `.safetensors` off the instance (scp, rsync, or the provider file browser). Do not commit them.

Stop the OneThing H100 in the provider console after the copy finishes. Confirm the instance is stopped. These scripts never call the provider API.

`python3 render_configs.py` only rewrites gitignored `train/rendered/*.yaml` if you want to inspect the paths before launching.
