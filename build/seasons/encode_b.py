"""Option B encoder: emit on-chain blobs for summer = genesis-style composite of
de-layered trait sprites + a per-token correction overlay (for alpha-blended edges).

Layout (build/seasons/out_b/summer/):
  sprites/<i>.bin      sprite chunks (RLE trait sprites, <=24KB, sprite-boundary)
  spriteLoc.bin        per global sprite id: (chunkIdx u16, localOff u16)
  corrPalette.bin      distinct correction colours, RGBA (4B each)
  tokens data/<i>.bin  combined per-token records, chunked (<=24KB)
  tokens loc/<i>.bin    per-token (dataChunkIdx u16, localOff u16), locPerChunk
  cats.txt             9 visual category names (newline)
  vals.txt             per-category value lists, '\\n' within cat, '\\x1f' between cats
  one.txt              1/1 values (newline)
  manifest.json        catBase, paint/alpha order, counts, locPerChunk, nChunks...

Per-token record:
  [flag u8]  0 = composite, 1 = 1/1
  composite: [localValIdx u8]*9   (category order = ORDER)
  1/1:       [oneIdx u8]
  [numCorr u16-BE] then (pixel u8, colorId u16-BE)*numCorr
"""
import json
import os
import struct
import sys
from collections import Counter, defaultdict

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from encoding import decode_sprite, encode_sprite  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
IMG = os.path.join(ROOT, "images", "seasons", "summer", "1600x1600")
META = os.path.join(ROOT, "metadata", "seasons", "summer")
OUT = os.path.join(HERE, "out_b", "summer")
ORDER = ["background", "body", "spikes", "chest", "feet", "hands", "head", "face", "eyes"]
ALPHA = sorted(ORDER)
DISP = "tiny dinos: summer 2022"
DESC = "one of 10k tiny dinos ready for summer vibes"
TRANS = (0, 0, 0, 0)
US = "\x1f"


