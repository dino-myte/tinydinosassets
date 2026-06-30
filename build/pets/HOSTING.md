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
