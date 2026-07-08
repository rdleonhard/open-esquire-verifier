#!/usr/bin/env python3
"""Render the Open Esquire Chambers app icon (gold diamond seal over an
engraved double rule, on the letterhead's near-black) and pack it as .icns
via iconutil. Usage: make_icon.py <out.icns>"""
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

GOLD = (231, 190, 85, 255)
GOLD_DIM = (154, 127, 58, 255)
BG = (5, 6, 8, 255)
IVORY = (239, 230, 207, 255)


def render(px):
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = px * 0.06                       # rounded-square plate, macOS style
    d.rounded_rectangle([m, m, px - m, px - m], radius=px * 0.22, fill=BG,
                        outline=GOLD_DIM, width=max(1, px // 128))
    cx, cy = px / 2, px / 2
    # double rule
    for y, col in ((cy + px * 0.215, GOLD_DIM), (cy + px * 0.245, GOLD_DIM)):
        d.line([px * 0.24, y, px * 0.76, y], fill=col,
               width=max(1, px // 170))
    # diamond seal
    r = px * 0.19
    pts = [(cx, cy - r * 1.35), (cx + r, cy - r * 0.1),
           (cx, cy + r * 1.15), (cx - r, cy - r * 0.1)]
    d.polygon(pts, outline=GOLD, width=max(2, px // 64))
    inner = [(cx, cy - r * 0.95), (cx + r * 0.62, cy - r * 0.1),
             (cx, cy + r * 0.75), (cx - r * 0.62, cy - r * 0.1)]
    d.polygon(inner, fill=GOLD)
    # flanking diamonds
    for fx in (px * 0.22, px * 0.78):
        s = px * 0.022
        d.polygon([(fx, cy - s), (fx + s, cy), (fx, cy + s), (fx - s, cy)],
                  fill=GOLD_DIM)
    return img


def main(out):
    with tempfile.TemporaryDirectory() as td:
        iconset = os.path.join(td, "chambers.iconset")
        os.makedirs(iconset)
        for size in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                px = size * scale
                name = "icon_%dx%d%s.png" % (
                    size, size, "@2x" if scale == 2 else "")
                render(px).save(os.path.join(iconset, name))
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", out],
                       check=True)
    print("icon:", out)


if __name__ == "__main__":
    main(sys.argv[1])
