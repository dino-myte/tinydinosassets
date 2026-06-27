"""Encode a seasonal collection into on-chain blobs.

Each token: a flattened 16x16 sprite + its attributes + its real token id.
(No compositing — seasonal art is stored per-token as a single sprite.)

Per collection, writes build/seasons/out/<name>/:
  sprites.bin        concatenated RLE sprites (one per token, token-id order)
  spriteOffsets.bin  uint32-BE (N+1) offsets into sprites.bin
  ids.bin            uint16-BE (N) real token ids, ascending
  records.bin        per token: numAttrs(u8) then (catIdx u8, valIdx u16-BE) pairs
  recordOffsets.bin  uint32-BE (N+1) offsets into records.bin
  cats.txt / vals.txt  '\n'-joined trait_type names / values (indexed by the records)
  manifest.json      counts, name, description, byte sizes
"""
import json
import os
import struct
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # build/
from encoding import encode_sprite, decode_sprite  # noqa: E402

DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "out")
ROOT = os.path.dirname(os.path.dirname(HERE))
SUMMER_IMG = os.path.join(ROOT, "images", "seasons", "summer", "1600x1600")
SUMMER_META = os.path.join(ROOT, "metadata", "seasons", "summer")

# visual categories alphabetical, then any specials (e.g. "1/1") appended.
VISUAL = ["background", "body", "chest", "eyes", "face", "feet", "hands", "head", "spikes"]
NAMES = {
    "summer": "tiny dinos: summer 2022",
    "winter": "tiny dinos: winter 2022",
    "halloween": "tiny dinos: halloween 2022",
}
# token-level description, matching the original IPFS metadata
DESCS = {
    "summer": "one of 10k tiny dinos ready for summer vibes",
    "winter": "one of 10k tiny dinos ready for winter vibes",
    "halloween": "one of 10k tiny dinos ready for halloween vibes",
}
EXACT = {"summer": True, "winter": False, "halloween": False}  # winter/halloween are approximations


def attr_order(attrs):
    keys = [c for c in VISUAL if c in attrs]
    keys += [c for c in attrs if c not in VISUAL]  # specials like "1/1"
    return keys


def downsample16(path):
    """Blocky NxN (multiple of 16) -> 16x16 by cell-centre sampling."""
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    cw, ch = w // 16, h // 16
    p = im.load()
    out = []
    for sy in range(16):
        for sx in range(16):
            out.append(p[sx * cw + cw // 2, sy * ch + ch // 2])
    return out


def load_collection(name):
    """Returns (tokens[{id,attrs}], image16_fn). Summer reads the committed raw
    IPFS files (metadata/seasons/summer + images/.../1600x1600); winter/halloween
    read the OpenSea-derived data/<name>/ (tokens.json + img16)."""
    if name == "summer":
        tokens = []
        for fn in os.listdir(SUMMER_META):
            if not fn.isdigit():
                continue
            tid = int(fn)
            if not os.path.exists(os.path.join(SUMMER_IMG, f"{tid}.png")):
                continue
            m = json.load(open(os.path.join(SUMMER_META, fn)))
            tokens.append({"id": tid, "attrs": {a["trait_type"]: a["value"] for a in m["attributes"]}})
        tokens.sort(key=lambda t: t["id"])
        return tokens, lambda tid: downsample16(os.path.join(SUMMER_IMG, f"{tid}.png"))
    ddir = os.path.join(DATA, name)
    tokens = json.load(open(os.path.join(ddir, "tokens.json")))
    tokens.sort(key=lambda t: t["id"])
    img_dir = os.path.join(ddir, "img16")
    tokens = [t for t in tokens if os.path.exists(os.path.join(img_dir, f"{t['id']}.png"))]
    return tokens, lambda tid: list(Image.open(os.path.join(img_dir, f"{tid}.png")).convert("RGBA").getdata())


def main():
    seasons = os.environ.get("SEASONS", "summer").split(",")
    for name in seasons:
        tokens, image16 = load_collection(name)

        # build the cat/val dictionaries
        cats, cat_idx = [], {}
        vals, val_idx = [], {}
        def cat_id(c):
            if c not in cat_idx:
                cat_idx[c] = len(cats); cats.append(c)
            return cat_idx[c]
        def val_id(v):
            if v not in val_idx:
                val_idx[v] = len(vals); vals.append(v)
            return val_idx[v]

        sprites = bytearray(); sp_off = [0]
        records = bytearray(); rec_off = [0]
        ids = []
        for t in tokens:
            tid = t["id"]; ids.append(tid)
            sprites += encode_sprite(image16(tid)); sp_off.append(len(sprites))
            order = attr_order(t["attrs"])
            records.append(len(order))
            for c in order:
                records.append(cat_id(c))
                records += struct.pack(">H", val_id(t["attrs"][c]))
            rec_off.append(len(records))

        assert max(val_idx.values(), default=0) < 65536
        assert max(cat_idx.values(), default=0) < 256
        assert ids == sorted(ids)

        odir = os.path.join(OUT, name)
        os.makedirs(odir, exist_ok=True)
        open(os.path.join(odir, "sprites.bin"), "wb").write(sprites)
        with open(os.path.join(odir, "spriteOffsets.bin"), "wb") as f:
            for o in sp_off: f.write(struct.pack(">I", o))
        with open(os.path.join(odir, "ids.bin"), "wb") as f:
            for i in ids: f.write(struct.pack(">H", i))
        open(os.path.join(odir, "records.bin"), "wb").write(records)
        with open(os.path.join(odir, "recordOffsets.bin"), "wb") as f:
            for o in rec_off: f.write(struct.pack(">I", o))
        open(os.path.join(odir, "cats.txt"), "w").write("\n".join(cats))
        open(os.path.join(odir, "vals.txt"), "w").write("\n".join(vals))

        # codec round-trip self-check
        for i in range(len(ids)):
            decode_sprite(bytes(sprites), sp_off[i])

        manifest = {
            "name": name, "displayName": NAMES[name], "description": DESCS[name],
            "exact": EXACT[name], "count": len(ids),
            "nCats": len(cats), "nVals": len(vals),
            "idRange": [ids[0], ids[-1]] if ids else None,
            "sizes": {"sprites.bin": len(sprites), "records.bin": len(records)},
        }
        json.dump(manifest, open(os.path.join(odir, "manifest.json"), "w"), indent=2)
        print(f"{name}: {len(ids)} tokens, {len(cats)} cats, {len(vals)} vals, "
              f"sprites {len(sprites):,}B, exact={EXACT[name]}")


if __name__ == "__main__":
    main()
