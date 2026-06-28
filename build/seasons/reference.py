"""Reference decoder/verifier for the seasonal blobs (combined-chunked design).

Decodes ONLY the on-chain blobs (build/seasons/out/<name>) the way the Solidity
SeasonalRenderer will, builds each token's SVG + metadata JSON, and asserts the
SVG rasterises to the source 16x16 image and the attributes match. Emits Foundry
fixtures (keccak hashes).
"""
import base64
import json
import os
import re
import struct
import sys

from Crypto.Hash import keccak

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from encoding import decode_sprite  # noqa: E402
from encode import load_collection  # noqa: E402

OUT = os.path.join(HERE, "out")
RECT = re.compile(r"<rect x='(\d+)' y='(\d+)' width='(\d+)' height='1' fill='#([0-9a-f]{6}(?:[0-9a-f]{2})?)'/>")


def build_svg(grid):
    parts = ["<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' shape-rendering='crispEdges'>"]
    for y in range(16):
        x = 0
        while x < 16:
            c = grid[y * 16 + x]
            x2 = x
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


def kec(s):
    h = keccak.new(digest_bits=256)
    h.update(s.encode())
    return "0x" + h.hexdigest()


def load(name):
    d = os.path.join(OUT, name)
    M = json.load(open(os.path.join(d, "manifest.json")))
    dchunks = [open(os.path.join(d, "data", f"{i:04d}.bin"), "rb").read() for i in range(M["nDataChunks"])]
    loc = b"".join(open(os.path.join(d, "loc", f"{i:04d}.bin"), "rb").read() for i in range(M["nLocChunks"]))
    cats = open(os.path.join(d, "cats.txt")).read().split("\n")
    vals = open(os.path.join(d, "vals.txt")).read().split("\n")
    return M, dchunks, loc, cats, vals


def token(M, dchunks, loc, cats, vals, idx):
    tid = idx + 1
    ci, lo = struct.unpack(">HH", loc[idx * 4:idx * 4 + 4])
    data = dchunks[ci]
    n = data[lo]
    o = lo + 1
    attrs = []
    for _ in range(n):
        cidx = data[o]
        vidx = struct.unpack(">H", data[o + 1:o + 3])[0]
        o += 3
        attrs.append((cats[cidx], vals[vidx]))
    grid, _ = decode_sprite(data, o)
    svg = build_svg(grid)
    image = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
    j = ('{"name":"%s #%d","description":"%s","tokenId":%d,"attributes":[%s],"image":"%s"}'
         % (M["displayName"], tid, M["description"], tid,
            ",".join('{"trait_type":"%s","value":"%s"}' % (t, v) for t, v in attrs), image))
    return tid, svg, j, dict(attrs)


def main():
    fix_dir = os.path.join(os.path.dirname(os.path.dirname(HERE)), "contracts", "test", "fixtures", "seasons")
    os.makedirs(fix_dir, exist_ok=True)
    allok = True
    for name in os.environ.get("SEASONS", "summer").split(","):
        if not os.path.isdir(os.path.join(OUT, name)):
            continue
        M, dchunks, loc, cats, vals = load(name)
        toks, image16 = load_collection(name)
        src = {t["id"]: t["attrs"] for t in toks}
        img_bad = attr_bad = 0
        svgH, jsonH = [], []
        for idx in range(M["count"]):
            tid, svg, j, attrs = token(M, dchunks, loc, cats, vals, idx)
            if raster(svg) != image16(tid):
                img_bad += 1
            if attrs != src[tid]:
                attr_bad += 1
            svgH.append(kec(svg)); jsonH.append(kec(j))
        json.dump({"count": M["count"], "svgHash": svgH, "jsonHash": jsonH},
                  open(os.path.join(fix_dir, f"{name}.json"), "w"))
        ok = img_bad == 0 and attr_bad == 0
        allok &= ok
        print(f"{name}: {M['count']} tokens | image-exact:{M['count']-img_bad}/{M['count']} "
              f"attrs-exact:{M['count']-attr_bad}/{M['count']} {'OK' if ok else 'FAIL'}")
    print("ALL SEASONAL CHECKS PASSED" if allok else "FAILURES")
    sys.exit(0 if allok else 1)


if __name__ == "__main__":
    main()
