"""Build a petdex pet pack (pet.json + spritesheet.png) for a tiny dino token,
plus an extended game atlas (extra rows) and animated GIF previews.

Usage:
  python build/pets/build_pet.py <tokenId> [<tokenId> ...] [--out DIR] [--preview]
"""
import argparse
import json
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import animator as A  # noqa: E402

OUT_DEFAULT = os.path.join(A.common.ROOT, "build", "pets", "out")


def build_sheet(layers, states):
    """Render a sprite sheet: one row per state, frames left->right."""
    rows = len(states)
    sheet = Image.new("RGBA", (A.COLS * A.FRAME_W, rows * A.FRAME_H), (0, 0, 0, 0))
    meta_rows = []
    for r, (state, n, dur) in enumerate(states):
        frames = A.frames_for(state, layers)
        for c, fr in enumerate(frames):
            sheet.paste(fr, (c * A.FRAME_W, r * A.FRAME_H))
        meta_rows.append({"id": state, "row": r, "frames": n, "durationMs": dur})
    return sheet, meta_rows


def pet_json(tok, is_unique, attrs):
    """Build the petdex pet.json dict for a token (shared by batch + generator)."""
    desc_traits = ", ".join(f"{k}: {attrs[k]}" for k in ("body", "head", "hands", "feet")
                            if attrs.get(k) and attrs[k] not in ("none", "normal"))
    return {
        "id": f"tiny-dino-{tok}",
        "displayName": f"tiny dino #{tok}",
        "description": ("one of 10k cc0 tiny dinos — now your Hermes pet"
                        + (f" ({desc_traits})" if desc_traits else "")),
        "tags": ["tiny-dinos", "cc0", "pixel", "16x16"],
        "kind": "1/1" if is_unique else "dino",
    }


def build_token(tok, out_dir, preview=False):
    layers, is_unique = A.load_layers(tok)
    _, attrs = A.common.load_meta(tok)
    slug = f"tiny-dino-{tok}"
    pet_dir = os.path.join(out_dir, slug)
    os.makedirs(pet_dir, exist_ok=True)

    # 1) petdex-conformant sheet: rows 0-8 only, exactly 1536x1872
    petdex_sheet, _ = build_sheet(layers, A.PETDEX_STATES)
    assert petdex_sheet.size == (1536, 1872), petdex_sheet.size
    petdex_sheet.save(os.path.join(pet_dir, "spritesheet.png"))

    # 2) extended game atlas: petdex rows + game-only rows, with a JSON descriptor
    game_sheet, meta_rows = build_sheet(layers, A.PETDEX_STATES + A.GAME_STATES)
    game_sheet.save(os.path.join(pet_dir, "spritesheet_game.png"))
    atlas = {
        "frameWidth": A.FRAME_W, "frameHeight": A.FRAME_H,
        "columns": A.COLS, "states": meta_rows,
    }
    with open(os.path.join(pet_dir, "atlas.json"), "w") as f:
        json.dump(atlas, f, indent=2)

    # 3) pet.json (petdex minimum + a few descriptive fields)
    pet = pet_json(tok, is_unique, attrs)
    with open(os.path.join(pet_dir, "pet.json"), "w") as f:
        json.dump(pet, f, indent=2)

    if preview:
        _write_previews(layers, pet_dir)
    return pet_dir, is_unique


_CHECKER = None


def _on_checker(frame):
    """Composite a frame over a light checkerboard so transparent pets are visible."""
    global _CHECKER
    if _CHECKER is None or _CHECKER.size != frame.size:
        c = Image.new("RGBA", frame.size, (240, 240, 240, 255))
        px = c.load()
        s = 16
        for y in range(frame.size[1]):
            for x in range(frame.size[0]):
                if (x // s + y // s) % 2:
                    px[x, y] = (212, 212, 212, 255)
        _CHECKER = c
    out = _CHECKER.copy()
    out.alpha_composite(frame)
    return out.convert("P", palette=Image.ADAPTIVE)


def _write_previews(layers, pet_dir):
    prev = os.path.join(pet_dir, "preview")
    os.makedirs(prev, exist_ok=True)
    for state, n, dur in A.PETDEX_STATES + A.GAME_STATES:
        frames = [_on_checker(f) for f in A.frames_for(state, layers)]
        frames[0].save(
            os.path.join(prev, f"{state}.gif"), save_all=True,
            append_images=frames[1:], duration=dur // n, loop=0, disposal=2,
        )
    # one contact sheet of all idle frames at 1x for quick glance
    idle = A.frames_for("idle", layers)
    strip = Image.new("RGBA", (A.FRAME_W * len(idle), A.FRAME_H), (255, 255, 255, 255))
    for i, f in enumerate(idle):
        strip.alpha_composite(f, (i * A.FRAME_W, 0))
    strip.save(os.path.join(prev, "idle_strip.png"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tokens", nargs="+", type=int)
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--preview", action="store_true")
    args = ap.parse_args()
    for tok in args.tokens:
        pet_dir, uniq = build_token(tok, args.out, preview=args.preview)
        print(f"#{tok}{' [1/1]' if uniq else ''} -> {pet_dir}")


if __name__ == "__main__":
    main()
