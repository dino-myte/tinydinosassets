"""Premium animation for the 16 one-of-one tiny dinos.

The 1/1s are flat single sprites (no trait layers), so the generic fallback only
gives them whole-sprite motion. There are only 16, so they get bespoke treatment:
  - clean background handling (flood-fill strip for ghost/rexx; keep mfer's gold),
  - a rarity aura + twinkle on every 1/1 (so they read as special in Hermes),
  - per-dino SIGNATURE effects (bug=glitch, mfer=smoke, ghost=float, ...).

Everything stays petdex-compatible: same 192x208 frames, same 9-row petdex sheet.
Effects are drawn inside each frame; the sheet layout is unchanged.
"""
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageChops

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import animator as A  # noqa: E402

GOLD = (247, 209, 0)
# chain-branded 1/1s -> brand aura color
CHAIN_COLORS = {
    "opt": (255, 4, 32), "ftm": (19, 181, 244), "poly": (130, 71, 229),
    "arb": (40, 160, 240), "bsc": (243, 186, 47), "avax": (232, 65, 66),
    "eth": (108, 122, 224),
}
# per-token config: name + signature. token ids from metadata "1/1" attribute.
UNIQUES = {
    101: ("opt", "chain"), 443: ("ftm", "chain"), 701: ("rexx", "sparkle"),
    1856: ("poly", "chain"), 2022: ("friendly dino", "aura"), 2918: ("ghost", "float"),
    3657: ("arb", "chain"), 5892: ("smol birb", "flap"), 6001: ("xoshi", "flutter"),
    6400: ("bsc", "chain"), 6672: ("avax", "chain"), 7710: ("mfer", "smoke"),
    8012: ("rapter", "lunge"), 8911: ("eth", "chain"), 9845: ("cryptoad", "hop"),
    10001: ("bug", "glitch"),
}
FLOODFILL = {701, 2918}   # remove the baked background
KEEP_GOLD = {7710}        # mfer keeps its iconic gold


# ---- background handling -----------------------------------------------------
def _floodfill_strip(im, tol=46):
    """Remove the background by flood-filling inward from the border (color-tolerant),
    so multi-color backdrops (rexx sky+ground, ghost box) go transparent but the dino
    stays."""
    px = im.load()
    W, H = im.size
    out = im.copy()
    op = out.load()
    seen = [[False] * W for _ in range(H)]
    stack = []
    for x in range(W):
        stack.append((x, 0)); stack.append((x, H - 1))
    for y in range(H):
        stack.append((0, y)); stack.append((W - 1, y))
    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= W or y >= H or seen[y][x]:
            continue
        seen[y][x] = True
        r, g, b, a = px[x, y]
        # compare against nearest already-removed neighbor color = local bg
        # seed: border pixels are bg; spread to neighbors within tolerance of THIS px
        op[x, y] = (0, 0, 0, 0)
        for nx, ny in ((x+1, y), (x-1, y), (x, y+1), (x, y-1)):
            if 0 <= nx < W and 0 <= ny < H and not seen[ny][nx]:
                nr, ng, nb, na = px[nx, ny]
                if na != 0 and (abs(nr-r)+abs(ng-g)+abs(nb-b)) <= tol:
                    stack.append((nx, ny))
    return out


def base_sprite(tok):
    """16x16 dino for a 1/1 with per-token background handling."""
    im = A.common.load_original(tok).convert("RGBA")
    if tok in FLOODFILL:
        return _floodfill_strip(im)
    if tok in KEEP_GOLD:
        return im  # keep the gold backdrop as a signature
    # default: strip the flat corner background color
    px = im.load(); bg = px[0, 0]
    if bg[3] == 0:
        return im
    out = Image.new("RGBA", im.size, (0, 0, 0, 0)); op = out.load()
    for y in range(16):
        for x in range(16):
            p = px[x, y]
            op[x, y] = (0, 0, 0, 0) if p[:3] == bg[:3] else p
    return out


# ---- effect helpers (operate on 192x208 frames) ------------------------------
def _silhouette(frame):
    return frame.split()[3]


def aura(frame, color, strength, grow=6):
    """Soft glow behind the sprite from its silhouette."""
    a = _silhouette(frame).filter(ImageFilter.MaxFilter(2 * grow + 1))
    glow = Image.new("RGBA", frame.size, color + (0,))
    glow.putalpha(a.point(lambda v: int(v * strength)))
    glow = glow.filter(ImageFilter.GaussianBlur(grow))
    out = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    out.alpha_composite(glow)
    out.alpha_composite(frame)
    return out


