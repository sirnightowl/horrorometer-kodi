#!/usr/bin/env bash
# Build a distributable zip for the Kodi addon.
# Usage: ./build.sh [version]
# Output: dist/plugin.video.horrorometer-<version>.zip

set -euo pipefail

VERSION="${1:-}"
ADDON_DIR="plugin.video.horrorometer"
DIST_DIR="dist"

# Read version from addon.xml if not specified
if [ -z "$VERSION" ]; then
  VERSION=$(grep -oP 'version="\K[^"]+' "$ADDON_DIR/addon.xml" | head -1)
fi

echo "Building Horrorometer Kodi addon v$VERSION"

# Clean and create dist
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

# Create the zip (zip the addon directory, preserving the top-level folder name)
cd "$(dirname "$0")"
zip -r "$DIST_DIR/$ADDON_DIR-$VERSION.zip" "$ADDON_DIR" \
  -x "*.DS_Store" "**/__pycache__/*" "**/*.pyc"

# Also copy to docs for GitHub Pages download
cp "$DIST_DIR/$ADDON_DIR-$VERSION.zip" "docs/$ADDON_DIR-$VERSION.zip"

echo ""
echo "Done. Output: $DIST_DIR/$ADDON_DIR-$VERSION.zip"
echo "GitHub Pages download: docs/$ADDON_DIR-$VERSION.zip"