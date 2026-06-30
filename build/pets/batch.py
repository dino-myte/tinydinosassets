"""Batch-render pet packs for all 10,001 tiny dinos in parallel.

  python build/pets/batch.py                 # all tokens -> build/pets/out
  python build/pets/batch.py --out DIR --webp # also emit WebP sheets
  python build/pets/batch.py --range 1 100    # a subset
  python build/pets/batch.py --jobs 8 --manifest

Each token -> <out>/tiny-dino-<id>/ with pet.json, spritesheet.png (+ .webp),
spritesheet_game.png, atlas.json. A manifest.json indexes the run.
"""
import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import animator as A  # noqa: E402
import build_pet  # noqa: E402

OUT_DEFAULT = os.path.join(A.common.ROOT, "build", "pets", "out")


def _one(args):
    tok, out_dir, webp = args
    try:
        pet_dir, is_unique = build_pet.build_token(tok, out_dir, preview=False)
        if webp:
            from PIL import Image
            for name in ("spritesheet.png", "spritesheet_game.png"):
                p = os.path.join(pet_dir, name)
                # lossless m6: smallest + pixel-perfect for this crisp art
                Image.open(p).save(p[:-4] + ".webp", lossless=True, method=6)
        return (tok, True, is_unique, None)
    except Exception as e:  # keep the batch going; report the failure
        return (tok, False, False, repr(e))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--range", nargs=2, type=int, metavar=("LO", "HI"))
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    ap.add_argument("--webp", action="store_true")
    ap.add_argument("--manifest", action="store_true")
    args = ap.parse_args()

    lo, hi = args.range if args.range else (1, A.common.SUPPLY)
    tokens = list(range(lo, hi + 1))
    os.makedirs(args.out, exist_ok=True)

    done = fail = uniq = 0
    failures = []
    work = [(t, args.out, args.webp) for t in tokens]
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        futs = [ex.submit(_one, w) for w in work]
        for fut in as_completed(futs):
            tok, ok, is_u, err = fut.result()
            if ok:
                done += 1
                uniq += int(is_u)
            else:
                fail += 1
                failures.append((tok, err))
            if (done + fail) % 500 == 0:
                print(f"  {done + fail}/{len(tokens)} ({fail} failed)", flush=True)

    print(f"done: {done} ok, {uniq} uniques, {fail} failed")
    if failures:
        print("failures:", failures[:20])

    if args.manifest:
        man = {
            "supply": len(tokens), "ok": done, "failed": fail, "uniques": uniq,
            "frame": [A.FRAME_W, A.FRAME_H], "grid": [9, A.COLS],
            "petdexStates": [s for s, _, _ in A.PETDEX_STATES],
            "gameStates": [s for s, _, _ in A.GAME_STATES],
            "failures": failures,
        }
        with open(os.path.join(args.out, "manifest.json"), "w") as f:
            json.dump(man, f, indent=2)


if __name__ == "__main__":
    main()
