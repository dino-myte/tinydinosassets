# Tiny Dinos → Hermes Pet Sprite Sheets — Research & Plan

Goal: turn each of the 10,001 tiny dinos into an animated sprite sheet that works as a
Hermes Agent pet (petdex format) **and** is reusable as a game-ready character with a full
movement set.

---

## 1. The target format (authoritative — pulled from `crafter-station/petdex`)

Hermes pets use the **petdex** package format. A pet is a folder:

```
<slug>/
├── pet.json
└── spritesheet.{png,webp}
```

Installed to `~/.codex/pets/<slug>/` and `~/.petdex/pets/<slug>/` (Hermes: `<HERMES_HOME>/pets/<slug>/`).
Decoded with Pillow on the Hermes side.

### Sprite sheet geometry (canonical)

- **Frame size: 192 × 208 px** (`PET_THUMBNAIL_FRAME_WIDTH/HEIGHT` in petdex).
- **Grid: 9 rows × 8 cols** → recommended sheet **1536 × 1872** (`8·192 × 9·208`).
  - NB: the README prose says "8 rows × 9 cols" but the real geometry from the
    dimensions and `pet-states.ts` is **9 rows (states) × 8 columns (frames)**. Max
    frames in any state = 8, hence 8 columns.
- **Format:** PNG or WebP. **Min 256×256**, recommended **1536×1872**.
- Each **row = one animation state**; frames play left→right and loop.

### The 9 animation states (rows) — from `src/lib/pet-states.ts`

| row | id | frames | durationMs | purpose |
|----:|----|-------:|-----------:|---------|
| 0 | idle           | 6 | 1100 | neutral breathing + blink loop |
| 1 | running-right  | 8 | 1060 | locomotion to the right |
| 2 | running-left   | 8 | 1060 | locomotion to the left |
| 3 | waving         | 4 | 700  | greeting / attention gesture |
| 4 | jumping        | 5 | 840  | anticipation, lift, peak, descent, settle |
| 5 | failed         | 8 | 1220 | readable error / sad reaction |
| 6 | waiting        | 6 | 1010 | patient idle variant |
| 7 | running        | 6 | 820  | generic in-place run loop |
| 8 | review         | 6 | 1030 | focused inspecting / thinking loop |

Hermes maps agent activity → states: idle, running (tool use), thinking/review,
waving, finishing/celebrating, failing, waiting.

### pet.json (minimum the submit pipeline reads)

```json
{
  "id": "tiny-dino-1234",
  "displayName": "tiny dino #1234",
  "description": "one of 10k cc0 tiny dinos — now your Hermes pet"
}
```

Richer fields seen in the wild: `tags`, `vibes`, `kind`, `frameSize`, `animationStates`.
Frame timing/state layout is standardized by the renderer (the table above), not by pet.json,
so a conformant sheet "just works." Distribution: `petdex submit <folder>` (10/24h rate limit),
or hand the holder the folder to drop into `~/.codex/pets/`.

---

## 2. The source assets (this repo)

- **10,001 dinos**, native **16×16 pixel art**, stored as blocky **1600×1600** PNGs
  (each 100×100 block = one pixel). `build/common.py::_downsample16()` recovers the true
  16×16 grid by sampling cell centers (`x*100+50, y*100+50`).
- **Layered, named traits** — the key enabler. Per-token trait map in `metadata/traits.json`;
  per-trait PNGs in `images/traits/1600x1600/<category>/<value>.png`. Categories &
  layer order (bottom→top): `background, body, spikes, chest, feet, hands, head, face, eyes`.
  Each trait PNG is a full 16×16 frame with the part drawn in place + transparent elsewhere.
- **Pixel-exact compositor already exists**: `build/common.py::blend` / `composite_pixels`
  (integer source-over, matches Pillow + the on-chain renderer bit-for-bit).
