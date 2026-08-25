"""Regenerate icon assets from the source logo.

Reads logo.png (the full brand image) and produces:
  - tray_icon.png : the bolt emblem, cropped + black made transparent (reads on any tray bg)
  - app.ico       : multi-size icon for shortcuts (startup .lnk, desktop shortcut)

Run:  .venv\\Scripts\\python.exe make_icons.py
Drop a new logo.png in this folder and re-run to rebrand.
"""

import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(HERE, "logo.png")
TRAY_PNG = os.path.join(HERE, "tray_icon.png")
APP_ICO = os.path.join(HERE, "app.ico")


def _bright_bbox(im, y_lo, y_hi, thresh=60):
    """Bounding box of non-dark pixels within a vertical band [y_lo, y_hi)."""
    band = im.crop((0, y_lo, im.width, y_hi)).convert("RGB")
    px = band.load()
    minx = miny = 10**9
    maxx = maxy = -1
    for y in range(band.height):
        for x in range(band.width):
            r, g, b = px[x, y]
            if max(r, g, b) > thresh:
                if x < minx:
                    minx = x
                if x > maxx:
                    maxx = x
                if y < miny:
                    miny = y
                if y > maxy:
                    maxy = y
    if maxx < 0:
        return None
    return (minx, y_lo + miny, maxx + 1, y_lo + maxy + 1)


def _round_corners(im, radius_frac=0.16):
    """Keep the emblem on its dark tile (white bolt needs the contrast) but round the
    outer corners to transparent so it isn't a hard black square on light taskbars."""
    from PIL import ImageDraw

    im = im.convert("RGBA")
    w, h = im.size
    radius = int(min(w, h) * radius_frac)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    out = im.copy()
    out.putalpha(mask)
    return out


def build():
    im = Image.open(LOGO).convert("RGBA")
    w, h = im.size

    # The emblem (rounded square + bolt) lives in the top ~58% of the logo;
    # the "TRY LAUNCHER" wordmark is below that band, so we exclude it.
    bbox = _bright_bbox(im, 0, int(h * 0.58))
    if bbox is None:
        raise SystemExit("Could not locate the emblem in logo.png")

    # pad slightly and expand to a centered square
    x0, y0, x1, y1 = bbox
    pad = int(max(x1 - x0, y1 - y0) * 0.03)
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1, y1 = min(w, x1 + pad), min(h, y1 + pad)
    cw, ch = x1 - x0, y1 - y0
    side = max(cw, ch)
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    sx0 = max(0, cx - side // 2)
    sy0 = max(0, cy - side // 2)
    emblem = im.crop((sx0, sy0, sx0 + side, sy0 + side))

    emblem = _round_corners(emblem)

    emblem.resize((256, 256), Image.LANCZOS).save(TRAY_PNG)
    print("wrote", TRAY_PNG)

    sizes = [16, 24, 32, 48, 64, 128, 256]
    emblem.save(APP_ICO, sizes=[(s, s) for s in sizes])
    print("wrote", APP_ICO, "sizes", sizes)


if __name__ == "__main__":
    build()
