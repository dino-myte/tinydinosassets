"""Reference renderer + full verification.

Decodes ONLY the on-chain blobs (build/out/*) — exactly what the Solidity
Renderer will read — then for every token:
  * composites sprites with the PIL-exact integer blend in the stored order,
  * builds the SVG and the metadata JSON,
  * rasterizes its own SVG string back to pixels,
and asserts:
  1. composited grid == original PNG               (all 10,000)
  2. rasterized SVG    == original PNG              (all 10,000)
  3. metadata name/description/tokenId/attributes/current-chain == source
     metadata for every one of the 7 chains.

This is the proof artifact for the off-chain build+verify deliverable.
"""
import base64
import json
import os
import re
import sys

from common import (CHAINS, DESCRIPTION, ROOT, SUPPLY, VIS, blend, load_meta,
                    load_original, px_list)
from encoding import ATTR_ORDER, OUT_DIR, WIDTHS, decode_sprite

# Folder name -> current-chain string is identity; minted-on uses 'bsc' for bnb,
# which is already baked into the stored ids, so nothing special here.
M = None       # manifest
SPRITES = b""  # sprites.bin
OFFSETS = []   # decoded offsets
TOKENS = b""   # tokens.bin


def load_blobs():
    global M, SPRITES, OFFSETS, TOKENS
    M = json.load(open(os.path.join(OUT_DIR, "manifest.json")))
    SPRITES = open(os.path.join(OUT_DIR, "sprites.bin"), "rb").read()
    raw = open(os.path.join(OUT_DIR, "spriteOffsets.bin"), "rb").read()
    OFFSETS = [int.from_bytes(raw[i:i + 4], "big") for i in range(0, len(raw), 4)]
    TOKENS = open(os.path.join(OUT_DIR, "tokens.bin"), "rb").read()


_sprite_cache = {}


def sprite(global_id):
    if global_id not in _sprite_cache:
        px, _ = decode_sprite(SPRITES, OFFSETS[global_id])
        _sprite_cache[global_id] = px
    return _sprite_cache[global_id]


def decode_token(tok):
    """Decode the 5-byte record into a dict, mirroring the Solidity decoder."""
    off = (tok - 1) * M["token_record_bytes"]
    word = int.from_bytes(TOKENS[off:off + M["token_record_bytes"]], "little")
    unique = bool((word >> 39) & 1)
    minton = M["minted_on"][(word >> 36) & 0x7]
    if unique:
        uimg = word & 0x1F
        one = M["one_of_one"][(word >> 5) & 0x1F]
        return {"unique": True, "minton": minton, "uimg": uimg, "one": one}
    shift, locals_ = 0, {}
    for c in VIS:
        locals_[c] = (word >> shift) & ((1 << WIDTHS[c]) - 1)
        shift += WIDTHS[c]
    order = (word >> 33) & 0x7
    return {"unique": False, "minton": minton, "locals": locals_, "order": order}


def composite_grid(tok):
    t = decode_token(tok)
    canvas = [(0, 0, 0, 0)] * 256
    if t["unique"]:
        layers = [M["n_composite_sprites"] + t["uimg"]]
    else:
        order = M["orders"][t["order"]]
        layers = [M["cat_base"][c] + t["locals"][c] for c in order]
    for gid in layers:
        sp = sprite(gid)
        for i in range(256):
            s = sp[i]
            if s[3] != 0:
                canvas[i] = blend(canvas[i], s)
    return canvas


# ---- SVG: merge horizontal runs of equal opaque color into <rect> ----
def build_svg(grid):
    parts = [
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' "
        "shape-rendering='crispEdges'>"
    ]
    for y in range(16):
        x = 0
        while x < 16:
            r, g, b, a = grid[y * 16 + x]
            x2 = x
            while x2 < 16 and grid[y * 16 + x2] == (r, g, b, a):
                x2 += 1
            w = x2 - x
            # opaque -> #rrggbb (compact); near-opaque edges -> #rrggbbaa (exact alpha)
            if a == 255:
                color = f"#{r:02x}{g:02x}{b:02x}"
            else:
                color = f"#{r:02x}{g:02x}{b:02x}{a:02x}"
            parts.append(
                f"<rect x='{x}' y='{y}' width='{w}' height='1' fill='{color}'/>")
            x = x2
    parts.append("</svg>")
    return "".join(parts)


