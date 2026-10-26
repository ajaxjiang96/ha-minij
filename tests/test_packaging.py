"""Verify that the distributed ZIP works outside the source checkout."""

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_archive_installs_in_a_clean_homeassistant_directory(tmp_path):
    """Boot entities from extracted runtime files rather than the working tree."""
    import json

    subprocess.run(
        [sys.executable, str(ROOT / "scripts/package_integration.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    version = json.loads((ROOT / "custom_components/minij/manifest.json").read_text())[
        "version"
    ]
    with zipfile.ZipFile(ROOT / f"dist/ha-minij-{version}.zip") as archive:
        names = set(archive.namelist())
        for relative in (
            "__init__.py",
            "config_flow.py",
            "diagnostics.py",
            "manifest.json",
            "translations/en.json",
            "translations/zh-Hans.json",
            "brand/icon.png",
        ):
            assert f"custom_components/minij/{relative}" in names
        assert all(name.startswith("custom_components/minij/") for name in names)
        assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)
        archive.extractall(tmp_path)
    # Reuse the existing real-HA smoke test with only the installed component.
    # Its fixture resolves custom_components relative to this copied test file.
    (tmp_path / "tests").mkdir()
    shutil.copyfile(ROOT / "tests/test_homeassistant.py", tmp_path / "tests/test_ha.py")
    shutil.copyfile(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTEST_ADDOPTS", None)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_ha.py",
            "-k",
            "test_config_flow_entities_and_unload",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
