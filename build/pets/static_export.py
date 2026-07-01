"""Export the full static site + assets for Cloudflare R2 + Pages hosting.

Renders every token's deployable files (reusing the generator's render()) into a
self-contained tree you can `aws s3 sync` to R2 and serve as-is:

  build/pets/deploy/
    index.html                 (CDN-aware frontend; set CDN_BASE before deploy)
    manifest.json
    pets/tiny-dino-<id>/
      pet.json  atlas.json
      spritesheet.webp  spritesheet_game.webp   (lossless)
      preview.webp                              (animated thumbnail)
      pet.zip                                   (installable: pet.json + spritesheet.webp)

Usage:
  python build/pets/static_export.py                  # all tokens
  python build/pets/static_export.py --range 1 50 --jobs 8
  python build/pets/static_export.py --no-game        # skip the heavy game sheets
"""
import argparse
import json
import os
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import animator as A  # noqa: E402
import server as S  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DEFAULT = os.path.join(HERE, "deploy")


def _one(args):
    tok, out_dir, game = args
    try:
        r = S.render(tok)
        d = os.path.join(out_dir, "pets", f"tiny-dino-{tok}")
        os.makedirs(d, exist_ok=True)
        files = {
            "pet.json": r["pet.json"], "atlas.json": r["atlas.json"],
            "spritesheet.webp": r["spritesheet.webp"], "preview.webp": r["preview.webp"],
            "pet.zip": S.pack_zip(tok),
        }
        if game:
            files["spritesheet_game.webp"] = r["spritesheet_game.webp"]
        for name, body in files.items():
            with open(os.path.join(d, name), "wb") as f:
                f.write(body)
        return (tok, True, None)
    except Exception as e:
        return (tok, False, repr(e))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--range", nargs=2, type=int, metavar=("LO", "HI"))
    ap.add_argument("--tokens", help="comma-separated token ids (overrides --range)")
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    ap.add_argument("--no-game", action="store_true")
    args = ap.parse_args()

    if args.tokens:
        tokens = [int(t) for t in args.tokens.split(",") if t.strip()]
    elif args.range:
        lo, hi = args.range
        tokens = list(range(lo, hi + 1))
    else:
        tokens = list(range(1, A.common.SUPPLY + 1))
    os.makedirs(args.out, exist_ok=True)

    # frontend + manifest
    shutil.copyfile(os.path.join(HERE, "site", "index.html"),
                    os.path.join(args.out, "index.html"))
    with open(os.path.join(args.out, "manifest.json"), "w") as f:
        json.dump({
            "name": "tiny dinos", "supply": A.common.SUPPLY,
            "frame": [A.FRAME_W, A.FRAME_H], "grid": [9, A.COLS],
            "petdexStates": [s for s, _, _ in A.PETDEX_STATES],
            "gameStates": [s for s, _, _ in A.GAME_STATES],
            "layout": "pets/tiny-dino-<id>/{pet.json,spritesheet.webp,spritesheet_game.webp,atlas.json,preview.webp,pet.zip}",
        }, f, indent=2)

    ok = fail = 0
    fails = []
    work = [(t, args.out, not args.no_game) for t in tokens]
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        for fut in as_completed([ex.submit(_one, w) for w in work]):
            tok, good, err = fut.result()
            ok += good
            if not good:
                fail += 1
                fails.append((tok, err))
            if (ok + fail) % 1000 == 0:
                print(f"  {ok + fail}/{len(tokens)} ({fail} failed)", flush=True)

    size = sum(os.path.getsize(os.path.join(dp, f))
               for dp, _, fs in os.walk(args.out) for f in fs)
    print(f"done: {ok} ok, {fail} failed -> {args.out}  ({size/1e6:.0f} MB)")
    if fails:
        print("failures:", fails[:10])


if __name__ == "__main__":
    main()