def sparkles(frame, i, n, seed=0, color=(255, 250, 230)):
    """A few twinkling 4-point stars around the sprite."""
    bb = frame.getbbox()
    if not bb:
        return frame
    pts = [(bb[0] + 6, bb[1] + 10), (bb[2] - 10, bb[1] + 24),
           (bb[0] + 2, (bb[1] + bb[3]) // 2), (bb[2] - 4, bb[3] - 30)]
    d = ImageDraw.Draw(frame)
    for k, (x, y) in enumerate(pts):
        phase = (i + seed + k * 2) % n
        s = [0, 3, 6, 3, 0, 0][min(phase, 5)] if n >= 6 else (5 if phase % 2 else 0)
        if s:
            d.line([(x - s, y), (x + s, y)], fill=color + (230,), width=2)
            d.line([(x, y - s), (x, y + s)], fill=color + (230,), width=2)
    return frame


def gold_badge(frame, color=GOLD):
    """A rounded gold medallion behind the sprite — keeps mfer's iconic gold but
    still floats as a desktop pet (vs a full-frame opaque box)."""
    W, H = frame.size
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    d.rounded_rectangle([W * 0.16, H * 0.12, W * 0.84, H * 0.90],
                        radius=26, fill=color + (255,))
    out.alpha_composite(frame)
    return out


def smoke(frame, i, n):
    """Rising smoke puffs (for mfer's cigarette)."""
    d = ImageDraw.Draw(frame)
    ox, oy = int(frame.width * 0.72), int(frame.height * 0.30)
    for k in range(3):
        t = ((i + k * (n // 3)) % n) / n
        y = oy - int(t * 60)
        r = 4 + int(t * 8)
        a = int(150 * (1 - t))
        d.ellipse([ox - r, y - r, ox + r, y + r], fill=(210, 210, 210, a))
    return frame


def glitch(frame, i, n):
    """RGB-split + scanline jitter for the 'bug' 1/1."""
    r, g, b, a = frame.split()
    dx = [0, 3, -2, 4, -3, 1, -4, 2][i % 8]
    rr = ImageChops.offset(r, dx, 0)
    bb = ImageChops.offset(b, -dx, 0)
    out = Image.merge("RGBA", (rr, g, bb, a))
    # scanlines: darken alternate rows slightly
    sl = Image.new("RGBA", frame.size, (0, 0, 0, 0)); ds = ImageDraw.Draw(sl)
    for y in range(0, frame.height, 3):
        ds.line([(0, y), (frame.width, y)], fill=(0, 0, 0, 40))
    out.alpha_composite(sl)
    # occasional horizontal slice shift
    if i % 4 == 0:
        y0 = (i * 37) % (frame.height - 20)
        sh = 8 if i % 8 == 0 else -6
        band = out.crop((0, y0, frame.width, y0 + 14))
        out.paste(ImageChops.offset(band, sh, 0), (0, y0))
    return out


def flicker(frame, i, n, lo=0.6):
    """Whole-sprite opacity flicker (ghost)."""
    f = lo + (1 - lo) * (0.5 + 0.5 * math.cos(2 * math.pi * i / n))
    r, g, b, a = frame.split()
    return Image.merge("RGBA", (r, g, b, a.point(lambda v: int(v * f))))


# ---- per-state motion (base = animator's HD-crisp, with signature overrides) --
def _params(sig, state, i, n):
    p = dict(A._params(state, i, n))
    if sig == "float":  # ghost hovers: bigger smooth bob, gentle sway, no run-hop
        ph = 2 * math.pi * i / n
        p = dict(ty=-6 + -3 * math.sin(ph), sx=1 + 0.03 * math.sin(ph),
                 sy=1 - 0.03 * math.sin(ph), tx=2 * math.sin(ph * 0.5))
        if state in ("running-right", "running"):
            p["tx"] = 6 * math.sin(ph)
        if state == "running-left":
            p["tx"] = -6 * math.sin(ph)
    elif sig == "hop" and state in ("idle", "waiting"):
        p["ty"] = p.get("ty", 0) - 4 * abs(math.sin(2 * math.pi * i / n))
    elif sig == "flutter" and state == "jumping":
        p["ty"] = [4, -14, -20, -22, -8][min(i, 4)]   # extra hang time
    return p


def _shadow(sig):
    return sig not in ("float",)   # floaters cast no ground shadow


# ---- main entry --------------------------------------------------------------
_cache = {}


def frames_for(state, layers):
    tok = layers["_tok"]
    name, sig = UNIQUES.get(tok, ("?", "aura"))
    if tok not in _cache:
        _cache[tok] = A.prep({"_flat": base_sprite(tok)})
    prep = _cache[tok]
    n = A.NFRAMES[state]
    out = []
    for i in range(n):
        fr = A._render(prep, shadow=_shadow(sig), **_params(sig, state, i, n))
        # signature effect
        if sig == "smoke":
            fr = gold_badge(fr)              # mfer: gold medallion (floats) + smoke
            fr = smoke(fr, i, n)
        elif sig == "glitch":
            fr = glitch(fr, i, n)
        elif sig == "float":
            fr = flicker(fr, i, n)
        # rarity aura + twinkle on every 1/1
        if sig == "chain":
            fr = aura(fr, CHAIN_COLORS.get(name, GOLD), 0.85,
                      grow=5 + int(2 * (0.5 + 0.5 * math.sin(2 * math.pi * i / n))))
        elif sig != "glitch":                # glitch is its own look; skip gold aura
            pulse = 0.55 + 0.35 * (0.5 + 0.5 * math.sin(2 * math.pi * i / n))
            fr = aura(fr, GOLD, pulse)
        if sig not in ("glitch",):
            fr = sparkles(fr, i, n, seed=tok % 5)
        out.append(fr)
    return out
