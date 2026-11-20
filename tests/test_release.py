"""The release script the tag workflow runs: tag check, stamped manifest, zip."""

import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "release.py"
MANIFEST = {"domain": "coinop", "name": "Coin-op", "version": "0.0.0"}


@pytest.fixture
def integration(tmp_path: Path) -> Path:
    """An integration folder as the workflow sees it after building the panel."""
    folder = tmp_path / "custom_components" / "coinop"
    (folder / "frontend").mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps(MANIFEST, indent=2) + "\n")
    (folder / "__init__.py").write_text('"""Coin-op."""\n')
    (folder / "frontend" / "coinop-panel.js").write_text("export {};\n")
    return folder


def release(tag: str, integration: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, SCRIPT, tag, integration, integration.parents[1] / "dist"],
        capture_output=True,
        text=True,
        check=False,
    )


def zipped(integration: Path) -> zipfile.ZipFile:
    return zipfile.ZipFile(integration.parents[1] / "dist" / "coinop.zip")


def test_a_version_tag_zips_the_integration_with_the_tag_as_version(
    integration: Path,
) -> None:
    result = release("1.2.0", integration)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "prerelease=false\n"
    with zipped(integration) as archive:
        assert sorted(archive.namelist()) == [
            "__init__.py",
            "frontend/coinop-panel.js",
            "manifest.json",
        ]
        assert json.loads(archive.read("manifest.json")) == {
            "domain": "coinop",
            "name": "Coin-op",
            "version": "1.2.0",
        }
    assert json.loads((integration / "manifest.json").read_text()) == MANIFEST


@pytest.mark.parametrize("tag", ["0.3.0b1", "1.1.0b12", "2.0.0rc1"])
def test_beta_and_release_candidate_tags_are_prereleases(
    integration: Path, tag: str
) -> None:
    result = release(tag, integration)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "prerelease=true\n"
    with zipped(integration) as archive:
        assert json.loads(archive.read("manifest.json"))["version"] == tag


@pytest.mark.parametrize(
    "tag",
    [
        "v1.0.0",
        "1.0",
        "1.0.0.0",
        "01.0.0",
        "1.0.0-beta.1",
        "1.0.0beta1",
        "1.0.0b",
        "1.0.0a1",
        "1.0.0.dev1",
        "1.0.0.post1",
        "1.0.0+local",
        "latest",
    ],
)
def test_a_tag_that_is_no_release_version_fails_without_an_asset(
    integration: Path, tag: str
) -> None:
    result = release(tag, integration)

    assert result.returncode != 0
    assert tag in result.stderr
    assert not (integration.parents[1] / "dist" / "coinop.zip").exists()


def test_without_the_built_panel_there_is_no_asset(integration: Path) -> None:
    (integration / "frontend" / "coinop-panel.js").unlink()

    result = release("1.2.0", integration)

    assert result.returncode != 0
    assert "coinop-panel.js" in result.stderr
    assert not (integration.parents[1] / "dist" / "coinop.zip").exists()


def test_bytecode_caches_stay_out_of_the_asset(integration: Path) -> None:
    (integration / "__pycache__").mkdir()
    (integration / "__pycache__" / "__init__.cpython-314.pyc").write_bytes(b"\0")

    release("1.2.0", integration)

    with zipped(integration) as archive:
        assert not [name for name in archive.namelist() if "pycache" in name]
