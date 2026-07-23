#!/usr/bin/env bash
# Batched iptv-org grab by site (GitHub Actions / Linux)
set -euo pipefail

export NODE_OPTIONS="${NODE_OPTIONS:---max-old-space-size=1536}"
DAYS="${EPG_DAYS:-2}"
MAX_CONN="${EPG_MAX_CONNECTIONS:-2}"

ROOT="$(cd "$(dirname "$0")" && pwd)"
EPG_DIR="${EPG_DIR:-$ROOT/iptv-org-epg}"
BY_SITE="$ROOT/iptv-org-work/by_site"
OUT_DIR="$ROOT/iptv-org-work/site_guides"
mkdir -p "$OUT_DIR"

SITES=(
  tvpassport.com
  pluto.tv
  xumo.tv
  tvguide.com
  plex.tv
  i.mjh.nz
  watchyour.tv
  gatotv.com
  ontvtonight.com
  watch.whaletvplus.com
  distro.tv
  mi.tv
)

cd "$EPG_DIR"

for site in "${SITES[@]}"; do
  safe="${site//[^a-zA-Z0-9._-]/_}"
  channels="$BY_SITE/${safe}.channels.xml"
  if [[ ! -f "$channels" ]]; then
    echo "SKIP missing $channels"
    continue
  fi
  out_xml="$OUT_DIR/${safe}.xml"
  out_gz="$OUT_DIR/${safe}.xml.gz"
  echo "=== GRAB $site (days=$DAYS) ==="
  npm run grab --- \
    --channels="$channels" \
    --output="$out_xml" \
    --gzip="$out_gz" \
    --days="$DAYS" \
    --maxConnections="$MAX_CONN" \
    --timeout=20000 || echo "WARN grab failed for $site"
done

echo "All site grabs finished"
