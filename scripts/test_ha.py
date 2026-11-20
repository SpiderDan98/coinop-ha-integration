# /// script
# requires-python = ">=3.14.2"
# dependencies = ["packaging"]
# ///
"""Run the tests against a Home Assistant release, each in its own venv.

Usage: uv run scripts/test_ha.py <minimum|stable|beta> [pytest args...]

The harness (pytest-homeassistant-custom-component) is cut from one HA release
and pins it exactly, so each target picks a harness release:
- minimum: the one pinning the minimum HA version from hacs.json
- stable: the newest one pinning a stable HA release
- beta: the newest one, which pins the current beta while a beta is out
"""

import json
from pathlib import Path
import subprocess
import sys
import tomllib
from typing import Any
import urllib.request

from packaging.requirements import Requirement
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
HARNESS = "pytest-homeassistant-custom-component"
# Must pin the HA version given as "homeassistant" in hacs.json.
MINIMUM_HARNESS_VERSION = "0.13.329"
TARGETS = ("minimum", "stable", "beta")


def pypi(path: str) -> Any:
    with urllib.request.urlopen(f"https://pypi.org/pypi/{path}/json") as response:
        return json.load(response)


def pinned_homeassistant(harness_version: str) -> Version:
    for line in pypi(f"{HARNESS}/{harness_version}")["info"]["requires_dist"]:
        requirement = Requirement(line)
        if requirement.name == "homeassistant":
            return Version(next(iter(requirement.specifier)).version)
    raise LookupError(f"{HARNESS} {harness_version} pins no homeassistant")


def harness_version(target: str) -> str:
    if target == "minimum":
        return MINIMUM_HARNESS_VERSION
    releases: dict[str, list[Any]] = pypi(HARNESS)["releases"]
    for version in sorted(releases, key=Version, reverse=True):
        if not releases[version]:
            continue
        if target == "beta" or not pinned_homeassistant(version).is_prerelease:
            return version
    raise LookupError(f"no {HARNESS} release for {target}")


def check_version(target: str, tested: Version) -> None:
    if target == "minimum":
        minimum = Version(json.loads((ROOT / "hacs.json").read_text())["homeassistant"])
        if tested != minimum:
            sys.exit(
                f"MINIMUM_HARNESS_VERSION pins HA {tested}, hacs.json says {minimum}"
            )
    elif target == "stable":
        latest = Version(pypi("homeassistant")["info"]["version"])
        if tested < latest:
            # GitHub Actions shows this as a warning annotation on the run.
            print(f"::warning::{HARNESS} lags HA {latest}; testing HA {tested}")


def main(target: str, pytest_args: list[str]) -> int:
    if target not in TARGETS:
        sys.exit(
            f"usage: uv run scripts/test_ha.py <{'|'.join(TARGETS)}> [pytest args]"
        )
    manifest = json.loads(
        (ROOT / "custom_components" / "coinop" / "manifest.json").read_text()
    )
    version = harness_version(target)
    tested = pinned_homeassistant(version)
    check_version(target, tested)
    print(f"Testing against Home Assistant {tested} ({HARNESS} {version})", flush=True)

    venv = ROOT / f".venv-{target}"
    subprocess.run(["uv", "venv", "--quiet", "--allow-existing", venv], check=True)
    # The test group's pins follow the locked HA; each target's HA pins its own.
    test_group = {
        Requirement(line).name
        for line in tomllib.loads((ROOT / "pyproject.toml").read_text())[
            "dependency-groups"
        ]["test"]
    } - {HARNESS}
    requirements = [f"{HARNESS}=={version}", *manifest["requirements"], *test_group]
    subprocess.run(
        ["uv", "pip", "install", "--quiet", "--python", venv, *requirements],
        check=True,
    )
    python = venv / "bin" / "python"
    return subprocess.run([python, "-m", "pytest", *pytest_args], cwd=ROOT).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "", sys.argv[2:]))
