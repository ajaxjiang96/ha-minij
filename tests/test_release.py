"""Check that stable promotion cannot inherit preview publication flags."""

import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "minij_release", Path(__file__).parents[1] / "scripts/prepare_release.py"
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def prepare(tmp_path, version, *, notes=True):
    component = tmp_path / "custom_components/minij"
    component.mkdir(parents=True)
    (component / "manifest.json").write_text(json.dumps({"version": version}))
    if notes:
        folder = tmp_path / "docs/releases"
        folder.mkdir(parents=True)
        (folder / f"{version}.md").write_text("# 中文发布说明\n")


@pytest.mark.parametrize("version", ["0.1.1b1", "0.1.1b2", "0.1.1b10"])
def test_preview_stays_prerelease_and_never_latest(tmp_path, version):
    prepare(tmp_path, version)
    settings = release.release_settings(tmp_path, f"v{version}")
    assert settings["RELEASE_VERSION"] == version
    assert settings["RELEASE_PRERELEASE"] == "true"
    assert settings["RELEASE_LATEST"] == "false"


def test_stable_is_public_stable_channel(tmp_path):
    prepare(tmp_path, "0.1.1")
    settings = release.release_settings(tmp_path, "v0.1.1")
    assert settings["RELEASE_PRERELEASE"] == "false"
    assert settings["RELEASE_LATEST"] == "true"


@pytest.mark.parametrize("tag", ["0.1.1", "v0.1.1b2", "v0.1.2", "main"])
def test_wrong_tag_is_rejected(tmp_path, tag):
    prepare(tmp_path, "0.1.1")
    with pytest.raises(ValueError, match="标签"):
        release.release_settings(tmp_path, tag)


def test_missing_notes_are_rejected(tmp_path):
    prepare(tmp_path, "0.1.1", notes=False)
    with pytest.raises(ValueError, match="发布说明"):
        release.release_settings(tmp_path, "v0.1.1")


@pytest.mark.parametrize("version", ["0.1.1rc1", "0.1.1b0", "../private", 123])
def test_unsupported_version_never_reaches_publication(tmp_path, version):
    prepare(tmp_path, version, notes=False)
    with pytest.raises(ValueError, match="只支持"):
        release.release_settings(tmp_path, f"v{version}")
