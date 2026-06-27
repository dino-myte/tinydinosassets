"""Encode the whole collection into deploy-ready on-chain blobs + a manifest.

Outputs (build/out/):
  sprites.bin        concatenated RLE sprites: composite sprites in global-id
                     order, then the 15 unique flattened images.
  spriteOffsets.bin  (n_sprites+1) uint32-BE start offsets into sprites.bin.
  tokens.bin         10000 * 5-byte packed token records.
  manifest.json      everything the Renderer/test needs: id maps, cat bases,
                     order table, label strings, byte layout.

Run order: solve_orders.py first (produces orders.json), then this.
"""
import json
import os
import struct

from common import VIS
from encoding import (ATTR_ORDER, OUT_DIR, WIDTHS, build_dictionaries,
                      decode_sprite, encode_sprite, sprite_pixels_for,
                      unique_pixels_for)

ORDER_BITS, MINTON_BITS = 3, 3
TOKEN_BYTES = 5  # 40 bits


def pack_token(fields):
    """fields: dict with category->localId, 'order', 'minton', 'unique',
    and for uniques 'uimg','one'. Returns 5 little-endian bytes."""
    word = 0
    shift = 0
    if fields["unique"]:
        word |= (fields["uimg"] & 0x1F) << shift  # reuse background slot (5b)
        shift += WIDTHS["background"]
        word |= (fields["one"] & 0x1F) << shift   # reuse body slot (5b)
        shift = 33
    else:
        for c in VIS:
            word |= (fields[c] & ((1 << WIDTHS[c]) - 1)) << shift
            shift += WIDTHS[c]
        assert shift == 33, shift
        word |= (fields["order"] & 0x7) << shift
        shift += ORDER_BITS
    # minton + unique flag occupy fixed positions regardless of branch
    word |= (fields["minton"] & 0x7) << 36
    if fields["unique"]:
        word |= 1 << 39
    return word.to_bytes(TOKEN_BYTES, "little")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    d = build_dictionaries()
    values, cat_base = d["values"], d["cat_base"]
    mintons, oneofones = d["mintons"], d["oneofones"]
    orders, unique_tokens = d["orders"], d["unique_tokens"]
    n_composite = d["n_composite"]

    minton_id = {v: i for i, v in enumerate(mintons)}
    one_id = {v: i for i, v in enumerate(oneofones)}
    uimg_id = {t: i for i, t in enumerate(unique_tokens)}

    # ---- sprite blob: composite sprites (global-id order) then unique images ----
    sprites = bytearray()
    offsets = [0]
    for c in VIS:
        for v in values[c]:
            sprites += encode_sprite(sprite_pixels_for(d, c, v))
            offsets.append(len(sprites))
    for t in unique_tokens:
        sprites += encode_sprite(unique_pixels_for(t))
        offsets.append(len(sprites))
    n_sprites = len(offsets) - 1
    assert n_sprites == n_composite + len(unique_tokens)

    # round-trip self-check of the codec
    for i in range(n_sprites):
        px, _ = decode_sprite(bytes(sprites), offsets[i])
        assert len(px) == 256

    # ---- token records ----
    from common import load_meta, is_unique
    order_of = d["order_of"]
    tokens = bytearray()
    for tok in range(1, 10001):
        _, attrs = load_meta(tok)
        if is_unique(attrs):
            f = {"unique": True, "uimg": uimg_id[tok], "one": one_id[attrs["1/1"]],
                 "minton": minton_id[attrs["minted on"]]}
        else:
            f = {"unique": False, "order": order_of[tok],
                 "minton": minton_id[attrs["minted on"]]}
            for c in VIS:
                f[c] = values[c].index(attrs[c])
        tokens += pack_token(f)
    assert len(tokens) == 10000 * TOKEN_BYTES

    # ---- write blobs ----
    with open(os.path.join(OUT_DIR, "sprites.bin"), "wb") as fh:
        fh.write(sprites)
    with open(os.path.join(OUT_DIR, "spriteOffsets.bin"), "wb") as fh:
        for o in offsets:
            fh.write(struct.pack(">I", o))
    with open(os.path.join(OUT_DIR, "tokens.bin"), "wb") as fh:
        fh.write(tokens)

    manifest = {
        "supply": 10000,
        "n_composite_sprites": n_composite,
        "n_unique_sprites": len(unique_tokens),
        "n_sprites": n_sprites,
        "cat_order": VIS,
        "attr_order": ATTR_ORDER,
        "widths": WIDTHS,
        "cat_base": cat_base,
        "values": values,
        "minted_on": mintons,
        "one_of_one": oneofones,
        "unique_tokens": unique_tokens,
        "orders": [list(o) for o in orders],
        "token_record_bytes": TOKEN_BYTES,
        "sprites_bytes": len(sprites),
        "sizes": {
            "sprites.bin": len(sprites),
            "spriteOffsets.bin": len(offsets) * 4,
            "tokens.bin": len(tokens),
        },
    }
    with open(os.path.join(OUT_DIR, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)

    print("=== extract complete ===")
    print(f"  composite sprites : {n_composite}")
    print(f"  unique sprites    : {len(unique_tokens)}")
    print(f"  sprites.bin       : {len(sprites):,} bytes")
    print(f"  spriteOffsets.bin : {len(offsets) * 4:,} bytes")
    print(f"  tokens.bin        : {len(tokens):,} bytes")
    print(f"  total on-chain    : {len(sprites) + len(offsets) * 4 + len(tokens):,} bytes")
    print(f"  distinct orders   : {len(orders)}")
    print(f"  wrote manifest + blobs to {OUT_DIR}")


if __name__ == "__main__":
    main()
