"""Validate a release tag and produce explicit GitHub release flags."""

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def release_settings(root: Path, tag: str) -> dict[str, str]:
    """Support numeric stable versions and bN previews with matching notes."""
    version = json.loads((root / "custom_components/minij/manifest.json").read_text())[
        "version"
    ]
    if not isinstance(version, str) or not re.fullmatch(
        r"[0-9]+\.[0-9]+\.[0-9]+(?:b[1-9][0-9]*)?", version
    ):
        raise ValueError("只支持 X.Y.Z 稳定版和 X.Y.ZbN 测试版")
    if tag != f"v{version}":
        raise ValueError("标签必须与 manifest 版本一致")
    if not (root / f"docs/releases/{version}.md").is_file():
        raise ValueError("缺少对应版本的中文发布说明")
    beta = "b" in version
    return {
        "RELEASE_VERSION": version,
        "RELEASE_PRERELEASE": "true" if beta else "false",
        "RELEASE_LATEST": "false" if beta else "true",
        "RELEASE_KIND": "测试版" if beta else "集成",
    }


def main() -> None:
    """Write validated flags; never create a tag or publish from this script."""
    settings = release_settings(ROOT, os.environ["RELEASE_TAG"])
    with Path(os.environ["GITHUB_ENV"]).open("a") as output:
        for key, value in settings.items():
            output.write(f"{key}={value}\n")


if __name__ == "__main__":
    main()
