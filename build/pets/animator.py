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
  4. Drop a stepped, dino-pixel-scale contact shadow that shrinks/fades with lift.

Personality pass (everything drawn as chunky dino-scale pixel blocks, so the 16x16
look holds):
  - eye acting: a blink (drop `eyes` for one frame) — eyes otherwise stay put;
  - pixel emotes: heart on wave, sweat drop on failed, thought dots on review,
    rising Z's on sleep, slash arc on attack, damage flash on hurt, soul on death,
    dust puffs on run/jump;
  - trait signatures: rocket-boots flame, hoverboard/skateboard glide, crown twinkle;
  - per-token seeding: bob amplitude/phase/blink slot vary by tokenId so 10k pets
    don't move in lockstep.

Geometry (petdex canonical, see PETS_RESEARCH.md):
  frame = 192x208, grid = 9 rows x 8 cols, sheet = 1536x1872.
"""
import math
import os
import sys

from PIL import Image, ImageDraw

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
SHADOW_ALPHA = 70

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
    Regular dinos also carry `_seed` (tokenId) and `_fx` (trait signatures).
    """
    _, attrs = common.load_meta(tok)
    if common.is_unique(attrs):
        # 1/1s get bespoke premium animation (see uniques.py); carry the token id.
        return {"_flat": _strip_bg_like(common.load_original(tok).copy()), "_tok": tok}, True
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
    layers["_seed"] = tok
    layers["_fx"] = _fx_for(attrs)
    return layers, False


