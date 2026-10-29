"""Run with a Python containing Pillow: python -m unittest discover -s site/scripts/tests -v."""
import importlib.util
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest

from PIL import Image, ImageCms, PngImagePlugin

SCRIPT = Path(__file__).resolve().parents[1] / "optimize-backgrounds.py"


def pipeline():
    if not SCRIPT.is_file():
        raise AssertionError("Background optimization pipeline has not been implemented")
    spec = importlib.util.spec_from_file_location("optimize_backgrounds", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CropTests(unittest.TestCase):
    def test_center_crop_uses_brief_ratios_without_upscaling(self):
        module = pipeline()
        expected = {
            "hero": (3840, 2160), "speed": (3840, 2160),
            "tile-model": (3240, 2160), "versus": (3840, 2160),
            "things": (3840, 1646), "checksum": (3840, 2160),
            "tile-fingerprint": (2880, 2160), "why": (3840, 2160),
            "tile-fast": (2880, 2160), "how": (3840, 2160),
            "news": (3840, 2160), "tile-news": (3456, 2160),
            "install": (3840, 2160),
        }
        self.assertEqual(set(module.SLOTS), set(expected))
        for slot, size in expected.items():
            with self.subTest(slot=slot):
                left, top, right, bottom = module.crop_box((3840, 2160), module.SLOTS[slot])
                self.assertEqual((right - left, bottom - top), size)
                self.assertLessEqual(abs(left - (3840 - right)), 1)
                self.assertLessEqual(abs(top - (2160 - bottom)), 1)
        self.assertEqual(module.crop_box((100, 300), (16, 9)), (0, 122, 100, 178))


class ValidationTests(unittest.TestCase):
    def test_invalid_requests_fail_before_publishing(self):
        module = pipeline()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            originals, site = root / "originals", root / "site"
            originals.mkdir()
            Image.new("RGB", (100, 60)).save(originals / "hero.png")
            cases = [(["hero"], 4, "workers"), (["hero"], 0, "workers"),
                     ([], 1, "slot"), (["hero", "hero"], 1, "duplicate"),
                     (["unknown"], 1, "Unknown"), (["speed"], 1, "Missing"),
                     (["hero"], 1, "960")]
            for slots, workers, message in cases:
                with self.subTest(slots=slots, workers=workers):
                    with self.assertRaisesRegex(ValueError, message):
                        module.run_pipeline(originals, site, slots, workers)
                    self.assertFalse(site.exists())

    def test_refuses_to_overwrite_master_directory(self):
        module = pipeline()
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            originals = site / "backgrounds/crops"
            originals.mkdir(parents=True)
            Image.new("RGB", (960, 540)).save(originals / "hero.png")
            with self.assertRaisesRegex(ValueError, "master"):
                module.run_pipeline(originals, site, ["hero"])

    def test_decode_dimension_mismatch_is_fatal(self):
        module = pipeline()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.png"
            Image.new("RGB", (64, 64)).save(source)
            with self.assertRaisesRegex(ValueError, "Decoded size mismatch"):
                module.encode((module.tools(), source, root / "bad.webp", (65, 64)))

    def test_codec_failure_reports_stderr(self):
        with self.assertRaisesRegex(RuntimeError, "codec test failure"):
            pipeline().command([sys.executable, "-c", "import sys; sys.exit('codec test failure')"])

    def test_rerun_removes_only_stale_renditions_of_selected_slot(self):
        module = pipeline()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            originals, site = root / "originals", root / "site"
            originals.mkdir()
            Image.new("RGB", (960, 540)).save(originals / "hero.png")
            public = site / "public/backgrounds"
            public.mkdir(parents=True)
            (public / "hero-1600.avif").write_bytes(b"stale larger rendition")
            (public / "speed-1600.avif").write_bytes(b"unselected slot")
            (public / "hero-custom.avif").write_bytes(b"not managed by pipeline")
            module.run_pipeline(originals, site, ["hero"])
            self.assertFalse((public / "hero-1600.avif").exists())
            self.assertEqual((public / "speed-1600.avif").read_bytes(), b"unselected slot")
            self.assertEqual((public / "hero-custom.avif").read_bytes(), b"not managed by pipeline")

    def test_full_default_run_has_all_thirteen_slots(self):
        module = pipeline()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            originals, site = root / "originals", root / "site"
            originals.mkdir()
            for slot in module.SLOTS:
                Image.new("RGB", (1280, 960), (6, 20, 40)).save(originals / f"{slot}.png")
            result = module.run_pipeline(originals, site)
            self.assertEqual(result["counts"], {"slots": 13, "crops": 13, "exports": 39, "by_format": {"avif": 13, "webp": 13, "jxl": 13}})
            self.assertEqual(len(list((site / "backgrounds/crops").glob("*.png"))), 13)
            self.assertTrue(all(len(row["exports"]) == 3 for row in result["slots"]))


class PipelineTests(unittest.TestCase):
    def test_real_codecs_export_verify_and_preserve_master(self):
        module = pipeline()
        self.assertTrue(callable(getattr(module, "run_pipeline", None)), "Missing executable encoding pipeline")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            originals, site = root / "originals", root / "site"
            originals.mkdir()
            master = originals / "hero.png"
            metadata = PngImagePlugin.PngInfo()
            metadata.add_text("private-note", "must not be shipped")
            Image.new("RGB", (1000, 600), (6, 20, 40)).save(
                master, pnginfo=metadata,
                icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes(),
            )
            before = hashlib.sha256(master.read_bytes()).hexdigest()
            result = module.run_pipeline(originals, site, ["hero"], workers=2)
            self.assertEqual(result["counts"], {"slots": 1, "crops": 1, "exports": 3, "by_format": {"avif": 1, "webp": 1, "jxl": 1}})
            self.assertEqual(result["slots"][0]["master"]["dimensions"], [1000, 600])
            self.assertEqual(result["slots"][0]["master"]["sha256"], before)
            self.assertEqual(result["slots"][0]["crop"]["dimensions"], [1000, 562])
            self.assertEqual(result["settings"]["workers"], 2)
            self.assertEqual(result["settings"]["encoder_threads"], 1)
            for exported in result["slots"][0]["exports"]:
                target = site / exported["path"]
                self.assertEqual(exported["dimensions"], [960, 540])
                self.assertTrue(exported["verified"])
                self.assertEqual(target.stat().st_size, exported["bytes"])
            self.assertEqual(sorted(p.suffix for p in (site / "public/backgrounds").glob("hero-*")), [".avif", ".jxl", ".webp"])
            crop = site / "backgrounds/crops/hero.png"
            with Image.open(crop) as image:
                self.assertEqual(image.size, (1000, 562))
                self.assertNotIn("private-note", image.info)
                self.assertIn("icc_profile", image.info)
            saved = json.loads((site / "backgrounds/manifest.json").read_text())
            self.assertEqual(saved, result)
            self.assertEqual(result["total_encoded_bytes"], sum(e["bytes"] for e in result["slots"][0]["exports"]))
            rerun = module.run_pipeline(originals, site, ["hero"], workers=1)
            self.assertEqual(rerun["counts"], result["counts"])
            self.assertEqual(hashlib.sha256(master.read_bytes()).hexdigest(), before)


if __name__ == "__main__":
    unittest.main()
