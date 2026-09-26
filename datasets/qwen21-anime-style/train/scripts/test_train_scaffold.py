"""Offline checks for the LoRA scaffold. No GPU and no network."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from caption_originals import screen_folder
from common import (
    ANCHORS,
    CAPTION_PROMPTS,
    CONFIG_DIR,
    DATASET,
    REPO_ROOT,
    finish_caption,
    image_size,
    png_bytes,
)
from render_configs import render
from stage_dataset import stage


class CaptionTest(unittest.TestCase):
    def test_anchor_and_safety(self):
        status, text = finish_caption(
            "Half-body anime portrait of an adult woman in a dark dress, closed mouth, soft rim light.",
            "style",
        )
        self.assertEqual(status, "ok")
        self.assertIn(ANCHORS["style"], text)
        again, twice = finish_caption(text, "style")
        self.assertEqual(again, "ok")
        self.assertEqual(twice.lower().count(ANCHORS["style"].lower()), 1)

        status, text = finish_caption("beautiful 16yo schoolgirl in a serafuku", "style")
        self.assertNotEqual(status, "ok")
        self.assertEqual(text, "")
        status, _ = finish_caption("SKIP", "anatomy")
        self.assertEqual(status, "empty_or_skip")

        status, text = finish_caption(
            "Side view of two adults, clear vaginal penetration, limbs separate, two nipples.",
            "anatomy",
        )
        self.assertEqual(status, "ok", status)
        self.assertIn(ANCHORS["anatomy"], text)

    def test_apply_quarantines_outside_the_dataset_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = root / "images"
            images.mkdir()
            good = images / "a.png"
            bad = images / "b.png"
            good.write_bytes(png_bytes(8, 8))
            bad.write_bytes(png_bytes(8, 8))
            good.with_suffix(".txt").write_text(
                "Anime illustration of an adult woman in armor, closed mouth, dusk sky.\n",
                encoding="utf-8",
            )
            bad.with_suffix(".txt").write_text("16 year old schoolgirl, serafuku\n", encoding="utf-8")
            reject = root / "rejected"
            result = screen_folder(images, "style", apply=True, reject_dir=reject)
            self.assertEqual(result["kept"], 1)
            self.assertEqual(len(result["rejected"]), 1)
            self.assertIn(ANCHORS["style"], good.with_suffix(".txt").read_text(encoding="utf-8"))
            self.assertFalse(bad.exists())
            self.assertTrue((reject / "style" / "b.png").is_file())


class StageTest(unittest.TestCase):
    def test_copies_full_size_and_skips_thumbs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src"
            src.mkdir()
            (src / "keep.png").write_bytes(png_bytes(1280, 1024))
            (src / "tiny.png").write_bytes(png_bytes(64, 64))
            (src / "square1200_thumb.png").write_bytes(png_bytes(1280, 1024))
            (src / "manifest.jsonl").write_text("{}\n", encoding="utf-8")
            dest = root / "out"
            result = stage([src], dest, min_long=1024, min_short=768)
            self.assertEqual(result["copied"], 1)
            self.assertTrue((dest / "keep.png").is_file())
            self.assertFalse((dest / "tiny.png").exists())
            self.assertFalse((dest / "square1200_thumb.png").exists())
            self.assertEqual(image_size(dest / "keep.png"), (1280, 1024))
            (dest / "keep.txt").write_text("old caption\n", encoding="utf-8")
            (src / "keep.png").write_bytes(png_bytes(1600, 1024))
            replaced = stage([src], dest, min_long=1024, min_short=768)
            self.assertEqual(replaced["copied"], 1)
            self.assertFalse((dest / "keep.txt").exists())
            self.assertEqual(image_size(dest / "keep.png"), (1600, 1024))

    def test_refuses_repo_paths_outside_train_data(self):
        with self.assertRaises(SystemExit):
            stage([Path("/tmp")], DATASET / "catalog", min_long=1, min_short=1)

    def test_refuses_quarantine_and_deprecated_originals(self):
        from stage_dataset import assert_trainable_source

        with self.assertRaises(SystemExit):
            assert_trainable_source(DATASET / "catalog" / "quarantine" / "poor-aesthetic-20260927" / "_originals")
        with self.assertRaises(SystemExit):
            assert_trainable_source(DATASET / "catalog" / "_originals")
        with self.assertRaises(SystemExit):
            assert_trainable_source(DATASET / "catalog" / "_originals_apr_oct")
        with self.assertRaises(SystemExit):
            assert_trainable_source(DATASET / "catalog" / "quarantine" / "pre-hot-rerank" / "_originals_apr_oct")
        assert_trainable_source(DATASET / "catalog" / "_originals_hot")
        assert_trainable_source(DATASET / "catalog" / "_originals_civitai")


class ConfigTest(unittest.TestCase):
    def test_templates_match_the_h100_defaults(self):
        style = (CONFIG_DIR / "style_lora.yaml").read_text(encoding="utf-8")
        anatomy = (CONFIG_DIR / "anatomy_lora.yaml").read_text(encoding="utf-8")
        for text in (style, anatomy):
            self.assertIn('arch: "qwen_image_2"', text)
            self.assertNotIn('arch: "qwen_image"', text)
            self.assertIn('name_or_path: "Qwen/Qwen-Image-2.1"', text)
            self.assertIn("resolution: [1024, 1280, 1536]", text)
            self.assertIn("batch_size: 1", text)
            self.assertIn("train_text_encoder: false", text)
            self.assertIn("gradient_checkpointing: true", text)
            self.assertIn("lr: 1.0e-4", text)
            self.assertIn("quantize: false", text)
            self.assertIn("use_comfy_weights: false", text)
            self.assertIn("guidance_scale: 1.0", text)
            self.assertIn("seed: 26092755", text)
            self.assertIn("push_to_hub: false", text)
            self.assertIn("__DATASET_DIR__", text)
            self.assertNotIn("hf_token", text.lower())
            self.assertNotIn("api_key", text.lower())
        self.assertIn("linear: 32", style)
        self.assertIn("steps: 2000", style)
        self.assertIn("linear: 16", anatomy)
        self.assertIn("steps: 2500", anatomy)
        self.assertIn(CAPTION_PROMPTS["style"], (CONFIG_DIR / "caption_style.yaml").read_text(encoding="utf-8"))
        self.assertIn(CAPTION_PROMPTS["anatomy"], (CONFIG_DIR / "caption_anatomy.yaml").read_text(encoding="utf-8"))

    def test_render_fills_absolute_paths_outside_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = render("style", "train", Path(tmp))
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("__DATASET_DIR__", text)
            self.assertNotIn("__OUTPUT_DIR__", text)
            self.assertIn("/train/data/style", text.replace("\\", "/"))
            self.assertIn('arch: "qwen_image_2"', text)

    def test_image_and_output_paths_are_gitignored(self):
        probe = DATASET / "train" / "data" / "style" / "probe.png"
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_bytes(png_bytes(8, 8))
        try:
            for rel in (
                "datasets/qwen21-anime-style/train/data/style/probe.png",
                "datasets/qwen21-anime-style/train/output/lora.safetensors",
                "datasets/qwen21-anime-style/train/rendered/style_lora.yaml",
                "datasets/qwen21-anime-style/catalog/_originals/1_p0.jpg",
                "datasets/qwen21-anime-style/catalog/_originals_anatomy/a.png",
            ):
                result = subprocess.run(
                    ["git", "check-ignore", "-q", rel],
                    cwd=REPO_ROOT,
                    capture_output=True,
                )
                self.assertEqual(result.returncode, 0, rel)
        finally:
            probe.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
