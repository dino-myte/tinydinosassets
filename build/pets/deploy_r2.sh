#!/usr/bin/env bash
# Sync the static export (build/pets/deploy/) to a Cloudflare R2 bucket.
#
# R2 is S3-compatible, so we use the AWS CLI. Set these env vars first:
#   R2_ACCOUNT_ID        your Cloudflare account id
#   R2_BUCKET            target bucket name (e.g. tinydinos-pets)
#   AWS_ACCESS_KEY_ID    R2 access key id      (from R2 API token)
#   AWS_SECRET_ACCESS_KEY R2 secret access key
#
# Then:  bash build/pets/deploy_r2.sh
#
# Prereqs: awscli installed; bucket created with public access (or a custom domain)
# and CORS allowing GET from your Pages origin (see HOSTING.md).
set -euo pipefail

: "${R2_ACCOUNT_ID:?set R2_ACCOUNT_ID}"
: "${R2_BUCKET:?set R2_BUCKET}"
: "${AWS_ACCESS_KEY_ID:?set AWS_ACCESS_KEY_ID}"
: "${AWS_SECRET_ACCESS_KEY:?set AWS_SECRET_ACCESS_KEY}"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/build/pets/deploy"
ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

[ -d "$SRC" ] || { echo "missing $SRC — run: python build/pets/static_export.py"; exit 1; }

echo "syncing $SRC -> r2://$R2_BUCKET (endpoint $ENDPOINT)"

# Immutable, long-cache assets (sheets/json/zip/webp never change for a fixed token).
aws s3 sync "$SRC/pets" "s3://${R2_BUCKET}/pets" \
  --endpoint-url "$ENDPOINT" \
  --cache-control "public, max-age=31536000, immutable" \
  --no-progress

# The frontend + manifest: short cache so updates show up.
aws s3 cp "$SRC/index.html" "s3://${R2_BUCKET}/index.html" \
  --endpoint-url "$ENDPOINT" --content-type "text/html; charset=utf-8" \
  --cache-control "public, max-age=300"
aws s3 cp "$SRC/manifest.json" "s3://${R2_BUCKET}/manifest.json" \
  --endpoint-url "$ENDPOINT" --content-type "application/json" \
  --cache-control "public, max-age=300"

echo "done. If using the R2 public dev URL, assets are at:"
echo "  https://<your-r2-public-host>/pets/tiny-dino-<id>/spritesheet.webp"
echo "Set CDN_BASE in index.html (or host the frontend on Pages) — see HOSTING.md."
