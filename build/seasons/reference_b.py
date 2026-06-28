"""Reference for option-B summer blobs: decode like the Solidity renderer, build
SVG + metadata JSON, verify SVG rasterises to the source image + attributes match,
and emit Foundry fixtures (keccak svg/json hashes).
"""
import base64
import json
import os
import re
import struct
import sys

from Crypto.Hash import keccak
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from encoding import decode_sprite  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "out_b", "summer")
IMG = os.path.join(ROOT, "images", "seasons", "summer", "1600x1600")
META = os.path.join(ROOT, "metadata", "seasons", "summer")
ORDER = ["background", "body", "spikes", "chest", "feet", "hands", "head", "face", "eyes"]
ALPHA = sorted(ORDER)
TRANS = (0, 0, 0, 0)
US = "\x1f"
RECT = re.compile(r"<rect x='(\d+)' y='(\d+)' width='(\d+)' height='1' fill='#([0-9a-f]{6}(?:[0-9a-f]{2})?)'/>")


def kec(s):
    h = keccak.new(digest_bits=256); h.update(s.encode()); return "0x" + h.hexdigest()


def build_svg(grid):
    parts = ["<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' shape-rendering='crispEdges'>"]
    for y in range(16):
        x = 0
        while x < 16:
            c = grid[y * 16 + x]; x2 = x
            while x2 < 16 and grid[y * 16 + x2] == c:
                x2 += 1
            r, g, b, a = c
            fill = f"#{r:02x}{g:02x}{b:02x}" if a == 255 else f"#{r:02x}{g:02x}{b:02x}{a:02x}"
            parts.append(f"<rect x='{x}' y='{y}' width='{x2 - x}' height='1' fill='{fill}'/>")
            x = x2
    parts.append("</svg>")
    return "".join(parts)


def raster(svg):
    g = [None] * 256
    for m in RECT.finditer(svg):
        x, y, w, hexc = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
        r, gn, b = int(hexc[0:2], 16), int(hexc[2:4], 16), int(hexc[4:6], 16)
        a = int(hexc[6:8], 16) if len(hexc) == 8 else 255
        for xx in range(x, x + w):
            g[y * 16 + xx] = (r, gn, b, a)
    return g


def grid16(tid):
    im = Image.open(os.path.join(IMG, f"{tid}.png")).convert("RGBA")
    w, h = im.size; cw, ch = w // 16, h // 16; p = im.load()
    return [p[sx * cw + cw // 2, sy * ch + ch // 2] for sy in range(16) for sx in range(16)]


def main():
    M = json.load(open(os.path.join(OUT, "manifest.json")))
    spr_chunks = [open(os.path.join(OUT, "sprites", f"{i:04d}.bin"), "rb").read() for i in range(M["nSpriteChunks"])]
    spr_loc = open(os.path.join(OUT, "spriteLoc.bin"), "rb").read()
    dchunks = [open(os.path.join(OUT, "data", f"{i:04d}.bin"), "rb").read() for i in range(M["nDataChunks"])]
    loc = b"".join(open(os.path.join(OUT, "loc", f"{i:04d}.bin"), "rb").read() for i in range(M["nLocChunks"]))
    pal_raw = open(os.path.join(OUT, "corrPalette.bin"), "rb").read()
    palette = [tuple(pal_raw[i:i + 4]) for i in range(0, len(pal_raw), 4)]
    cats = open(os.path.join(OUT, "cats.txt")).read().split("\n")
    vals = [b.split("\n") for b in open(os.path.join(OUT, "vals.txt")).read().split(US)]
    one = open(os.path.join(OUT, "one.txt")).read().split("\n")
    catBase = M["catBase"]
    DISP, DESC = M["displayName"], M["description"]

    sprites = []
    for i in range(M["nSprites"]):
        ci, lo = struct.unpack(">HH", spr_loc[i * 4:i * 4 + 4])
        sprites.append(decode_sprite(spr_chunks[ci], lo)[0])

    fix_dir = os.path.join(ROOT, "contracts", "test", "fixtures", "seasons")
    os.makedirs(fix_dir, exist_ok=True)
    img_bad = attr_bad = 0
    svgH, jsonH = [], []
    for idx in range(M["count"]):
        tid = idx + 1
        ci, lo = struct.unpack(">HH", loc[idx * 4:idx * 4 + 4])
        data = dchunks[ci]; o = lo
        flag = data[o]; o += 1
        canvas = [TRANS] * 256
        attrs = []
        if flag == 0:
            vidx = list(data[o:o + 9]); o += 9
            for c in ORDER:
                ci2 = ORDER.index(c)
                s = sprites[catBase[ci2] + vidx[ci2]]
                for p in range(256):
                    if s[p] != TRANS:
                        canvas[p] = s[p]
            for c in ALPHA:
                ci2 = ORDER.index(c)
                attrs.append((c, vals[ci2][vidx[ci2]]))
        else:
            attrs.append(("1/1", one[data[o]])); o += 1
        nc = struct.unpack(">H", data[o:o + 2])[0]; o += 2
        for _ in range(nc):
            p, cid = struct.unpack(">BH", data[o:o + 3]); o += 3
            canvas[p] = palette[cid]
        svg = build_svg(canvas)
        if raster(svg) != grid16(tid):
            img_bad += 1
        # attrs match source metadata
        src = {a["trait_type"]: a["value"]
               for a in json.load(open(os.path.join(META, str(tid))))["attributes"]}
        image = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
        j = ('{"name":"%s #%d","description":"%s","tokenId":%d,"attributes":[%s],"image":"%s"}'
             % (DISP, tid, DESC, tid, ",".join('{"trait_type":"%s","value":"%s"}' % a for a in attrs), image))
        if dict(attrs) != src:
            attr_bad += 1
        svgH.append(kec(svg)); jsonH.append(kec(j))

    json.dump({"count": M["count"], "svgHash": svgH, "jsonHash": jsonH},
              open(os.path.join(fix_dir, "summer.json"), "w"))
    print(f"summer: {M['count']} tokens | image-exact:{M['count']-img_bad}/{M['count']} "
          f"attrs-exact:{M['count']-attr_bad}/{M['count']} {'OK' if img_bad==0 and attr_bad==0 else 'FAIL'}")
    sys.exit(0 if img_bad == 0 and attr_bad == 0 else 1)


if __name__ == "__main__":
    main()
