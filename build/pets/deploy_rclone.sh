#!/usr/bin/env bash
# Upload the rendered pet assets (build/pets/deploy/pets/) to the PRIVATE R2 bucket
# via rclone — a single Go binary with no Python dependency (the Homebrew aws-cli is
# currently broken under Python 3.14). This is also Cloudflare's recommended tool for
# bulk R2 uploads. The Worker streams these on dinomyte.xyz/pets/* (bucket stays
# private; no public URL, no CORS).
#
# Configure the remote ONCE, in YOUR terminal (keeps the secret in
# ~/.config/rclone/rclone.conf, never in the shell/transcript):
#
#   rclone config create r2 s3 provider=Cloudflare \
#     access_key_id=<R2_ACCESS_KEY_ID> secret_access_key=<R2_SECRET> \
#     endpoint=https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com
#
# Then:  R2_BUCKET=tinydinos-pets bash build/pets/deploy_rclone.sh
set -euo pipefail

: "${R2_BUCKET:?set R2_BUCKET}"
REMOTE="${R2_REMOTE:-r2}"     # name of the rclone remote created above
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/build/pets/deploy/pets"

[ -d "$SRC" ] || { echo "missing $SRC — run: python build/pets/static_export.py"; exit 1; }

echo "uploading $SRC -> ${REMOTE}:${R2_BUCKET}/pets"
# rclone auto-sets Content-Type from each file's extension (webp/json/zip).
# --s3-no-check-bucket avoids a Class-A HeadBucket per run; resumable (re-run to finish).
rclone copy "$SRC" "${REMOTE}:${R2_BUCKET}/pets" \
  --header-upload "Cache-Control: public, max-age=31536000, immutable" \
  --s3-no-check-bucket --transfers 32 --checkers 64 --fast-list --progress

echo "done. Assets will serve at https://dinomyte.xyz/pets/tiny-dino-<id>/spritesheet.webp"
echo "Next:  (cd build/pets && npx wrangler deploy)"
