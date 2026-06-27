"""Shared encoding logic: trait/value/order/chain id assignment, sprite RLE codec.

Both extract.py (writes blobs) and reference_render.py (decodes blobs and
verifies) import from here so the encoder and the reference decoder can never
drift apart.
"""
import collections
import json
import os

from common import (CHAINS, ROOT, VIS, is_unique, load_meta, load_original,
                    load_sprite, px_list)

# Attribute output order in the original metadata: visual cats alphabetical, then "minted on".
ATTR_ORDER = sorted(VIS)  # ['background','body','chest','eyes','face','feet','hands','head','spikes']

# Per-category packed bit widths for the token record (must hold the largest local value id).
WIDTHS = {
    "background": 5, "body": 5, "spikes": 4, "chest": 4, "feet": 2,
    "hands": 2, "head": 4, "face": 3, "eyes": 4,
}

ORDERS_JSON = os.path.join(ROOT, "build", "orders.json")
OUT_DIR = os.path.join(ROOT, "build", "out")


def build_dictionaries():
    """Scan metadata once and assign stable (sorted) ids for every label/order.

    Returns a dict with:
      values[cat]      -> sorted list of trait values (index = local value id)
      cat_base[cat]    -> global sprite index where this category's sprites start
      n_composite      -> number of composite (trait) sprites
      mintons          -> sorted list of `minted on` values (id = index)
      oneofones        -> sorted list of `1/1` values (id = index)
      orders           -> sorted list of distinct render orders (id = index),
                          each a tuple of category names bottom->top
      unique_tokens    -> sorted list of unique token ids (uniqueImageId = index)
      order_of[tok]    -> order id for each non-unique token
    """
    orders_raw = {int(k): v for k, v in json.load(open(ORDERS_JSON)).items()}

    values = {c: set() for c in VIS}
    mintons, oneofones, unique_tokens = set(), set(), []
    distinct_orders = set()
    order_of = {}

    for tok in range(1, 10001):
        _, attrs = load_meta(tok)
        mintons.add(attrs["minted on"])
        if is_unique(attrs):
            oneofones.add(attrs["1/1"])
            unique_tokens.append(tok)
            continue
        for c in VIS:
            values[c].add(attrs[c])
        o = tuple(orders_raw[tok])
        distinct_orders.add(o)
        order_of[tok] = o

    values = {c: sorted(v) for c, v in values.items()}
    orders = sorted(distinct_orders)
    order_id = {o: i for i, o in enumerate(orders)}

    cat_base, n = {}, 0
    for c in VIS:
        cat_base[c] = n
        n += len(values[c])

    return {
        "values": values,
        "cat_base": cat_base,
        "n_composite": n,
        "mintons": sorted(mintons),
        "oneofones": sorted(oneofones),
        "orders": orders,
        "unique_tokens": sorted(unique_tokens),
        "order_of": {t: order_id[o] for t, o in order_of.items()},
    }


# ---------------------------------------------------------------------------
# Sprite RLE codec
#   byte[0]              = palette length P (0 means 256)
#   next P*4 bytes       = palette entries R,G,B,A
#   then RLE runs        = repeated (count 1..255, paletteIndex) covering 256 px
# ---------------------------------------------------------------------------

def encode_sprite(pixels):
    """pixels: 256 (r,g,b,a) tuples (row-major). Returns bytes."""
    palette = []
    pal_index = {}
    for p in pixels:
        if p not in pal_index:
            pal_index[p] = len(palette)
            palette.append(p)
    assert len(palette) <= 256, "palette too large for 16x16 sprite"

    out = bytearray()
    out.append(len(palette) & 0xFF)  # 256 -> 0
    for (r, g, b, a) in palette:
        out += bytes((r, g, b, a))

    i = 0
    while i < 256:
        j = i
        idx = pal_index[pixels[i]]
        while j < 256 and pal_index[pixels[j]] == idx and (j - i) < 255:
            j += 1
        out.append(j - i)  # run length 1..255
        out.append(idx)
        i = j
    return bytes(out)


def decode_sprite(blob, off=0):
    """Inverse of encode_sprite. Returns (pixels[256], bytes_consumed)."""
    p = blob[off]
    plen = 256 if p == 0 else p
    o = off + 1
    palette = []
    for _ in range(plen):
        palette.append((blob[o], blob[o + 1], blob[o + 2], blob[o + 3]))
        o += 4
    pixels = []
    while len(pixels) < 256:
        count = blob[o]
        idx = blob[o + 1]
        o += 2
        pixels.extend([palette[idx]] * count)
    assert len(pixels) == 256
    return pixels, o - off


def sprite_pixels_for(d, category, value):
    return px_list(load_sprite(category, value))


def unique_pixels_for(tok):
    return px_list(load_original(tok))