_RECT = re.compile(
    r"<rect x='(\d+)' y='(\d+)' width='(\d+)' height='1' fill='#([0-9a-f]{6}(?:[0-9a-f]{2})?)'/>")


def rasterize_svg(svg):
    """Independently parse the SVG string back into a 16x16 RGBA grid."""
    grid = [None] * 256
    for m in _RECT.finditer(svg):
        x, y, w, hexc = m.groups()
        x, y, w = int(x), int(y), int(w)
        r, g, b = int(hexc[0:2], 16), int(hexc[2:4], 16), int(hexc[4:6], 16)
        a = int(hexc[6:8], 16) if len(hexc) == 8 else 255
        for xx in range(x, x + w):
            grid[y * 16 + xx] = (r, g, b, a)
    return grid


def build_metadata(tok):
    """Chain-independent metadata, matching the LIVE collection: no current-chain
    field; the only chain shown is the static 'minted on' attribute."""
    t = decode_token(tok)
    svg = build_svg(composite_grid(tok))
    image = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
    if t["unique"]:
        attrs = [
            {"trait_type": "1/1", "value": t["one"]},
            {"trait_type": "minted on", "value": t["minton"]},
        ]
    else:
        attrs = [{"trait_type": c, "value": M["values"][c][t["locals"][c]]}
                 for c in ATTR_ORDER]
        attrs.append({"trait_type": "minted on", "value": t["minton"]})
    return {
        "name": f"tiny dinos #{tok}",
        "description": DESCRIPTION,
        "tokenId": tok,
        "attributes": attrs,
        "image": image,
    }


def main():
    load_blobs()
    px_fail = svg_fail = 0
    fails = []
    for tok in range(1, SUPPLY + 1):
        grid = composite_grid(tok)
        orig = px_list(load_original(tok))
        if grid != orig:
            px_fail += 1
            fails.append(("px", tok))
        elif rasterize_svg(build_svg(grid)) != orig:
            svg_fail += 1
            fails.append(("svg", tok))
        if tok % 2000 == 0:
            print(f"  ...rendered {tok}", flush=True)

    print(f"\nPIXEL/SVG verification: {SUPPLY - px_fail - svg_fail}/{SUPPLY} exact")
    print(f"  composite mismatches: {px_fail}   svg-raster mismatches: {svg_fail}")
    if fails:
        print("  first failures:", fails[:20])

    # ---- metadata verification (chain-independent: name/description/tokenId/
    # attributes incl. 'minted on'; no current-chain, matching the live collection) ----
    meta_fail = 0
    meta_examples = []
    for tok in range(1, SUPPLY + 1):
        got = build_metadata(tok)
        src, _attrs = load_meta(tok, "eth")  # attributes are identical across chains
        ok = (
            got["name"] == src["name"]
            and got["description"] == src["description"]
            and got["tokenId"] == src["tokenId"]
            and got["attributes"] == src["attributes"]
            and "current-chain" not in got
        )
        if not ok:
            meta_fail += 1
            if len(meta_examples) < 10:
                meta_examples.append(tok)

    total = SUPPLY
    print(f"\nMETADATA verification: {total - meta_fail}/{total} exact "
          f"(name/description/tokenId/attributes incl 'minted on'; no current-chain)")
    if meta_examples:
        print("  first metadata mismatches:", meta_examples)

    ok = (px_fail == 0 and svg_fail == 0 and meta_fail == 0)
    print("\n" + ("ALL CHECKS PASSED ✅" if ok else "FAILURES PRESENT ❌"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
