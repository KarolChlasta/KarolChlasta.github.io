#!/usr/bin/env bash
# Download the self-hosted woff2 subsets. Run once; re-running is harmless.
#
# The site links no font CDN at runtime: no third-party request on page load,
# no silent fallback if a CDN changes, nothing to break in five years.
set -euo pipefail

DEST="$(cd "$(dirname "$0")/.." && pwd)/assets/fonts"
BASE="https://cdn.jsdelivr.net/npm/@fontsource"
mkdir -p "$DEST"

files=(
  "ibm-plex-sans@5/files/ibm-plex-sans-latin-400-normal.woff2"
  "ibm-plex-sans@5/files/ibm-plex-sans-latin-600-normal.woff2"
  "ibm-plex-sans@5/files/ibm-plex-sans-latin-ext-400-normal.woff2"
  "ibm-plex-sans@5/files/ibm-plex-sans-latin-ext-600-normal.woff2"
  "ibm-plex-mono@5/files/ibm-plex-mono-latin-400-normal.woff2"
  "ibm-plex-mono@5/files/ibm-plex-mono-latin-ext-400-normal.woff2"
  "source-serif-4@5/files/source-serif-4-latin-400-normal.woff2"
  "source-serif-4@5/files/source-serif-4-latin-ext-400-normal.woff2"
  "source-serif-4@5/files/source-serif-4-latin-400-italic.woff2"
  "source-serif-4@5/files/source-serif-4-latin-ext-400-italic.woff2"
)

for path in "${files[@]}"; do
  name="${path##*/}"
  curl -fsSL --max-time 30 -o "$DEST/$name" "$BASE/$path"
  printf '%8d  %s\n' "$(stat -c%s "$DEST/$name")" "$name"
done

echo "downloaded ${#files[@]} files to $DEST"
