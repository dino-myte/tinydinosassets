#!/usr/bin/env bash
# Upload the rendered pet assets (build/pets/deploy/pets/) to the PRIVATE R2 bucket.
# The Worker (wrangler.toml) streams them on dinomyte.xyz/pets/* — bucket stays
# private, so no public URL and no CORS needed. The frontend is served by the Worker's
# static-assets binding (./site), so we do NOT upload index.html/manifest here.
#
# R2 is S3-compatible. Set first:
#   R2_ACCOUNT_ID         your Cloudflare account id
#   R2_BUCKET             bucket name (tinydinos-pets)
#   AWS_ACCESS_KEY_ID     R2 access key id      (R2 -> Manage API Tokens, S3 key)
#   AWS_SECRET_ACCESS_KEY R2 secret access key
#
# Then:  bash build/pets/deploy_r2.sh
# Prereqs: awscli; bucket already created (npx wrangler r2 bucket create tinydinos-pets).
set -euo pipefail

: "${R2_ACCOUNT_ID:?set R2_ACCOUNT_ID}"
: "${R2_BUCKET:?set R2_BUCKET}"
# Credentials: either set AWS_ACCESS_KEY_ID/SECRET, or an AWS_PROFILE you stored with
# `aws configure --profile r2` (keeps the secret in ~/.aws/credentials, not the shell).
if [ -z "${AWS_PROFILE:-}" ]; then
  : "${AWS_ACCESS_KEY_ID:?set AWS_ACCESS_KEY_ID (or AWS_PROFILE)}"
  : "${AWS_SECRET_ACCESS_KEY:?set AWS_SECRET_ACCESS_KEY (or AWS_PROFILE)}"
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/build/pets/deploy"
ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

[ -d "$SRC/pets" ] || { echo "missing $SRC/pets — run: python build/pets/static_export.py"; exit 1; }

# Newer aws-cli (>=2.23) sends CRC32 integrity headers R2 can reject; force when_required.
export AWS_REQUEST_CHECKSUM_CALCULATION="when_required"
aws configure set s3.max_concurrent_requests 32 2>/dev/null || true

echo "syncing $SRC/pets -> r2://$R2_BUCKET/pets (endpoint $ENDPOINT)"
# Immutable, long-cache: assets never change for a fixed token. Content-Type is
# auto-derived by extension (webp/json/zip). Resumable — re-run to finish a partial upload.
aws s3 sync "$SRC/pets" "s3://${R2_BUCKET}/pets" \
  --endpoint-url "$ENDPOINT" \
  --cache-control "public, max-age=31536000, immutable" \
  --no-progress

echo "done. Assets will serve at https://dinomyte.xyz/pets/tiny-dino-<id>/spritesheet.webp"
echo "Deploy the Worker that streams them:  (cd build/pets && npx wrangler deploy)"
