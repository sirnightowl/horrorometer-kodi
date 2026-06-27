#!/usr/bin/env bash
# Build a distributable zip for the Kodi addon.
# Also regenerates docs/addons.xml from the addon's addon.xml so there's
# a single source of truth for addon metadata.
# Usage: ./build.sh [version]
# Output: dist/plugin.video.horrorometer-<version>.zip

set -euo pipefail

VERSION="${1:-}"
ADDON_DIR="plugin.video.horrorometer"
DIST_DIR="dist"
ADDON_XML="$ADDON_DIR/addon.xml"

# Read version from addon.xml if not specified
if [ -z "$VERSION" ]; then
  VERSION=$(grep -oP 'version="\K[^"]+' "$ADDON_XML" | head -1)
fi

echo "Building Horrorometer Kodi addon v$VERSION"

# Regenerate docs/addons.xml from the addon's addon.xml (single source of truth)
echo "<addons>" > docs/addons.xml
cat "$ADDON_XML" >> docs/addons.xml
echo "</addons>" >> docs/addons.xml
echo "Regenerated docs/addons.xml from $ADDON_XML"

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