def _fx_for(attrs):
    """Trait -> signature-effect tags (kept tiny & on-brand)."""
    fx = set()
    feet = attrs.get("feet")
    if feet == "rocket boots":
        fx.add("rocket")
    elif feet in ("hoverboard", "skateboard"):
        fx.add("board")
    if attrs.get("head") == "crown":
        fx.add("crown")
    return frozenset(fx)


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

    Returns the cropped content sprite (and an eyes-dropped variant for blinks),
    keyed for reuse across all frames of a token.
    """
    d = assemble(layers)
    bb = d.getbbox() or (0, 0, DINO, DINO)
    ch = max(1, bb[3] - bb[1])
    s = _clamp(round(REST_CONTENT_H / ch), SCALE_MIN, SCALE_MAX)
    box = (bb[0] * s, bb[1] * s, bb[2] * s, bb[3] * s)

    def up(im):
        return im.resize((DINO * s, DINO * s), Image.NEAREST).crop(box)

    p = {"content": up(d), "noeyes": up(assemble(layers, drop=("eyes",))), "s": s}
    p["w"], p["h"] = p["content"].size
    return p


def _shadow(frame, p, tx, ty):
    """Stepped contact shadow at dino-pixel scale; shrinks and fades with lift."""
    s = p["s"]
    lift = max(0.0, -ty)
    f = max(0.35, 1.0 - lift / 130.0)
    wc = max(3, int(round(p["w"] * 0.84 * f / s)))   # width in dino-pixels
    cx = FRAME_W / 2 + tx * 0.5
    d = ImageDraw.Draw(frame)
    rh = max(3, int(s * 0.5))                        # half-cell rows: low, subtle
    for r, (rw, ra) in enumerate(((wc, SHADOW_ALPHA), (wc - 2, int(SHADOW_ALPHA * 0.55)))):
        rw = max(2, rw)
        x0 = int(cx - rw * s / 2)
        y0 = int(FEET_Y - s * 0.35) + r * rh
        d.rectangle([x0, y0, x0 + rw * s - 1, y0 + rh - 1], fill=(0, 0, 0, int(ra * f)))


def _render(p, *, tx=0.0, ty=0.0, sx=1.0, sy=1.0, rot=0.0, flip=False,
            noeyes=False, flash=False, shadow=True):
    img = p["noeyes"] if noeyes else p["content"]
    if flip:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    w = max(2, round(img.width * sx))
    h = max(2, round(img.height * sy))
    if (w, h) != img.size:
        img = img.resize((w, h), Image.NEAREST)
    if rot:
        img = img.rotate(rot, resample=Image.NEAREST, expand=True)
    if flash:  # damage flash: solid white silhouette
        white = Image.new("RGBA", img.size, (255, 255, 255, 255))
        white.putalpha(img.split()[3])
        img = white
    frame = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
    if shadow:
        _shadow(frame, p, tx, ty)
    x = round(FRAME_W / 2 + tx - img.width / 2)
    y = round(FEET_Y + ty - img.height)
    frame.alpha_composite(img, (x, y))
    return frame


# ---- pixel emotes (drawn as dino-scale pixel blocks -> stays on-brand) -------
HEART_C = (232, 82, 105)
SWEAT_C = (92, 172, 255)
ZZZ_C = (168, 186, 255)
DOTS_C = (126, 126, 126)
SLASH_C = (255, 255, 255)
DUST_C = (186, 186, 186)
FLAME_C, FLAME_C2 = (255, 122, 36), (255, 214, 64)
SOUL_C = (214, 228, 255)
TWINKLE_C = (255, 252, 214)

GLYPH_HEART = ((0, 0), (2, 0), (0, 1), (1, 1), (2, 1), (1, 2))
GLYPH_Z = ((0, 0), (1, 0), (2, 0), (1, 1), (0, 2), (1, 2), (2, 2))
GLYPH_SLASH = ((2, 0), (3, 1), (3, 2), (2, 3))


def _stamp(frame, x, y, cells, s, color, alpha=235, flipx=False):
    """Blit a glyph of s-by-s pixel blocks with its (0,0) cell at frame coords (x,y)."""
    d = ImageDraw.Draw(frame)
    for gx, gy in cells:
        if flipx:
            gx = -gx
        x0, y0 = int(x + gx * s), int(y + gy * s)
        if x0 + s < 0 or y0 + s < 0 or x0 >= FRAME_W or y0 >= FRAME_H:
            continue
        d.rectangle([x0, y0, x0 + s - 1, y0 + s - 1], fill=color + (alpha,))


def _decorate(frame, state, i, n, p, kw, seed, fx):
    """State-specific pixel emotes + trait signatures, anchored to the sprite."""
    s = p["s"]
    sx, sy = kw.get("sx", 1.0), kw.get("sy", 1.0)
    tx, ty = kw.get("tx", 0.0), kw.get("ty", 0.0)
    w, h = p["w"] * sx, p["h"] * sy
    cx = FRAME_W / 2 + tx            # sprite center x
    top = FEET_Y + ty - h            # sprite top y
    feet = FEET_Y + ty               # sprite bottom y

    if state == "waving" and i in (1, 2):
        _stamp(frame, cx + w * 0.38, top - 2.4 * s - (i - 1) * 0.5 * s,
               GLYPH_HEART, s, HEART_C, alpha=245 if i == 1 else 185)

    elif state == "failed" and i >= 2:
        k = min(i - 2, 4)
        _stamp(frame, cx + w * 0.42, top + 0.6 * s + k * 0.45 * s,
               ((0, 0),), s, SWEAT_C, alpha=225)
        _stamp(frame, cx + w * 0.42, top + 0.6 * s + k * 0.45 * s + s,
               ((0, 0),), s, tuple(min(255, c + 45) for c in SWEAT_C), alpha=190)

    elif state == "review":
        for k in range(min(3, i // 2 + 1)):        # thought dots pop in one by one
            _stamp(frame, cx - 1.5 * s + k * 2 * s, top - 2 * s,
                   ((0, 0),), s, DOTS_C, alpha=210)

    elif state == "sleep":
        for k in range(2):                          # two Z's drifting up-right
            tt = ((i + k * n // 2) % n) / n
            _stamp(frame, cx + w * 0.30 + k * 1.9 * s + tt * 1.2 * s,
                   top - 0.8 * s - tt * 3.2 * s,
                   GLYPH_Z, s, ZZZ_C, alpha=int((235 - k * 60) * (1 - tt * 0.8)))

    elif state == "attack" and i in (2, 3):
        _stamp(frame, cx + w * 0.52 + (i - 2) * 0.6 * s, top + h * 0.22,
               GLYPH_SLASH, s, SLASH_C, alpha=235 if i == 2 else 140)

    elif state == "death" and i >= n - 3:
        k = i - (n - 3)                             # little soul-heart floats away
        _stamp(frame, cx - 1.5 * s, top + h * 0.25 - k * 1.3 * s,
               GLYPH_HEART, s, SOUL_C, alpha=max(130, 240 - 55 * k))

    elif state == "jumping":
        if i == 1:                                  # launch dust
            for dx in (-0.55, 0.45):
                _stamp(frame, cx + w * dx, FEET_Y - 0.6 * s, ((0, 0),), s, DUST_C, 150)
        elif i == n - 1:                            # landing dust
            for dx in (-0.65, -0.15, 0.5):
                _stamp(frame, cx + w * dx, FEET_Y - 0.6 * s, ((0, 0),), s, DUST_C, 170)
        if "rocket" in fx and i in (1, 2):          # rocket boots: thrust on launch
            _flame(frame, cx, feet, s, i)

    elif state in ("running-right", "running-left", "running"):
        dirn = -1 if state == "running-left" else 1
        hop = abs(math.sin(2 * math.pi * i / n * 2))
        if "board" in fx:                           # board riders leave a low trail
            if i % 2 == 0:
                _stamp(frame, cx - dirn * (w * 0.55 + 0.3 * s), FEET_Y - 0.7 * s,
                       ((0, 0),), s, DUST_C, 120)
        elif "rocket" in fx and hop > 0.5:          # airborne: thrust
            _flame(frame, cx, feet, s, i)
        elif hop < 0.25:                            # footfall: kick up dust
            _stamp(frame, cx - dirn * w * 0.52, FEET_Y - 0.6 * s, ((0, 0),), s, DUST_C, 150)
            _stamp(frame, cx - dirn * (w * 0.52 + s), FEET_Y - 0.5 * s - 0.4 * s,
                   ((0, 0),), s, DUST_C, 100)

    if "crown" in fx and state in ("idle", "waiting", "waving") and (i + seed) % 3 == 0:
        _stamp(frame, cx + 0.9 * s, top + 0.25 * s, ((0, 0),), s, TWINKLE_C, 220)


def _flame(frame, cx, feet, s, i):
    """Two-tone boot flame, flickering with frame parity."""
    _stamp(frame, cx - s, feet - 0.2 * s, ((0, 0), (1, 0)), s, FLAME_C, 220)
    _stamp(frame, cx - s + (i % 2) * s, feet + 0.8 * s, ((0, 0),), s, FLAME_C2, 200)


# ---- per-state continuous motion --------------------------------------------
def frames_for(state, layers):
    if "_tok" in layers:                      # 1/1 -> premium bespoke path
        import uniques
        return uniques.frames_for(state, layers)
    p = prep(layers)
    seed = layers.get("_seed", 0)
    fx = layers.get("_fx", frozenset())
    n = NFRAMES[state]
    out = []
    for i in range(n):
        kw = _params(state, i, n, seed=seed, fx=fx)
        fr = _render(p, **kw)
        _decorate(fr, state, i, n, p, kw, seed, fx)
        out.append(fr)
    return out


def _params(state, i, n, seed=0, fx=frozenset()):
    t = i / n
    ph = 2 * math.pi * t
    # seeded de-sync for ambient states: 10k pets shouldn't breathe in unison
    phs = 2 * math.pi * ((t + (seed % 8) / 8.0) % 1.0)
    if state == "idle":
        amp = 2.5 + (seed % 5) * 0.25
        kw = dict(ty=-amp * (0.5 - 0.5 * math.cos(phs)),
                  sy=1 + 0.025 * math.sin(phs), sx=1 - 0.02 * math.sin(phs))
        blink = n - 2 if (seed >> 3) % 2 == 0 else n - 3
        if i == blink:
            kw["noeyes"] = True            # one blink near the loop end
        return kw
    if state in ("running-right", "running-left"):
        flip = state == "running-left"
        dirn = -1 if flip else 1
        if "board" in fx:                  # hoverboard/skateboard: glide, don't hop
            glide = math.sin(ph)
            return dict(ty=-3 - 2 * abs(math.sin(ph * 2)), tx=dirn * 4 * glide,
                        rot=dirn * (5 + 2 * glide), flip=flip)
        hop = abs(math.sin(ph * 2))        # two strides per loop
        return dict(ty=-12 * hop, sy=1 + 0.06 * hop, sx=1 - 0.05 * hop,
                    rot=dirn * 6 * math.sin(ph * 2 + 0.6),
                    tx=dirn * 2 * math.sin(ph * 2), flip=flip)
    if state == "running":                 # generic in-place run
        if "board" in fx:
            glide = math.sin(ph)
            return dict(ty=-3 - 2 * abs(math.sin(ph * 2)), tx=4 * glide,
                        rot=5 + 2 * glide)
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
    if state == "waiting":                 # patient bob, with a blink mid-loop
        kw = dict(ty=-2 * (0.5 - 0.5 * math.cos(phs)), sy=1 + 0.02 * math.sin(phs),
                  rot=2 * math.sin(phs))
        if i == 3:
            kw["noeyes"] = True
        return kw
    if state == "review":                  # leaning in over the work
        return dict(rot=6 + 2 * math.sin(ph * 2), tx=4,
                    ty=-2 * abs(math.sin(ph * 2)))
    if state == "attack":
        lunge = math.sin(math.pi * t)
        return dict(tx=12 * lunge, rot=14 * lunge, sx=1 + 0.10 * lunge,
                    sy=1 - 0.05 * lunge)
    if state == "hurt":
        knock = math.cos(ph) * (1 - t)
        return dict(tx=12 * knock, rot=-12 * (1 - t), sy=0.90, flash=i == 0)
    if state == "death":
        return dict(ty=14 * t, sy=1 - 0.45 * t, sx=1 + 0.20 * t, rot=-85 * t,
                    noeyes=True)
    if state == "sleep":
        br = 0.5 - 0.5 * math.cos(ph)
        return dict(ty=3, sy=1 - 0.06 + 0.06 * br, sx=1 + 0.04 - 0.04 * br,
                    noeyes=True)
    return dict()
