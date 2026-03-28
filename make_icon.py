"""
make_icon.py — Convert luca_logo.png -> audit_icon.ico for LUCA app.

Usage:
  1. Save the polyhedron image as  luca_logo.png  in this directory.
  2. Run:  python make_icon.py
  3. Rebuild the exe:  python -m PyInstaller luca.spec --noconfirm

Keeps white background intact — black lines on white, crisp at all sizes.
Saves a multi-resolution ICO:  16 / 32 / 48 / 64 / 128 / 256 px.
"""
from pathlib import Path
import sys

try:
    from PIL import Image, ImageEnhance, ImageOps
except ImportError:
    sys.exit("Pillow not installed. Run:  pip install pillow")

SRC   = Path(__file__).parent / "luca_logo.png"
DST   = Path(__file__).parent / "audit_icon.ico"
SIZES = [16, 32, 48, 64, 128, 256]


def make_square(img: Image.Image) -> Image.Image:
    """Pad to square with white background if not already square."""
    w, h = img.size
    if w == h:
        return img
    size = max(w, h)
    bg = Image.new("RGB", (size, size), (255, 255, 255))
    bg.paste(img, ((size - w) // 2, (size - h) // 2))
    return bg


def main():
    if not SRC.exists():
        sys.exit(
            f"ERROR: {SRC.name} not found.\n"
            "Save the polyhedron logo image as  luca_logo.png  in:\n"
            f"  {SRC.parent}"
        )

    print(f"Reading {SRC} ...")
    img = Image.open(SRC).convert("RGB")

    # Strong contrast boost: push lines to pure black, background to pure white
    img = ImageEnhance.Contrast(img).enhance(2.0)
    img = ImageEnhance.Sharpness(img).enhance(2.0)

    img = make_square(img)

    # Build all size variants — use LANCZOS for clean downscaling
    frames = []
    for s in SIZES:
        resized = img.resize((s, s), Image.LANCZOS)
        # At small sizes boost contrast again so lines don't blur to gray
        if s <= 32:
            resized = ImageEnhance.Contrast(resized).enhance(1.5)
        frames.append(resized.convert("RGB"))
        print(f"  {s}x{s} px")

    frames[0].save(
        DST,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=frames[1:],
    )
    print(f"\nIcon saved: {DST}")
    print("Next step: python -m PyInstaller luca.spec --noconfirm")


if __name__ == "__main__":
    main()
