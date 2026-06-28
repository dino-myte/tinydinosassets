"""Feasibility: recover summer trait sprites by de-layering the composited images,
so summer can be rendered by compositing (like genesis) instead of storing 10,001
flattened images.

Summer 16x16 images are opaque composites of 9 trait layers. Given all images +
their trait values, derive each (category,value) sprite top-down: a pixel belongs
to layer k's sprite iff, across all tokens sharing that value where no higher
layer covers the pixel, the source color is constant. Then composite and verify.
"""
import json
import os
import sys
from collections import defaultdict

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
IMG = os.path.join(ROOT, "images", "seasons", "summer", "1600x1600")
META = os.path.join(ROOT, "metadata", "seasons", "summer")

# bottom -> top (genesis-style); refine if needed
ORDER = ["background", "body", "spikes", "chest", "feet", "hands", "head", "face", "eyes"]


def grid16(tid):
    im = Image.open(os.path.join(IMG, f"{tid}.png")).convert("RGBA")
    w, h = im.size
    cw, ch = w // 16, h // 16
    p = im.load()
    return [p[sx * cw + cw // 2, sy * ch + ch // 2] for sy in range(16) for sx in range(16)]


def main():
    n = int(os.environ.get("N", "10001"))
    ids = list(range(1, n + 1))
    print(f"loading {len(ids)} summer tokens...", flush=True)
    imgs = {}
    traits = {}
    for tid in ids:
        m = json.load(open(os.path.join(META, str(tid))))
        traits[tid] = {a["trait_type"]: a["value"] for a in m["attributes"]}
        imgs[tid] = grid16(tid)

    # tokens grouped by (category, value)
    by_val = defaultdict(lambda: defaultdict(list))
    for tid in ids:
        for c in ORDER:
            if c in traits[tid]:
                by_val[c][traits[tid][c]].append(tid)

    # derive sprites top-down. covered[tid][p] = painted by an already-derived
    # higher layer (so lower layers don't matter there).
    sprites = {}  # (cat,val) -> [color or None]*256
    covered = {tid: [False] * 256 for tid in ids}
    for c in reversed(ORDER):
        for v, toks in by_val[c].items():
            sprite = [None] * 256
            for p in range(256):
                color = None
                ok = True
                seen = False
                for t in toks:
                    if covered[t][p]:
                        continue
                    seen = True
                    cpx = imgs[t][p]
                    if color is None:
                        color = cpx
                    elif cpx != color:
                        ok = False
                        break
                if seen and ok:
                    sprite[p] = color
            sprites[(c, v)] = sprite
        # mark covered for this layer
        for tid in ids:
            v = traits[tid].get(c)
            if v is None:
                continue
            sp = sprites[(c, v)]
            cov = covered[tid]
            for p in range(256):
                if sp[p] is not None:
                    cov[p] = True

    # composite bottom->top and compare
    n_sprites = len(sprites)
    exact = 0
    bad = []
    for tid in ids:
        canvas = [None] * 256
        for c in ORDER:
            v = traits[tid].get(c)
            if v is None:
                continue
            sp = sprites[(c, v)]
            for p in range(256):
                if sp[p] is not None:
                    canvas[p] = sp[p]
        if canvas == imgs[tid]:
            exact += 1
        else:
            bad.append(tid)
    print(f"derived sprites: {n_sprites}")
    print(f"composite-exact: {exact}/{len(ids)}  mismatches: {len(bad)} {bad[:10]}")


if __name__ == "__main__":
    main()
