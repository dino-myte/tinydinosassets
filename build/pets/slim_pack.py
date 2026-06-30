"""Build a lean, webp-only distributable pack from the rendered PNG sheets.

Re-encodes the pristine PNG sheets to LOSSLESS WebP (method 6) — smallest AND
pixel-perfect for this crisp art (lossy is both larger and noisier here). Output is
a flat tree ready for static / IPFS / R2 hosting.

  python build/pets/slim_pack.py                 # petdex-only (lean, ~0.3GB)
  python build/pets/slim_pack.py --game          # also include the game sheets
  python build/pets/slim_pack.py --src DIR --out DIR --jobs 8

  <out>/tiny-dino-<id>/
    pet.json
    atlas.json
    spritesheet.webp            (+ spritesheet_game.webp with --game)
"""
import argparse
import os
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DEFAULT = os.path.join(ROOT, "build", "pets", "out")
OUT_DEFAULT = os.path.join(ROOT, "build", "pets", "dist")


def _one(args):
    slug, src_dir, out_dir, game = args
    s = os.path.join(src_dir, slug)
    o = os.path.join(out_dir, slug)
    os.makedirs(o, exist_ok=True)
    try:
        for j in ("pet.json", "atlas.json"):
            if os.path.exists(os.path.join(s, j)):
                shutil.copyfile(os.path.join(s, j), os.path.join(o, j))
        sheets = ["spritesheet.png"] + (["spritesheet_game.png"] if game else [])
        for name in sheets:
            p = os.path.join(s, name)
            Image.open(p).save(os.path.join(o, name[:-4] + ".webp"),
                               lossless=True, method=6)
        return (slug, True, None)
    except Exception as e:
        return (slug, False, repr(e))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC_DEFAULT)
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--game", action="store_true")
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    args = ap.parse_args()

    slugs = sorted(d for d in os.listdir(args.src) if d.startswith("tiny-dino-"))
    os.makedirs(args.out, exist_ok=True)
    work = [(s, args.src, args.out, args.game) for s in slugs]

    ok = fail = 0
    fails = []
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        for fut in as_completed([ex.submit(_one, w) for w in work]):
            slug, good, err = fut.result()
            ok += good
            if not good:
                fail += 1
                fails.append((slug, err))
            if (ok + fail) % 1000 == 0:
                print(f"  {ok + fail}/{len(slugs)} ({fail} failed)", flush=True)

    size = sum(os.path.getsize(os.path.join(dp, f))
               for dp, _, fs in os.walk(args.out) for f in fs)
    print(f"done: {ok} ok, {fail} failed -> {args.out}  ({size/1e6:.0f} MB)")
    if fails:
        print("failures:", fails[:10])


if __name__ == "__main__":
    main()
