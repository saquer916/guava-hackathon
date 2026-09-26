#!/usr/bin/env bash
# Deterministically destroy and recreate the local synthetic OpenEMR.
# Deletes ONLY this project's Compose volumes (guava-openemr-local_*).
# Usage: infra/openemr/reset.sh --yes-destroy-local-synthetic-data
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
compose=(docker compose --project-directory "$here" -f "$here/compose.yaml")

if [[ "${1:-}" != "--yes-destroy-local-synthetic-data" ]]; then
  echo "Refusing to reset without --yes-destroy-local-synthetic-data" >&2
  exit 64
fi
if [[ ! -f "$here/.env" ]]; then
  echo "Missing $here/.env; copy .env.example and set local-only values" >&2
  exit 65
fi

"${compose[@]}" config --quiet
"${compose[@]}" down --volumes --remove-orphans
"${compose[@]}" up -d --wait --wait-timeout 600

published="$("${compose[@]}" port openemr 443)"
case "$published" in
  127.0.0.1:*) ;;
  *) echo "OpenEMR is published on a non-loopback address: $published" >&2
     "${compose[@]}" down
     exit 66 ;;
esac

echo "OpenEMR is healthy on https://localhost:${published##*:} (loopback only)."
echo "Next: pin the certificate and run the CapabilityStatement probe (docs/openemr-local.md)."