- Transparent (no-background) dino renders already exist: `images/dinos/.../transparent/`.
- **1/1 uniques** (~15–16 special tokens incl. #10001) are flat single sprites — not
  decomposable into the standard layers.

---

## 3. The core challenge

The dinos are **static, single-pose** 16×16 art. The pet format wants a **9-state movement
suite**. So the real work is **synthesizing animation from a still** — and doing it
**10,001× consistently** and **on-brand** (crisp pixels, CC0 look).

The lever that makes this tractable: **dinos are not flat — they're separable named layers**
(`feet`, `hands`, `head`, `face`, `eyes`, `body`, ...). We can translate/squash/swap
individual layers per frame to build real walk/wave/jump cycles, instead of faking it on a
flat image. This is procedural rigging, not redrawing.

### Why not AI image generation?
img2img / sprite-diffusion can't hold pixel-exact CC0 identity across 10,001 tokens, is
expensive at that scale, and drifts off-style. Procedural layer animation is deterministic,
cheap, reproducible, and reuses the existing pipeline. (AI could be an optional "deluxe"
flavor later, not the canonical path.)

---

## 4. Recommended approach — procedural layer animation (PIL)

**Canvas math (clean integer scaling):** work on a **24 × 26 logical grid at 8× → 192 × 208**.
- `24·8 = 192`, `26·8 = 208` ✓ exact, nearest-neighbor (crisp pixels).
- Center the 16×16 dino horizontally (4 px margin each side); sit it on a baseline with
  ~6–8 px headroom above and a few below — room for run-bob, jump arc, wave arm extension,
  squash/stretch without clipping.

**Per-token pipeline (reuse `build/`):**
1. Downsample the token's trait PNGs to 16×16 (cached, already implemented).
2. For each of the 9 states, for each frame: place each layer onto the 24×26 logical canvas
   with that frame's per-layer transform (offset/squash/blink/swap), composite bottom→top
   with the existing integer `blend`.
3. Nearest-neighbor scale 8× → 192×208 frame.
4. Tile frames into the 9×8 sheet (1536×1872), pad unused columns transparent.
5. Emit `spritesheet.png` (+ optional `.webp`) and `pet.json`.

**Animation recipes (first pass — tune on a proof-of-concept):**
- **idle (6f):** 1–2 px body bob (sine), breathing squash/stretch, blink on 1 frame (hide/shrink `eyes`).
- **running-right/left (8f):** body bob + slight forward lean, alternate `feet` offsets, swing `hands` counter-phase; mirror horizontally for left.
- **running in-place (6f):** same gait, no net lean.
- **waving (4f):** hold body; oscillate `hands` (raise + wave); optional head tilt.
- **jumping (5f):** crouch-squash → stretch-launch → airborne (feet tucked) → descend → land-squash.
- **failed (8f):** slump/shrink, head dip, maybe a 1-px shake.
- **waiting (6f):** slower, smaller idle; occasional look-around (shift `eyes`/`face`).
- **review (6f):** lean-in, narrowed/scanning eyes, small head bob.

**1/1 uniques:** flat-sprite fallback — whole-sprite bob/squash/blink-free idle, jump, simple
run via vertical bounce + horizontal scoot. Document the visual compromise.

---

## 5. Scale, storage, compute

- **Per sheet:** 1536×1872 PNG of ~16-color upscaled pixel art compresses small. Est.
  ~30–80 KB PNG (smaller as WebP). 10,001 × ~50 KB ≈ **~0.5 GB**. Consider: store WebP, or
  ship a **generator** (render on demand) rather than committing 10k sheets to git.
- **Compute:** 10,001 tokens × 72 frames = ~720k frame composites. Pure-Python PIL is the
  slow path but parallelizable across cores; expect minutes→~1h for a full batch. A
  proof-of-concept (1 dino → full sheet) runs in well under a second.
- **Distribution options:**
  - (a) **On-demand generator**: a small CLI / web endpoint that takes a tokenId and returns
    `pet.json` + sheet. Cheapest to store, easiest to keep CC0/self-serve.
  - (b) **Pre-rendered pack**: all 10,001 committed (WebP) for bulk petdex submission / IPFS.
  - (c) **Hybrid**: render-on-demand now, batch-export later if there's demand.

---

## 6. Open decisions (need your call before full build)

1. **Backgrounds:** pets read best as transparent sprites over the desktop. Use the existing
   **transparent** dino layers (drop the `background` trait)? Or keep the bg as a static
   backdrop band? (Recommend: transparent.)
2. **Distribution:** generator-on-demand vs. pre-render all 10,001 vs. hybrid? (Recommend: build
   the generator first, prove one dino, then decide on bulk.)
3. **Scope of "game-ready":** the 9 petdex states already cover idle/run(L/R/in-place)/jump/
   wave/hurt/wait/think. Want extra game-only states too (attack, hurt-knockback, death,
   climb)? Those can live in extra rows beyond the petdex sheet for an engine, while the
   petdex sheet stays conformant.
4. **Fidelity bar:** ship clean procedural motion (deterministic, on-brand) as v1, or invest
   in hand-tuned per-archetype rigs (e.g. special-case the 11 head / 4 feet / 4 hands shapes)
   for nicer gaits?

---

## 7. Proposed phased plan

- **Phase 0 (this doc):** spec locked, worktree ready. ✅
- **Phase 1 — Proof of concept:** pick 2–3 dinos (one ordinary, one with hands+head traits,
  one 1/1). Build `build/pets/` generator: layer-aware animator → one `spritesheet.png` +
  `pet.json` per token. Visually review all 9 states (and as an animated preview/GIF).
- **Phase 2 — Tune recipes:** refine per-state motion + blink/wave/jump feel; handle layer
  edge cases (missing hands/head, uniques, tall heads clipping the canvas).
- **Phase 3 — Batch + package:** parallel render, WebP option, manifest; wire `petdex submit`
  flow and/or a tokenId→pet generator endpoint.
- **Phase 4 (optional) — game extras:** extra animation rows, engine-friendly export
  (Aseprite/JSON atlas, Godot/Unity import notes), direction variants.

Recommendation: start Phase 1 on a single dino so we can eyeball the motion before committing
to 10,001.
