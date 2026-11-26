#!/usr/bin/env bash
# Build the Kodi ZIP and refresh the GitHub Pages download and metadata.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

python3 - "${1:-}" <<'PY'
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile

addon = Path("plugin.video.horrorometer")
manifest = ET.parse(addon / "addon.xml").getroot()
version = manifest.attrib["version"]
if sys.argv[1] and sys.argv[1] != version:
    raise SystemExit(f"Version {sys.argv[1]} does not match addon.xml ({version}).")

files = [addon / "addon.xml", addon / "main.py"]
files.extend(addon / asset.text for asset in manifest.findall(".//assets/*"))
for path in [*files, Path("LICENSE")]:
    if not path.is_file():
        raise SystemExit(f"Missing package file: {path}")

dist = Path("dist")
dist.mkdir(exist_ok=True)
output = dist / f"{addon.name}-{version}.zip"
with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as package:
    for source, destination in [(path, path) for path in files] + [
        (Path("LICENSE"), addon / "LICENSE"),
    ]:
        entry = zipfile.ZipInfo(destination.as_posix())
        entry.external_attr = 0o100644 << 16
        package.writestr(entry, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)

index = ET.Element("addons")
index.append(manifest)
ET.indent(index)
ET.ElementTree(index).write("docs/addons.xml", encoding="UTF-8", xml_declaration=True)
download = Path("docs") / output.name
download.write_bytes(output.read_bytes())
print(f"Built {output} and {download}")
PY