def grid(tid):
    im = Image.open(os.path.join(IMG, f"{tid}.png")).convert("RGBA")
    w, h = im.size
    cw, ch = w // 16, h // 16
    p = im.load()
    return [p[sx * cw + cw // 2, sy * ch + ch // 2] for sy in range(16) for sx in range(16)]


def chunk_at_boundaries(items, cap=24000):
    """items: list of bytes. Returns (chunks, loc[(chunkIdx,localOff)])."""
    chunks, loc, cur = [], [], bytearray()
    for b in items:
        assert len(b) <= cap
        if cur and len(cur) + len(b) > cap:
            chunks.append(bytes(cur)); cur = bytearray()
        loc.append((len(chunks), len(cur)))
        cur += b
    if cur:
        chunks.append(bytes(cur))
    return chunks, loc


def main():
    n = int(os.environ.get("N", "10001"))
    print(f"loading {n}...", flush=True)
    tr, im = {}, {}
    for tid in range(1, n + 1):
        m = json.load(open(os.path.join(META, str(tid))))
        tr[tid] = {a["trait_type"]: a["value"] for a in m["attributes"]}
        im[tid] = grid(tid)

    by = defaultdict(lambda: defaultdict(list))
    for tid in tr:
        for c in ORDER:
            if c in tr[tid]:
                by[c][tr[tid][c]].append(tid)

    # de-layer (unanimous, 0 wrong colors)
    print("de-layering...", flush=True)
    sp = {}
    covered = {t: [False] * 256 for t in tr}
    for c in reversed(ORDER):
        for v, toks in by[c].items():
            s = [None] * 256
            for p in range(256):
                col, ok, seen = None, True, False
                for t in toks:
                    if covered[t][p]:
                        continue
                    seen = True
                    if col is None:
                        col = im[t][p]
                    elif im[t][p] != col:
                        ok = False
                        break
                if seen and ok:
                    s[p] = col
            sp[(c, v)] = s
        for t in tr:
            v = tr[t].get(c)
            if v is None:
                continue
            for p in range(256):
                if sp[(c, v)][p] is not None:
                    covered[t][p] = True

    # value dictionaries per category + global sprite ids (catBase + localIdx)
    values = {c: sorted(by[c].keys()) for c in ORDER}
    cat_base, gid = {}, 0
    sprite_list = []  # global sprite id -> sprite (256 px, None=transparent)
    for c in ORDER:
        cat_base[c] = gid
        for v in values[c]:
            sprite_list.append([TRANS if x is None else x for x in sp[(c, v)]])
            gid += 1
    one_vals = sorted({tr[t]["1/1"] for t in tr if "1/1" in tr[t]})
    one_idx = {v: i for i, v in enumerate(one_vals)}

    # per token: composite + corrections + record
    print("compositing + records...", flush=True)
    corr_palette, corr_pid = [], {}
    def cpid(col):
        if col not in corr_pid:
            corr_pid[col] = len(corr_palette); corr_palette.append(col)
        return corr_pid[col]

    records = []
    for tid in tr:
        visual = [c for c in ORDER if c in tr[tid]]
        canvas = [None] * 256
        rec = bytearray()
        if visual:
            rec.append(0)
            for c in ORDER:
                vi = values[c].index(tr[tid][c])
                assert vi < 256
                rec.append(vi)
            for c in ORDER:  # paint in ORDER (bottom->top)
                s = sprite_list[cat_base[c] + values[c].index(tr[tid][c])]
                for p in range(256):
                    if s[p] != TRANS:
                        canvas[p] = s[p]
        else:
            rec.append(1)
            rec.append(one_idx[tr[tid]["1/1"]])
        corr = [(p, im[tid][p]) for p in range(256) if canvas[p] != im[tid][p]]
        rec += struct.pack(">H", len(corr))
        for p, col in corr:
            rec += struct.pack(">BH", p, cpid(col))
        records.append(bytes(rec))

    assert len(corr_palette) < 65536
    assert max((cat_base[c] + len(values[c]) for c in ORDER)) < 65536

    # sprites -> chunks (sprite boundary) + spriteLoc
    spr_bytes = [encode_sprite(s) for s in sprite_list]
    spr_chunks, spr_loc = chunk_at_boundaries(spr_bytes)
    # token records -> chunks + loc
    dchunks, dloc = chunk_at_boundaries(records)
    LOC_PER = 6000

    os.makedirs(OUT, exist_ok=True)
    for sub in ("sprites", "data", "loc"):
        d = os.path.join(OUT, sub); os.makedirs(d, exist_ok=True)
        for fn in os.listdir(d):
            os.remove(os.path.join(d, fn))
    for i, c in enumerate(spr_chunks):
        open(os.path.join(OUT, "sprites", f"{i:04d}.bin"), "wb").write(c)
    with open(os.path.join(OUT, "spriteLoc.bin"), "wb") as f:
        for ci, lo in spr_loc:
            f.write(struct.pack(">HH", ci, lo))
    for i, c in enumerate(dchunks):
        open(os.path.join(OUT, "data", f"{i:04d}.bin"), "wb").write(c)
    locb = b"".join(struct.pack(">HH", ci, lo) for ci, lo in dloc)
    for i in range(0, len(locb), LOC_PER * 4):
        open(os.path.join(OUT, "loc", f"{i // (LOC_PER * 4):04d}.bin"), "wb").write(locb[i:i + LOC_PER * 4])
    with open(os.path.join(OUT, "corrPalette.bin"), "wb") as f:
        for (r, g, b, a) in corr_palette:
            f.write(bytes((r, g, b, a)))
    open(os.path.join(OUT, "cats.txt"), "w").write("\n".join(ORDER))
    open(os.path.join(OUT, "vals.txt"), "w").write(US.join("\n".join(values[c]) for c in ORDER))
    open(os.path.join(OUT, "one.txt"), "w").write("\n".join(one_vals))

    manifest = {
        "displayName": DISP, "description": DESC, "count": len(tr),
        "catBase": [cat_base[c] for c in ORDER], "catCount": [len(values[c]) for c in ORDER],
        "order": ORDER, "alpha": ALPHA,
        "alphaIdx": [ORDER.index(c) for c in ALPHA],
        "nSprites": len(sprite_list), "nSpriteChunks": len(spr_chunks),
        "nDataChunks": len(dchunks), "nLocChunks": (len(locb) + LOC_PER * 4 - 1) // (LOC_PER * 4),
        "locPerChunk": LOC_PER, "nCorrColors": len(corr_palette), "nOne": len(one_vals),
    }
    json.dump(manifest, open(os.path.join(OUT, "manifest.json"), "w"), indent=2)

    # self-verify: decode like the renderer will, reconstruct, compare to source
    print("self-verify...", flush=True)
    spr_decoded = [decode_sprite(spr_chunks[ci], lo)[0] for ci, lo in spr_loc]
    bad = 0
    for i, tid in enumerate(tr):
        ci, lo = dloc[i]
        rec = dchunks[ci]
        o = lo
        flag = rec[o]; o += 1
        canvas = [TRANS] * 256
        if flag == 0:
            vidx = list(rec[o:o + 9]); o += 9
            for c in ORDER:
                s = spr_decoded[manifest["catBase"][ORDER.index(c)] + vidx[ORDER.index(c)]]
                for p in range(256):
                    if s[p] != TRANS:
                        canvas[p] = s[p]
        else:
            o += 1
        nc = struct.unpack(">H", rec[o:o + 2])[0]; o += 2
        for _ in range(nc):
            p, cid = struct.unpack(">BH", rec[o:o + 3]); o += 3
            canvas[p] = corr_palette[cid]
        if canvas != im[tid]:
            bad += 1

    total = sum(len(c) for c in spr_chunks) + sum(len(c) for c in dchunks) + len(locb) + len(corr_palette) * 4
    print(f"\nself-verify reconstruction: {len(tr)-bad}/{len(tr)} exact")
    print(f"sprites {len(sprite_list)} in {len(spr_chunks)} chunks, data {len(dchunks)} chunks, "
          f"corr colors {len(corr_palette)}, 1/1 {len(one_vals)}")
    print(f"TOTAL ~{total:,}B  est Base ~${total*200*0.006e-9*1580:.2f}")


if __name__ == "__main__":
    main()
