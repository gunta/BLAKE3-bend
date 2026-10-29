#!/usr/bin/env python3
"""Center-crop and encode the thirteen site background slots."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image, ImageCms

WIDTHS = (960, 1600, 2400, 3200, 3840)
# Build inputs, never deployed: the manifest Backdrop.astro reads, and the slot crops.
MANIFEST = "backgrounds/manifest.json"
CROPS = "backgrounds/crops"
FORMATS = ("avif", "webp", "jxl")
SLOTS = {
    "hero": (16, 9), "speed": (16, 9), "tile-model": (3, 2),
    "versus": (16, 9), "things": (21, 9), "checksum": (16, 9),
    "tile-fingerprint": (4, 3), "why": (16, 9), "tile-fast": (4, 3),
    "how": (16, 9), "news": (16, 9), "tile-news": (16, 10),
    "install": (16, 9),
}


def crop_box(size, ratio):
    """Largest centered crop, rounding fractional target pixels to nearest."""
    width, height = size
    a, b = ratio
    if width * b > height * a:
        crop_width, crop_height = round(height * a / b), height
    else:
        crop_width, crop_height = width, round(width * b / a)
    left, top = (width - crop_width) // 2, (height - crop_height) // 2
    return left, top, left + crop_width, top + crop_height


def command(arguments):
    """Run a codec, retaining its diagnostic output on failure."""
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=600)
    if result.returncode:
        raise RuntimeError(f"Codec failed ({result.returncode}): {arguments!r}\n{result.stdout}\n{result.stderr}")
    return result.stdout + result.stderr


def tools():
    """Resolve encoders/decoders; allow Homebrew outside PATH."""
    found = {}
    for name in ("avifenc", "cwebp", "cjxl", "avifdec", "dwebp", "djxl"):
        executable = shutil.which(name)
        if not executable and (Path("/opt/homebrew/bin") / name).is_file():
            executable = str(Path("/opt/homebrew/bin") / name)
        if not executable:
            raise ValueError(f"Required codec missing: {name}; install libavif webp jpeg-xl")
        found[name] = executable
    return found


def encode(task):
    """Encode and independently decode one rendition, checking actual pixels."""
    codec_tools, source, target, dimensions = task
    suffix = target.suffix[1:]
    if suffix == "avif":
        args = [codec_tools["avifenc"], "-j", "1", "-q", "75", "-s", "6",
                "--yuv", "444", "--cicp", "1/13/1", "--range", "full",
                "--ignore-exif", "--ignore-xmp", str(source), str(target)]
    elif suffix == "webp":
        args = [codec_tools["cwebp"], "-quiet", "-q", "88", "-m", "6",
                "-metadata", "icc", str(source), "-o", str(target)]
    else:
        args = [codec_tools["cjxl"], str(source), str(target), "-d", "1", "-e", "7",
                "--num_threads=1", "-x", "strip=exif", "-x", "strip=xmp",
                "-x", "strip=jumbf", "--quiet"]
    command(args)
    decoded = target.with_suffix(f".{suffix}.decoded.png")
    if suffix == "avif":
        decode_args = [codec_tools["avifdec"], "-j", "1", str(target), str(decoded)]
    elif suffix == "webp":
        decode_args = [codec_tools["dwebp"], str(target), "-quiet", "-o", str(decoded)]
    else:
        decode_args = [codec_tools["djxl"], str(target), str(decoded), "--num_threads=1", "--quiet"]
    command(decode_args)
    with Image.open(decoded) as image:
        image.load()
        if image.size != dimensions:
            raise ValueError(f"Decoded size mismatch: {target}: {image.size} != {dimensions}")
    decoded.unlink()
    return {"path": f"public/backgrounds/{target.name}", "format": suffix,
            "dimensions": list(dimensions), "bytes": target.stat().st_size, "verified": True}


def run_pipeline(source_dir, site_dir, slots=None, workers=3):
    """Stage all outputs, verify codecs, then publish; never modify masters."""
    source_dir, site_dir = Path(source_dir).resolve(), Path(site_dir).resolve()
    selected = list(SLOTS) if slots is None else list(slots)
    if workers not in (1, 2, 3):
        raise ValueError("workers must be between 1 and 3")
    if not selected:
        raise ValueError("At least one slot is required")
    if len(selected) != len(set(selected)):
        raise ValueError("Repeated/duplicate slots are not allowed")
    unknown = set(selected) - set(SLOTS)
    if unknown:
        raise ValueError(f"Unknown slots: {sorted(unknown)}")
    for slot in selected:
        master = source_dir / f"{slot}.png"
        if not master.is_file():
            raise ValueError(f"Missing master: {master}")
        if master.resolve() == (site_dir / f"{CROPS}/{slot}.png").resolve():
            raise ValueError(f"Output would overwrite master: {master}")
        with Image.open(master) as image:
            if image.format != "PNG":
                raise ValueError(f"Master must be PNG: {master}")
            box = crop_box(image.size, SLOTS[slot])
            if box[2] - box[0] < min(WIDTHS):
                raise ValueError(f"Cropped master must be at least 960 px wide: {master}")
    codec_tools = tools()
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    records = []
    tasks = []
    # TemporaryDirectory respects TMPDIR (the Hermes scratch directory locally).
    with tempfile.TemporaryDirectory(prefix="backgrounds-") as temporary:
        stage = Path(temporary)
        for slot in selected:
            master = source_dir / f"{slot}.png"
            with Image.open(master) as original:
                original.load()
                dimensions = original.size
                box = crop_box(dimensions, SLOTS[slot])
                if original.info.get("icc_profile"):
                    rgb = ImageCms.profileToProfile(
                        original.convert("RGB"),
                        ImageCms.ImageCmsProfile(io.BytesIO(original.info["icc_profile"])),
                        ImageCms.createProfile("sRGB"), outputMode="RGB",
                    )
                else:
                    rgb = original.convert("RGB")
                assert rgb is not None
                # New RGB image drops all EXIF/XMP/text while retaining sRGB explicitly.
                region = rgb.crop(box)
                cropped = Image.frombytes("RGB", region.size, region.tobytes())
            crop_file = stage / f"{slot}.png"
            cropped.save(crop_file, icc_profile=profile)
            record = {
                "slot": slot, "ratio": list(SLOTS[slot]),
                "master": {"path": master.name, "dimensions": list(dimensions),
                           "bytes": master.stat().st_size,
                           "sha256": hashlib.sha256(master.read_bytes()).hexdigest()},
                "crop": {"path": f"{CROPS}/{slot}.png", "box": list(box),
                         "dimensions": list(cropped.size), "bytes": crop_file.stat().st_size},
                "exports": [],
            }
            for width in WIDTHS:
                if width > cropped.width:
                    continue
                size = (width, round(width * cropped.height / cropped.width))
                rendition = stage / f"{slot}-{width}.png"
                resized = cropped.resize(size, Image.Resampling.LANCZOS)
                resized.save(rendition, icc_profile=profile)
                for extension in FORMATS:
                    target = stage / f"{slot}-{width}.{extension}"
                    tasks.append((codec_tools, rendition, target, size))
            records.append(record)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            exports = list(executor.map(encode, tasks))
        for record in records:
            record["exports"] = [e for e in exports if Path(e["path"]).name.startswith(record["slot"] + "-")]
        result = {
            "schema_version": 1, "slots": records,
            "settings": {"widths": list(WIDTHS), "workers": workers, "encoder_threads": 1,
                         "color_space": "sRGB", "metadata": "color profile only",
                         "avif": {"quality": 75, "speed": 6, "yuv": "444"},
                         "webp": {"quality": 88, "method": 6},
                         "jxl": {"distance": 1, "effort": 7}},
            "counts": {"slots": len(records), "crops": len(records), "exports": len(exports),
                       "by_format": {fmt: sum(e["format"] == fmt for e in exports) for fmt in FORMATS}},
            "total_encoded_bytes": sum(e["bytes"] for e in exports),
        }
        for record in records:
            for item in [record["crop"], *record["exports"]]:
                destination = site_dir / item["path"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                # copy + replace works even if TMPDIR and repository are on different volumes.
                pending = destination.with_name(destination.name + ".tmp")
                shutil.copyfile(stage / destination.name, pending)
                os.replace(pending, destination)
        for record in records:
            wanted = {Path(item["path"]).name for item in record["exports"]}
            for width in WIDTHS:
                for extension in FORMATS:
                    name = f"{record['slot']}-{width}.{extension}"
                    if name not in wanted:
                        (site_dir / "public/backgrounds" / name).unlink(missing_ok=True)
        manifest = site_dir / MANIFEST
        manifest.parent.mkdir(parents=True, exist_ok=True)
        pending = manifest.with_suffix(".json.tmp")
        pending.write_text(json.dumps(result, indent=2) + "\n")
        os.replace(pending, manifest)
    return result


def main(argv=None):
    default_site = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=default_site / "backgrounds/originals")
    parser.add_argument("--site-dir", type=Path, default=default_site,
                        help="Output site root; use a scratch directory for smoke tests")
    parser.add_argument("--slots", nargs="+", choices=list(SLOTS), help="Default: all thirteen slots")
    parser.add_argument("--workers", type=int, choices=(1, 2, 3), default=3)
    args = parser.parse_args(argv)
    try:
        result = run_pipeline(args.source_dir, args.site_dir, args.slots, args.workers)
    except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"Background optimization failed: {error}\n")
    print(json.dumps({"manifest": str(args.site_dir / MANIFEST),
                      **result["counts"], "total_encoded_bytes": result["total_encoded_bytes"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
