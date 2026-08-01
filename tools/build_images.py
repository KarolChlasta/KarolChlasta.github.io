#!/usr/bin/env python3
"""Produce the web-sized images from the originals in new/.

Idempotent: re-running overwrites the outputs with identical results.
Run:  python3 tools/build_images.py

Prints the pixel dimensions of every output, because the HTML needs them in
width/height attributes to avoid layout shift.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "new"
OUT = ROOT / "assets/img"

# Hero: the seated three-quarter portrait, cropped to exactly 3:4.
#
# Chosen over the standing shot (K-CH_SP_26) on the strength of the render
# size: the hero image is about 350px wide, and at that width the standing
# pose leaves the face small while the suit fills the frame. This crop puts
# the face at roughly twice the size.
HERO_SRC = "K-CH_SP_27_ALK.jpg"
HERO_BOX = (366, 274, 3476, 4421)          # 3110 x 4147 = 3:4

# Open Graph card, 1200x630. Not a crop: a 2:3 portrait cut to 1.9:1 across
# the full width leaves nothing but a band across the eyes. The card is
# composed instead — the same portrait on the right, the session's own navy
# backdrop stretched behind it, and the join feathered so no seam shows.
OG_BG_BOX = (0, 700, 1150, 700 + int(1150 * 630 / 1200))
OG_FEATHER = 150

# "Beyond work": ultramarathon photo, fits inside a square box.
ABOUT_SRC = "K-CH_SP_23.jpg"

# Only the four the gallery actually shows. The other two source photos — the
# venue exterior at night and a second wide shot of the hall — were built once
# and never used, so they are not built any more.
# Output name -> source. Mapped explicitly rather than numbered by position,
# so dropping a photo cannot silently renumber the rest and break the markup.
# These four names are already live; the other two source photos, the venue
# exterior and a second wide shot of the hall, are not used by the gallery.
AWARDS = {
    "award-cio-3.jpg": "Karol_Chlasta-CIO_Award_2.jpg",   # the hall, wide
    "award-cio-4.jpg": "Karol_Chlasta-CIO_Award_3.jpg",   # winners on stage
    "award-cio-5.jpg": "Karol_Chlasta-CIO_Award_5.png",   # receiving the award
    "award-cio-6.jpg": "Karol_Chlasta-CIO_Award_6.png",   # speaking at the lectern
}


def save(image: Image.Image, name: str, quality: int = 82) -> None:
    path = OUT / name
    image.save(path, "JPEG", quality=quality, optimize=True, progressive=True)
    size_kb = path.stat().st_size / 1024
    print(f"{name:28} {image.width:5} x {image.height:<5} {size_kb:7.1f} KB")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    hero = Image.open(SRC / HERO_SRC).convert("RGB").crop(HERO_BOX)
    save(hero.resize((1200, 1600), Image.LANCZOS), "portrait-hero@2x.jpg")
    save(hero.resize((600, 800), Image.LANCZOS), "portrait-hero.jpg")

    full = Image.open(SRC / HERO_SRC).convert("RGB")
    card = full.crop(OG_BG_BOX).resize((1200, 630), Image.LANCZOS)
    figure = full.crop(HERO_BOX).resize((int(630 * 3 / 4), 630), Image.LANCZOS)
    mask = Image.new("L", figure.size, 255)
    pixels = mask.load()
    for x in range(min(OG_FEATHER, figure.width)):
        value = int(255 * x / OG_FEATHER)
        for y in range(figure.height):
            pixels[x, y] = value
    card.paste(figure, (1200 - figure.width, 0), mask)
    save(card, "og-card.jpg")

    about = Image.open(SRC / ABOUT_SRC).convert("RGB")
    about.thumbnail((900, 900), Image.LANCZOS)
    save(about, "portrait-about.jpg")

    for out_name, source in AWARDS.items():
        photo = Image.open(SRC / source).convert("RGB")
        photo.thumbnail((1600, 1600), Image.LANCZOS)
        save(photo, out_name)

    print("\nCopy the pixel dimensions above into the width/height attributes.")


if __name__ == "__main__":
    main()
