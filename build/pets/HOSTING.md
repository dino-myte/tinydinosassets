# Hosting the tiny dinos → Hermes pet site

The collection is fixed and every dino renders deterministically, so production is
**fully static** — no server to run. Immutable assets live on **Cloudflare R2**.

> **Architecture note (important):** the asset tree is ~60k files. **Cloudflare Pages
> can't hold it** (Free 20k-file cap, 100k on paid), so **assets must live on R2, not
> Pages.** The cleanest topology is a **single Cloudflare Worker on the apex domain**
> that (a) serves the tiny frontend via a static-assets binding, (b) streams `/pets/*`
> from a *private* R2 binding (no public bucket, no CORS), and (c) hosts the future
> agent-tool routes `/api/pet` + `/.well-known/ai-tool/*` on the same origin. This
> unifies the site, the assets, and the OpenSea agent tool behind one origin.
> Plain "R2 public bucket + Pages frontend" also works but needs a public bucket +
> CORS and splits origins. See the Worker sketch below.
>
> Free tier easily covers this: 1.7 GB ≪ 10 GB storage, ~60k upload PUTs ≪ 1M Class A
> ops/mo, **egress free**. One-time upload cost ≈ $0.

`server.py` is still handy for local dev / on-demand rendering, but isn't needed in
prod.

## What gets deployed

`python build/pets/static_export.py` builds a self-contained tree in
`build/pets/deploy/`:

```
deploy/
  index.html                 CDN-aware frontend
  manifest.json
  pets/tiny-dino-<id>/
    pet.json  atlas.json
    spritesheet.webp         lossless, 1536x1872, 9 petdex states
    spritesheet_game.webp    + attack/hurt/death/sleep (game engines)
    preview.webp             animated thumbnail for the site
    pet.zip                  installable pack (pet.json + spritesheet.webp)
```

Size: ~2.1 GB with game sheets, ~1.4 GB with `--no-game`. On R2 that's ~$0.05/mo
storage and **$0 egress**. (Encoding is lossless WebP — smallest *and* pixel-exact
for this art; lossy is both bigger and noisier here.)

## Cost & staying in the free tier

R2 free tier: 10 GB storage, 1M Class A ops/mo (writes/lists), 10M Class B ops/mo
(reads), **zero egress**. Our footprint:
- **Storage 2.1 GB** — fixed at what we upload, never grows on its own (~21% of free).
- **Class A ~60k** — basically just the one-time upload; re-syncs add ~60k each. <6%.
- **Class B (reads)** — the only traffic-driven number. The Worker uses the **edge cache**
  (Cache API + `immutable` headers), so each file is read from R2 **at most once per colo**
  and then served from cache (free, not a Class B op). Repeat views cost zero R2 ops, so
  this stays far under 10M except at extreme viral scale.

Net: realistically **$0/mo**. Cloudflare has **no hard auto-shutoff spend cap** for R2, so
the guardrails are: (1) the edge caching above, (2) the bucket is **private** (only the
Worker reads it — no one can hammer R2 directly), (3) storage is small and fixed, and
(4) set **billing/usage notifications** (dash → Manage Account → Notifications → add a
Billing alert) to email you if usage ever climbs. Worst-case overage is cents
($0.015/GB, $0.36/M reads).

## Topology (single Worker on dinomyte.xyz)

One Worker (`build/pets/wrangler.toml` + `src/worker.ts`) serves all three on one origin:
- frontend `index.html` via the static-assets binding (`./site`),
- `/pets/*` streamed from the **private** R2 bucket `tinydinos-pets` (no public URL, no CORS),
- `/api/pet` + `/.well-known/ai-tool/*` for the future OpenSea agent tool.

The frontend's `CDN_BASE` is set to `https://dinomyte.xyz`, so it fetches `/pets/...` on
the same origin. The R2 bucket stays private — only the Worker reads it.

## Two credentials

- **`wrangler login`** (OAuth) — for `wrangler r2 bucket create` and `wrangler deploy`.
- **An R2 S3 API token** (R2 → Manage API Tokens → *Object Read & Write*) — for the bulk
  asset upload, since there's no `wrangler` bulk-upload. Gives an Access Key ID + Secret +
  your Account ID.

## Deploy runbook

```bash
# 0. (done) render the static tree
python build/pets/static_export.py            # build/pets/deploy/ (~2.1 GB w/ game sheets)

# 1. auth for wrangler (run on your machine; OAuth stays local)
wrangler login

# 2. create the private bucket
cd build/pets && npx wrangler r2 bucket create tinydinos-pets

# 3. bulk-upload the ~60k asset files to R2 (needs the R2 S3 token)
export R2_ACCOUNT_ID=...   R2_BUCKET=tinydinos-pets
export AWS_ACCESS_KEY_ID=...  AWS_SECRET_ACCESS_KEY=...   # the R2 S3 token
bash deploy_r2.sh

# 4. deploy the Worker + bind the apex domain (zone already in your account)
npx wrangler deploy
```

After step 4, `https://dinomyte.xyz` serves the site and streams every pet from R2.
`deploy_r2.sh` sets `cache-control: immutable` on `/pets/**` (safe — per-token assets
never change) and is resumable (re-run to finish a partial upload).

## Optional: IPFS permanence

For CC0 durability you can also pin `deploy/pets/` to IPFS (e.g. `ipfs add -r`,
or a pinning service) and surface the CID. Set `CDN_BASE` to an IPFS gateway to
serve from there instead of / in addition to R2.

## Updating animations later

Re-run `static_export.py` (re-renders from source) and `deploy_r2.sh` (re-syncs).
Because per-token paths are immutable, bump a query string or path version only if
you change a token's output.
