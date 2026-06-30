"""Procedural animator: turn a static 16x16 tiny dino into a petdex pet sprite sheet.

The dinos are single-pose 16x16 pixel art, and `normal` feet/hands are baked into
the body (only `eyes` and special `hands` are separable), so true articulated walk
cycles aren't possible. Instead we synthesize the 9 petdex states (+ game-only
states) with deterministic, on-brand WHOLE-SPRITE motion.

Pipeline ("HD-crisp" + frame-filling), chosen after comparing to live Hermes pets:
  1. Assemble the token's layers into a 16x16 RGBA dino (VIS order == the canonical
     transparent render, verified pixel-exact). Background dropped (pets float).
  2. Scale it up so its CONTENT fills most of the 192x208 frame like real pets do
     (~full height, the iikun/chillhouse proportion), NEAREST -> stays crisp pixel art.
  3. Animate with CONTINUOUS (float) translation / squash-stretch / small rotation,
     computed at this high resolution so motion glides instead of snapping in 8px
     jumps. (The earlier 16-grid integer approach looked jittery.)
  4. Drop a soft contact shadow that shrinks/fades as the dino leaves the ground.
Layer-aware touches the trait split gives us for free: blink (drop `eyes` for a frame).

Geometry (petdex canonical, see PETS_RESEARCH.md):
  frame = 192x208, grid = 9 rows x 8 cols, sheet = 1536x1872.
"""
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import common  # noqa: E402  (build/common.py: load_sprite, load_meta, VIS, is_unique)

# ---- frame geometry (petdex canonical) --------------------------------------
DINO = 16                                  # native dino grid
FRAME_W, FRAME_H = 192, 208                # petdex frame
COLS = 8                                    # frames-per-row max

# ---- framing: how the dino sits in the frame --------------------------------
REST_CONTENT_H = 158        # target on-screen height of the dino's content at rest
FEET_Y = 192                # baseline (px) the feet rest on
SCALE_MIN, SCALE_MAX = 9, 16
SHADOW_ALPHA = 82

# layer paint order, background excluded (pets are transparent)
LAYERS = [c for c in common.VIS if c != "background"]


# ---- petdex state table (must match src/lib/pet-states.ts) -------------------
PETDEX_STATES = [
    ("idle", 6, 1100),
    ("running-right", 8, 1060),
    ("running-left", 8, 1060),
    ("waving", 4, 700),
    ("jumping", 5, 840),
    ("failed", 8, 1220),
    ("waiting", 6, 1010),
    ("running", 6, 820),
    ("review", 6, 1030),
]

# game-only states, appended in rows >= 9 (ignored by petdex, used by game engines)
GAME_STATES = [
    ("attack", 6, 600),
    ("hurt", 4, 500),
    ("death", 8, 1200),
    ("sleep", 6, 1600),
]
NFRAMES = {s: f for s, f, _ in PETDEX_STATES + GAME_STATES}


# ---- assembling the dino (unchanged: base pose is pixel-exact) ---------------
def load_layers(tok):
    """Return ({category: 16x16 RGBA sprite}, is_unique) for a token, bg excluded.

    Unique 1/1s are flat single sprites: load the canonical render, strip the bg.
    """
    _, attrs = common.load_meta(tok)
    if common.is_unique(attrs):
        return {"_flat": _strip_bg_like(common.load_original(tok).copy())}, True
    layers = {}
    for cat in LAYERS:
        v = attrs.get(cat)
        if not v or v == "none":
            continue
        try:
            sp = common.load_sprite(cat, v)
        except FileNotFoundError:
            continue
        if sp.getbbox():
            layers[cat] = sp
    return layers, False


def _strip_bg_like(im):
    """For 1/1 flats: make the dominant corner color transparent (best effort)."""
    im = im.convert("RGBA")
    px = im.load()
    bg = px[0, 0]
    if bg[3] == 0:
        return im
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    op = out.load()
    for y in range(im.height):
        for x in range(im.width):
            p = px[x, y]
            op[x, y] = (0, 0, 0, 0) if p[:3] == bg[:3] else p
    return out


def assemble(layers, drop=()):
    """Composite layers into a single 16x16 RGBA dino (drop e.g. ('eyes',))."""
    canvas = Image.new("RGBA", (DINO, DINO), (0, 0, 0, 0))
    if "_flat" in layers:
        canvas.alpha_composite(layers["_flat"])
        return canvas
    for cat in LAYERS:
        sp = layers.get(cat)
        if sp is not None and cat not in drop:
            canvas.alpha_composite(sp)
    return canvas


# ---- HD source prep & frame rendering ---------------------------------------
def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def prep(layers):
    """Pre-scale the dino to a crisp HD sprite sized to fill the frame.

    Returns a dict with the cropped content sprite (and an eyes-dropped variant for
    blinks), keyed for reuse across all frames of a token.
    """
    d = assemble(layers)
    bb = d.getbbox() or (0, 0, DINO, DINO)
    ch = max(1, bb[3] - bb[1])
    s = _clamp(round(REST_CONTENT_H / ch), SCALE_MIN, SCALE_MAX)
    box = (bb[0] * s, bb[1] * s, bb[2] * s, bb[3] * s)
    full = d.resize((DINO * s, DINO * s), Image.NEAREST).crop(box)
    noeyes = assemble(layers, drop=("eyes",)).resize(
        (DINO * s, DINO * s), Image.NEAREST).crop(box)
    return {"content": full, "noeyes": noeyes, "w": full.width, "h": full.height}


