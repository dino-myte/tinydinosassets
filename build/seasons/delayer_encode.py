"""Option B encoder: de-layer summer into shared trait sprites + per-token
correction tables, like the genesis collection but with a small correction
overlay for the art's alpha-blended trait edges.

Pipeline:
  1. de-layer all 10,001 images into (category,value) sprites (unanimous vote ->
     0 wrong colors, some gaps)
  2. per token: composite its trait sprites in layer order, diff vs source ->
     corrections (pixel, color); 1/1 tokens (no visual traits) become all-correction
  3. verify reconstruction == source for every token
  4. report sprite count, correction stats, total on-chain size / cost

This run only validates + measures the model (no blob writing yet).
"""
import json
import os
import sys
from collections import Counter, defaultdict

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from encoding import encode_sprite  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
IMG = os.path.join(ROOT, "images", "seasons", "summer", "1600x1600")
META = os.path.join(ROOT, "metadata", "seasons", "summer")
ORDER = ["background", "body", "spikes", "chest", "feet", "hands", "head", "face", "eyes"]
TRANS = (0, 0, 0, 0)


def grid(tid):
    im = Image.open(os.path.join(IMG, f"{tid}.png")).convert("RGBA")
    w, h = im.size
    cw, ch = w // 16, h // 16
    p = im.load()
    return [p[sx * cw + cw // 2, sy * ch + ch // 2] for sy in range(16) for sx in range(16)]


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

    # de-layer top-down, unanimous (0 wrong colors)
    print("de-layering...", flush=True)
    sprites = {}
    covered = {t: [False] * 256 for t in tr}
    for c in reversed(ORDER):
        for v, toks in by[c].items():
            sp = [None] * 256
            for p in range(256):
                color = None
                ok = True
                seen = False
                for t in toks:
                    if covered[t][p]:
                        continue
                    seen = True
                    cpx = im[t][p]
                    if color is None:
                        color = cpx
                    elif cpx != color:
                        ok = False
                        break
                if seen and ok:
                    sp[p] = color
            sprites[(c, v)] = sp
        for t in tr:
            v = tr[t].get(c)
            if v is None:
                continue
            sp = sprites[(c, v)]
            for p in range(256):
                if sp[p] is not None:
                    covered[t][p] = True

    # composite + corrections per token; verify exact
    print("compositing + corrections...", flush=True)
    corr_counts = []
    corr_colors = Counter()
    bad = 0
    n_unique = 0
    for tid in tr:
        visual = [c for c in ORDER if c in tr[tid]]
        canvas = [None] * 256
        for c in visual:
            sp = sprites[(c, tr[tid][c])]
            for p in range(256):
                if sp[p] is not None:
                    canvas[p] = sp[p]
        if not visual:
            n_unique += 1
        corr = [(p, im[tid][p]) for p in range(256) if canvas[p] != im[tid][p]]
        corr_counts.append(len(corr))
        for _, col in corr:
            corr_colors[col] += 1
        # verify: composite + corrections == source
        recon = list(canvas)
        for p, col in corr:
            recon[p] = col
        recon = [TRANS if x is None else x for x in recon]
        if recon != im[tid]:
            bad += 1

    import statistics
    # sprite storage
    spr_bytes = sum(len(encode_sprite([TRANS if x is None else x for x in sprites[k]])) for k in sprites)
    n_corr_colors = len(corr_colors)
    color_id_bytes = 1 if n_corr_colors <= 256 else 2
    palette_bytes = n_corr_colors * 4
    # per-token record: numSprites(1)+spriteId(1)*visual + numCorr(2) + (pixel1+colorId)*corr
    rec_bytes = 0
    for tid in tr:
        visual = [c for c in ORDER if c in tr[tid]]
        rec_bytes += 1 + len(visual) + 2 + len(corr_counts and [0]) * 0
    rec_bytes = sum(1 + len([c for c in ORDER if c in tr[tid]]) + 2 + corr_counts[i] * (1 + color_id_bytes)
                    for i, tid in enumerate(tr))
    total = spr_bytes + palette_bytes + rec_bytes
    print(f"\nreconstruction: {n - bad}/{n} exact")
    print(f"trait sprites: {len(sprites)}  ({spr_bytes:,}B)")
    print(f"1/1 tokens (all-correction): {n_unique}")
    print(f"corrections: mean {statistics.mean(corr_counts):.1f}px median {statistics.median(corr_counts):.0f} "
          f"max {max(corr_counts)} total {sum(corr_counts):,}")
    print(f"distinct correction colors: {n_corr_colors} (colorId {color_id_bytes}B, palette {palette_bytes:,}B)")
    print(f"per-token records: {rec_bytes:,}B")
    print(f"TOTAL on-chain ~{total:,}B  est Base ~${total*200*0.006e-9*1580:.2f}  (vs 5.3MB/$11)")


if __name__ == "__main__":
    main()
