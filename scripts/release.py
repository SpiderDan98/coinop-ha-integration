# /// script
# requires-python = ">=3.14.2"
# dependencies = []
# ///
"""Build the release asset for a version tag.

Usage: uv run scripts/release.py <tag> <integration folder> <output folder>

Writes <output folder>/coinop.zip with the integration's files at its root
(HACS unpacks it into custom_components/coinop/) and the tag as the
manifest's version, and prints `prerelease=<true|false>` for $GITHUB_OUTPUT.
"""

import json
from pathlib import Path
import re
import sys
import zipfile

# The canonical PEP 440 form of X.Y.Z, X.Y.ZbN or X.Y.ZrcN, which HA's loader
# and HACS both order correctly.
VERSION = re.compile(
    r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?P<pre>(b|rc)(0|[1-9]\d*))?"
)
PANEL_BUNDLE = "frontend/coinop-panel.js"


def main(tag: str, integration: Path, output: Path) -> None:
    if not (version := VERSION.fullmatch(tag)):
        sys.exit(f"{tag!r} is not a release version like 1.2.0, 1.2.0b1 or 1.2.0rc1")
    if not (integration / PANEL_BUNDLE).is_file():
        sys.exit(
            f"{PANEL_BUNDLE} is missing: run `npm ci && npm run build` in frontend/"
        )
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((integration / "manifest.json").read_text())
    with zipfile.ZipFile(output / "coinop.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(integration.rglob("*")):
            name = path.relative_to(integration).as_posix()
            if (
                path.is_file()
                and name != "manifest.json"
                and "__pycache__" not in path.parts
            ):
                zf.write(path, name)
        zf.writestr(
            "manifest.json", json.dumps({**manifest, "version": tag}, indent=2) + "\n"
        )
    print(f"prerelease={str(bool(version['pre'])).lower()}")


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]))