def _shadow(frame, base_w, tx, ty):
    """Soft contact shadow on the floor; shrinks and fades as the dino rises."""
    lift = max(0.0, -ty)
    f = max(0.35, 1.0 - lift / 130.0)
    ex = base_w * 0.42 * f
    ey = 9 * f
    cx = FRAME_W / 2 + tx * 0.5
    sh = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse(
        [cx - ex, FEET_Y - ey, cx + ex, FEET_Y + ey],
        fill=(0, 0, 0, int(SHADOW_ALPHA * f)))
    frame.alpha_composite(sh.filter(ImageFilter.GaussianBlur(4)))


def _render(p, *, tx=0.0, ty=0.0, sx=1.0, sy=1.0, rot=0.0, flip=False,
            noeyes=False, shadow=True):
    img = p["noeyes"] if noeyes else p["content"]
    if flip:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    w = max(2, round(img.width * sx))
    h = max(2, round(img.height * sy))
    if (w, h) != img.size:
        img = img.resize((w, h), Image.NEAREST)
    if rot:
        img = img.rotate(rot, resample=Image.NEAREST, expand=True)
    frame = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
    if shadow:
        _shadow(frame, p["w"], tx, ty)
    x = round(FRAME_W / 2 + tx - img.width / 2)
    y = round(FEET_Y + ty - img.height)
    frame.alpha_composite(img, (x, y))
    return frame


# ---- per-state continuous motion --------------------------------------------
def frames_for(state, layers):
    p = prep(layers)
    n = NFRAMES[state]
    out = []
    for i in range(n):
        out.append(_render(p, **_params(state, i, n)))
    return out


def _params(state, i, n):
    t = i / n
    ph = 2 * math.pi * t
    if state == "idle":
        kw = dict(ty=-3 * (0.5 - 0.5 * math.cos(ph)),
                  sy=1 + 0.025 * math.sin(ph), sx=1 - 0.02 * math.sin(ph))
        if i == n - 2:
            kw["noeyes"] = True            # one blink near the loop end
        return kw
    if state in ("running-right", "running-left"):
        flip = state == "running-left"
        hop = abs(math.sin(ph * 2))        # two strides per loop
        return dict(ty=-12 * hop, sy=1 + 0.06 * hop, sx=1 - 0.05 * hop,
                    rot=(-1 if flip else 1) * 6 * math.sin(ph * 2 + 0.6),
                    tx=(-1 if flip else 1) * 2 * math.sin(ph * 2), flip=flip)
    if state == "running":                 # generic in-place run
        hop = abs(math.sin(ph * 2))
        return dict(ty=-11 * hop, sy=1 + 0.06 * hop, sx=1 - 0.05 * hop,
                    rot=4 * math.sin(ph * 2))
    if state == "waving":
        return dict(ty=-4 * (0.5 - 0.5 * math.cos(ph)), rot=11 * math.sin(ph * 2))
    if state == "jumping":                 # crouch, launch, peak, descend, land
        ty = [6, -16, -22, -14, 4][min(i, 4)]
        sy = [0.86, 1.10, 1.04, 1.00, 0.88][min(i, 4)]
        sx = [1.14, 0.93, 0.97, 1.00, 1.12][min(i, 4)]
        return dict(ty=ty, sy=sy, sx=sx)
    if state == "failed":
        k = min(1.0, t * 1.5)
        return dict(ty=10 * k, sy=1 - 0.28 * k, sx=1 + 0.14 * k, rot=-8 * k,
                    noeyes=t > 0.3)
    if state == "waiting":
        return dict(ty=-2 * (0.5 - 0.5 * math.cos(ph)), sy=1 + 0.02 * math.sin(ph),
                    rot=2 * math.sin(ph))
    if state == "review":
        return dict(rot=6 + 2 * math.sin(ph * 2), tx=4,
                    ty=-2 * abs(math.sin(ph * 2)))
    if state == "attack":
        lunge = math.sin(math.pi * t)
        return dict(tx=12 * lunge, rot=14 * lunge, sx=1 + 0.10 * lunge,
                    sy=1 - 0.05 * lunge)
    if state == "hurt":
        knock = math.cos(ph) * (1 - t)
        return dict(tx=12 * knock, rot=-12 * (1 - t), sy=0.90)
    if state == "death":
        return dict(ty=14 * t, sy=1 - 0.45 * t, sx=1 + 0.20 * t, rot=-85 * t,
                    noeyes=True)
    if state == "sleep":
        br = 0.5 - 0.5 * math.cos(ph)
        return dict(ty=3, sy=1 - 0.06 + 0.06 * br, sx=1 + 0.04 - 0.04 * br,
                    noeyes=True)
    return dict()
