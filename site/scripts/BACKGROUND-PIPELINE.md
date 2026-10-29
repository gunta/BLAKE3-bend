# Background optimization

`optimize-backgrounds.py` reads `<slot>.png` masters from
`site/backgrounds/originals` by default. Run from the repository root:

```sh
python3 site/scripts/optimize-backgrounds.py
python3 site/scripts/optimize-backgrounds.py --slots hero --workers 2
python3 -m unittest discover -s site/scripts/tests -v
```

Requirements: Python 3.10+ with **Pillow**, and `avifenc`, `avifdec`, `cwebp`,
`dwebp`, `cjxl`, `djxl`. The executables are resolved from PATH, falling back to
`/opt/homebrew/bin`. On macOS, `brew install libavif webp jpeg-xl` installs them.
No image generation, component edits, or site build is performed.

## Using the installed Hermes Python

On this machine, the ordinary `python3` does **not** contain Pillow. Hermes'
managed environment does. This shell helper discovers the runtime and preserves
its bootstrap instead of hard-coding a changing virtualenv path:

```sh
hpython() {
  python3 - "$@" <<'PY'
import json
import subprocess
import sys
command = json.loads(subprocess.check_output(["hermes", "--print-runtime-command"]))
bootstrap = command[-1].split("runpy.run_module(")[0]
command[-1] = bootstrap + "sys.argv=" + repr(sys.argv[1:]) + "; runpy.run_path(sys.argv[0], run_name='__main__')"
sys.exit(subprocess.call(command))
PY
}

export TMPDIR=/Users/minion/.hermes/cache/scratch
hpython site/scripts/tests/test_optimize_backgrounds.py -v
hpython site/scripts/optimize-backgrounds.py --workers 3
```

For an isolated smoke test, put or symlink a real master at
`$TMPDIR/background-smoke/originals/hero.png`, then run:

```sh
hpython site/scripts/optimize-backgrounds.py \
  --source-dir "$TMPDIR/background-smoke/originals" \
  --site-dir "$TMPDIR/background-smoke/site" \
  --slots hero
```

`--site-dir` changes only the output root, not the default input directory; specify
both paths for an isolated run. No final repository images are needed for a smoke
test.

## Outputs and guarantees

- All thirteen slots are required unless `--slots` is supplied. Ratios match the
  background brief: 16:9 except `tile-model` 3:2, `things` 21:9,
  `tile-fingerprint` and `tile-fast` 4:3, and `tile-news` 16:10.
- Masters are read-only. Actual input dimensions and SHA-256 hashes are recorded;
  no assumption that an input really is 3840×2160 is made.
- Center crops preserve native pixels; fractional crop dimensions round to the
  nearest pixel. PNG crops go to `backgrounds/crops/<slot>.png` under the output root (build
  input only; nothing under `backgrounds/` is deployed).
- Each crop is resized with Lanczos to 960, 1600, 2400, 3200 and 3840 pixels wide,
  **only when that width is no larger than the crop**. Inputs whose crop is below
  960 pixels wide are rejected, never enlarged.
- Renditions go to `public/backgrounds/<slot>-<width>.{avif,webp,jxl}`.
  Settings: AVIF quality 75 / speed 6 / YUV444 / full-range sRGB;
  WebP quality 88 / method 6; JPEG XL distance 1 / effort 7.
- Tagged source pixels are converted to sRGB; untagged sources are assumed sRGB.
  RGB output strips EXIF/XMP/text and retains only the sRGB color profile.
- Every compressed file is decoded with its format's standalone decoder, fully
  loaded by Pillow, and checked against the expected dimensions before publishing.
- At most three worker processes run codecs concurrently, each codec using one
  thread. `--workers` accepts only 1, 2, or 3. Each codec invocation has a
  ten-minute timeout.
- All work is staged first; missing inputs and encoding/decoding failures do not
  publish partial images. Publication uses atomic replacement **per file**, not
  a transaction for the entire set (a filesystem error during publication can
  therefore leave a mixed set).
- Reruns replace selected-slot outputs and remove obsolete renditions at the five
  managed widths. Other slots and custom filenames are left alone. Do not run
  multiple pipelines against the same output directory concurrently.
- `backgrounds/manifest.json` is replaced on each successful invocation. It lives
  outside `public/` so it is not deployed, and records paths relative to the site.
  It describes **that invocation's selected slots**, not any unselected files
  already on disk. It records crop boxes, input/output dimensions, settings,
  original hashes/sizes, verified rendition sizes, format counts and total encoded
  bytes. Run without `--slots` for the complete release manifest.

The tests run the real installed encoders and decoders, including an all-thirteen
small-fixture pass; they do not generate final repository assets.
