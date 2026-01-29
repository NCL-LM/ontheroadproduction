from pathlib import Path
from PIL import Image, ImageOps
import os
import json
from flask import Flask, render_template, jsonify
import argparse

# Config
INPUT_DIR = Path("assets/originals")
OUTPUT_DIR = Path("static/optimized")
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"
# sizes to produce (px width)
SIZES = [1600, 1200, 800, 400]
# poster and og dimensions
POSTER_SIZE = (1200, 675)
OG_SIZE = (1200, 630)

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".tiff", ".webp"}

app = Flask(__name__, static_folder="static", template_folder="templates")

def ensure_dirs():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def make_responsive_variants(src_path: Path, out_base: Path):
    """
    Produce webp and jpeg variants at configured widths.
    Returns a dict with srcset strings and primary src.
    """
    img = Image.open(src_path).convert("RGB")
    name = src_path.stem
    variants = {"webp": [], "jpeg": []}
    for w in SIZES:
        # compute height to preserve aspect ratio
        ratio = w / img.width
        h = int(img.height * ratio)
        resized = img.resize((w, h), Image.LANCZOS)

        webp_path = out_base / f"{name}-{w}.webp"
        jpeg_path = out_base / f"{name}-{w}.jpg"

        resized.save(webp_path, "WEBP", quality=82, method=6)
        resized.save(jpeg_path, "JPEG", quality=82, optimize=True)

        variants["webp"].append((webp_path.as_posix(), w))
        variants["jpeg"].append((jpeg_path.as_posix(), w))

    # build srcset strings (webp first)
    webp_srcset = ", ".join(f"{p} {w}w" for p, w in variants["webp"])
    jpeg_srcset = ", ".join(f"{p} {w}w" for p, w in variants["jpeg"])

    # choose fallback src: the largest jpeg
    fallback = variants["jpeg"][0][0] if variants["jpeg"] else src_path.as_posix()
    return {"webp_srcset": webp_srcset, "jpeg_srcset": jpeg_srcset, "fallback": fallback}

def make_poster_and_og(src_path: Path, out_base: Path):
    """
    Create centered cropped poster and OG images with the target sizes.
    """
    img = Image.open(src_path).convert("RGB")
    poster = ImageOps.fit(img, POSTER_SIZE, Image.LANCZOS, centering=(0.5, 0.5))
    og = ImageOps.fit(img, OG_SIZE, Image.LANCZOS, centering=(0.5, 0.5))

    name = src_path.stem
    poster_path = out_base / f"{name}-poster.jpg"
    og_path = out_base / f"{name}-og.jpg"

    poster.save(poster_path, "JPEG", quality=84, optimize=True)
    og.save(og_path, "JPEG", quality=84, optimize=True)
    return {"poster": poster_path.as_posix(), "og": og_path.as_posix()}

def optimize_images(input_dir=INPUT_DIR, output_dir=OUTPUT_DIR):
    """
    Scan input_dir for images and produce optimized outputs under output_dir.
    Writes a manifest.json mapping basenames to srcsets and poster/og.
    """
    ensure_dirs()
    manifest = {}
    found = list(Path(input_dir).glob("*"))
    for p in found:
        if p.suffix.lower() not in ALLOWED_EXT:
            continue
        base_name = p.stem
        out_base = output_dir
        # generate responsive images
        resp = make_responsive_variants(p, out_base)
        # generate poster and og crops
        crops = make_poster_and_og(p, out_base)
        manifest[base_name] = {
            "webp_srcset": resp["webp_srcset"],
            "jpeg_srcset": resp["jpeg_srcset"],
            "fallback": resp["fallback"],
            "poster": crops["poster"],
            "og": crops["og"],
        }
        print(f"Optimized {p.name} -> {base_name} (variants created)")

    # save manifest
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"Manifest written to {MANIFEST_PATH}")
    return manifest

def load_manifest():
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

@app.route("/optimize", methods=["POST", "GET"])
def optimize_route():
    manifest = optimize_images()
    return jsonify({"status": "ok", "entries": len(manifest)})

@app.route("/")
def index():
    manifest = load_manifest()
    # pass manifest to template; template will use keys like "hero", "project1", etc.
    return render_template("index.html", manifest=manifest)

def main():
    parser = argparse.ArgumentParser(description="On The Road Production — app runner")
    parser.add_argument("--optimize", action="store_true", help="Run image optimization and exit")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    if args.optimize:
        optimize_images()
        print("Optimization complete.")
        return

    # On startup, if there's no manifest but there are originals, attempt a quick optimize
    if INPUT_DIR.exists() and not MANIFEST_PATH.exists():
        print("No manifest found; running initial optimization...")
        optimize_images()

    print(f"Starting dev server at http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=True)

if __name__ == "__main__":
    main()