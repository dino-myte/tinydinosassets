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

## One-time setup

1. **Create an R2 bucket** in the Cloudflare dashboard, e.g. `tinydinos-pets`.
2. **Make it publicly reachable** — either enable the R2 "Public Development URL",
   or (recommended) connect a **custom domain** like `pets.tinydinos.xyz`.
3. **CORS** (R2 → bucket → Settings → CORS) so the Pages origin can fetch assets:
   ```json
   [{ "AllowedOrigins": ["*"], "AllowedMethods": ["GET"], "AllowedHeaders": ["*"] }]
   ```
4. **R2 API token** (R2 → Manage API Tokens) → use its key id/secret as
   `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`.

## Deploy

```bash
# 1. render the static tree (once; re-run only if animations change)
python build/pets/static_export.py            # or: --no-game to halve size

# 2. point the frontend at your public assets host
#    edit build/pets/site/index.html -> set CDN_BASE, e.g.
#    const CDN_BASE = "https://pets.tinydinos.xyz";
#    then re-run static_export so deploy/index.html picks it up.

# 3. sync to R2 (S3-compatible; needs awscli)
export R2_ACCOUNT_ID=...   R2_BUCKET=tinydinos-pets
export AWS_ACCESS_KEY_ID=...  AWS_SECRET_ACCESS_KEY=...
bash build/pets/deploy_r2.sh
```

`deploy_r2.sh` sets `cache-control: immutable` on `/pets/**` (safe — assets never
change per token) and a short cache on `index.html` / `manifest.json`.

## Frontend hosting (two options)

- **Simplest:** serve `index.html` straight from the R2 bucket root (it's already
  synced). Visit your public bucket URL.
- **Recommended:** deploy the frontend on **Cloudflare Pages** for a clean apex
  domain and instant cache invalidation:
  - Pages project → upload `build/pets/deploy/index.html` (or point Pages at the
    repo with build output dir `build/pets/deploy`).
  - Keep `CDN_BASE` pointing at the R2 assets host.

## Optional: IPFS permanence

For CC0 durability you can also pin `deploy/pets/` to IPFS (e.g. `ipfs add -r`,
or a pinning service) and surface the CID. Set `CDN_BASE` to an IPFS gateway to
serve from there instead of / in addition to R2.

## Updating animations later

Re-run `static_export.py` (re-renders from source) and `deploy_r2.sh` (re-syncs).
Because per-token paths are immutable, bump a query string or path version only if
you change a token's output.
