"""Build a manual-install archive containing only integration runtime files."""

import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "minij"


def main() -> None:
    version = json.loads((COMPONENT / "manifest.json").read_text())["version"]
    output = ROOT / "dist" / f"ha-minij-{version}.zip"
    output.parent.mkdir(exist_ok=True)
    files = sorted(
        path
        for path in COMPONENT.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix in {".py", ".json", ".png", ".svg"}
    )
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT))
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Archive verification failed")
        if not all(
            name.startswith("custom_components/minij/") for name in archive.namelist()
        ):
            raise RuntimeError("Unexpected archive member")
    print(f"Built {output.name}: {len(files)} files")


if __name__ == "__main__":
    main()
