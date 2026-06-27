"""Shared constants, asset loading, and the PIL-exact integer source-over blend.

The integer `blend()` below reproduces Pillow's `Image.alpha_composite` bit-for-bit
(verified 0 mismatches over 500k random pairs). The Solidity Renderer mirrors this
exact formula so on-chain output matches the original PNGs pixel-for-pixel.
"""
import json
import os
from functools import lru_cache

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Visual trait categories in canonical metadata order.
VIS = ["background", "body", "spikes", "chest", "feet", "hands", "head", "face", "eyes"]
CAT_INDEX = {c: i for i, c in enumerate(VIS)}

# The 7 chains the collection was minted across (the `minted on` attribute).
CHAINS = ["eth", "avax", "bnb", "poly", "arb", "ftm", "opt"]

DESCRIPTION = "one of 10k cc0 tiny dinos minted out across 7 different chains"
SUPPLY = 10000

# Canonical source = the 1600x1600 PNGs. These are pixel-identical to the minted
# IPFS images and are blocky (every 100x100 cell is one solid color), so they are
# really 16x16-grid images at 100x scale. We downsample them to the 16x16 grid.
# (The repo's own images/.../16x16 PNGs differ by +/-1 per channel on ~9,795
# tokens and by more on 205 snow/night-landscape tokens, so they are NOT used as
# the source of truth — only 1600x1600 is.)
TRAIT_DIR = os.path.join(ROOT, "images", "traits", "1600x1600")
DINO_DIR = os.path.join(ROOT, "images", "dinos", "1600x1600", "original")

# The repo's 16x16 PNGs, kept only for comparison/reporting (not as source).
TRAIT_DIR_16 = os.path.join(ROOT, "images", "traits", "16x16")
DINO_DIR_16 = os.path.join(ROOT, "images", "dinos", "16x16", "original")


def meta_path(chain, tok):
    return os.path.join(ROOT, "metadata", chain, str(tok))


def load_meta(tok, chain="eth"):
    with open(meta_path(chain, tok)) as f:
        d = json.load(f)
    attrs = {a["trait_type"]: a["value"] for a in d["attributes"]}
    return d, attrs


def is_unique(attrs):
    return "1/1" in attrs


def _downsample16(path):
    """Downsample a blocky 1600x1600 PNG to its 16x16 grid (one color per cell)."""
    src = Image.open(path).convert("RGBA").load()
    out = Image.new("RGBA", (16, 16))
    op = out.load()
    for sy in range(16):
        for sx in range(16):
            op[sx, sy] = src[sx * 100 + 50, sy * 100 + 50]
    return out


@lru_cache(maxsize=None)
def load_sprite(category, value):
    return _downsample16(os.path.join(TRAIT_DIR, category, value + ".png"))


@lru_cache(maxsize=None)
def load_original(tok):
    return _downsample16(os.path.join(DINO_DIR, f"{tok}.png"))


def px_list(im):
    return list(im.getdata())


# ---- PIL-exact integer source-over (mirrors Pillow AlphaComposite.c, PRECISION_BITS=7) ----
_PB = 7


def _div255(a):
    return (((a >> 8) + a) >> 8)


def blend(dst, src):
    """Composite src over dst. dst/src are (r,g,b,a) 0..255. Returns (r,g,b,a)."""
    in2a = src[3]
    if in2a == 0:
        return dst
    if in2a == 255:
        return src
    in1a = dst[3]
    blend_ = in1a * (255 - in2a)
    outa255 = in2a * 255 + blend_
    coef1 = in2a * 255 * 255 * (1 << _PB) // outa255
    coef2 = 255 * (1 << _PB) - coef1
    out = []
    for i in range(3):
        tmp = src[i] * coef1 + dst[i] * coef2
        out.append(_div255(tmp + (0x80 << _PB)) >> _PB)
    oa = _div255(outa255 + 0x80)
    return (out[0], out[1], out[2], oa)


def composite_pixels(sprite_px_layers):
    """sprite_px_layers: list of 256-length pixel lists, bottom->top. Returns 256 pixels."""
    canvas = [(0, 0, 0, 0)] * 256
    for layer in sprite_px_layers:
        for i in range(256):
            s = layer[i]
            if s[3] != 0:
                canvas[i] = blend(canvas[i], s)
    return canvas
