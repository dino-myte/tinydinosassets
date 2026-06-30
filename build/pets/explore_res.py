"""Resolution / smoothness exploration for the pet animation.

Renders the same states three ways so we can compare how internal resolution and
resampling affect motion quality:
  A) native16  - current approach: 16-grid motion, 8x NEAREST, integer steps
  B) hd_crisp  - high-res working buffer, continuous (float) motion + small
                 rotations, NEAREST resampling (stays blocky pixel-art)
  C) hd_smooth - same motion, LANCZOS resampling (smooth "HD pixel" look)

Output: comparison GIFs + a side-by-side strip in build/pets/out/explore/.
"""
import math
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import animator as A  # noqa: E402

FW, FH = A.FRAME_W, A.FRAME_H          # 192 x 208
DINO_PX = 132                          # on-screen size the 16-grid dino maps to
FEET_Y = 188                           # baseline (screen px) the feet rest on


def base_dino(layers, drop=()):
    """16x16 assembled dino -> RGBA upscaled to DINO_PX with NEAREST (crisp source)."""
    d = A.assemble(layers, drop=drop)
    return d.resize((DINO_PX, DINO_PX), Image.NEAREST)


def place(frame_buf, sprite, cx, feet_y):
    """alpha_composite sprite centered at cx with its bottom at feet_y."""
    x = round(cx - sprite.width / 2)
    y = round(feet_y - sprite.height)
    frame_buf.alpha_composite(sprite, (x, y))


def hd_frame(src, *, tx=0.0, ty=0.0, sx=1.0, sy=1.0, rot=0.0, flip=False,
             smooth=False, drop_src=None):
    """Render one 192x208 frame from a high-res dino src via resize+rotate+place."""
    img = drop_src if drop_src is not None else src
    if flip:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    flt = Image.LANCZOS if smooth else Image.NEAREST
    w = max(2, round(img.width * sx))
    h = max(2, round(img.height * sy))
    if (w, h) != img.size:
        img = img.resize((w, h), flt)
    if rot:
        img = img.rotate(rot, resample=(Image.BICUBIC if smooth else Image.NEAREST),
                         expand=True)
    frame = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    place(frame, img, FW / 2 + tx, FEET_Y + ty)
    return frame


# ---- continuous (float) motion for the HD variants -------------------------
def hd_state_frames(state, layers, smooth):
    src = base_dino(layers)
    src_noeyes = base_dino(layers, drop=("eyes",))
    n = {s: f for s, f, _ in A.PETDEX_STATES + A.GAME_STATES}[state]
    out = []
    for i in range(n):
        t = i / n
        ph = 2 * math.pi * t
        kw = dict(smooth=smooth)
        if state == "idle":
            kw.update(ty=-3 * (0.5 - 0.5 * math.cos(ph)),
                      sy=1 + 0.03 * math.sin(ph), sx=1 - 0.02 * math.sin(ph))
            if i == n - 2:
                kw["drop_src"] = src_noeyes
        elif state in ("running-right", "running-left", "running"):
            hop = abs(math.sin(ph * 2))             # two strides per loop
            kw.update(ty=-10 * hop, sy=1 + 0.06 * hop, sx=1 - 0.04 * hop,
                      rot=6 * math.sin(ph * 2 + 0.6), tx=2 * math.sin(ph * 2),
                      flip=(state == "running-left"))
        elif state == "waving":
            kw.update(ty=-4 * (0.5 - 0.5 * math.cos(ph)), rot=10 * math.sin(ph * 2))
        elif state == "jumping":
            # parabolic arc with anticipation + landing squash
            air = math.sin(math.pi * t)
            sq = -0.18 if t < 0.12 or t > 0.88 else 0.0   # crouch at ends
            kw.update(ty=-46 * air + (8 if sq else 0),
                      sy=1 + sq + 0.18 * air, sx=1 - 0.12 * air - sq)
        elif state == "failed":
            k = min(1.0, t * 1.6)
            kw.update(ty=10 * k, sy=1 - 0.28 * k, sx=1 + 0.12 * k, rot=-8 * k)
            if t > 0.3:
                kw["drop_src"] = src_noeyes
        elif state == "waiting":
            kw.update(ty=-2 * (0.5 - 0.5 * math.cos(ph)), sy=1 + 0.02 * math.sin(ph))
        elif state == "review":
            kw.update(rot=7, tx=4, ty=-2 * abs(math.sin(ph * 2)))
        elif state == "attack":
            lunge = math.sin(math.pi * t)
            kw.update(tx=10 * lunge, rot=12 * lunge, sx=1 + 0.1 * lunge)
        elif state == "hurt":
            kw.update(tx=10 * math.cos(ph) * (1 - t), rot=-12 * (1 - t), sy=1 - 0.1)
        elif state == "death":
            kw.update(ty=12 * t, sy=1 - 0.4 * t, sx=1 + 0.18 * t, rot=-80 * t,
                      drop_src=src_noeyes)
        elif state == "sleep":
            br = 0.5 - 0.5 * math.cos(ph)
            kw.update(ty=2, sy=1 - 0.05 + 0.05 * br, drop_src=src_noeyes)
        out.append(hd_frame(src, **kw))
    return out


def checker(size):
    c = Image.new("RGBA", size, (238, 238, 238, 255))
    px = c.load(); s = 24
    for y in range(size[1]):
        for x in range(size[0]):
            if (x // s + y // s) % 2:
                px[x, y] = (208, 208, 208, 255)
    return c


def gif(frames, path, dur):
    bg = checker(frames[0].size)
    seq = []
    for f in frames:
        c = bg.copy(); c.alpha_composite(f)
        seq.append(c.convert("P", palette=Image.ADAPTIVE))
    seq[0].save(path, save_all=True, append_images=seq[1:], duration=dur,
                loop=0, disposal=2)


def main():
    tok = int(sys.argv[1]) if len(sys.argv) > 1 else 33
    layers, _ = A.load_layers(tok)
    out = os.path.join(A.common.ROOT, "build", "pets", "out", "explore")
    os.makedirs(out, exist_ok=True)
    states = ["idle", "running-right", "jumping", "waving", "review", "failed"]

    # A) current native-16 approach (reuse the production animator)
    a_seq = []
    for s in states:
        a_seq += A.frames_for(s, layers)
    gif(a_seq, os.path.join(out, f"A_native16_{tok}.gif"), 110)

    # B) HD crisp, C) HD smooth
    for tag, smooth in (("B_hd_crisp", False), ("C_hd_smooth", True)):
        seq = []
        for s in states:
            seq += hd_state_frames(s, layers, smooth)
        gif(seq, os.path.join(out, f"{tag}_{tok}.gif"), 110)
    print("wrote A/B/C gifs for", tok, "->", out)


if __name__ == "__main__":
    main()
