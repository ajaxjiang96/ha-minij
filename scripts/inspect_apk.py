#!/usr/bin/env python3
"""Record APK identity and exact locations of MiniJ native protocol clues.

Reads archive bytes only; never executes the APK or contacts a service.
Matches are literal byte observations, not recovered request semantics.
"""

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

NEEDLES = (
    "https://lilith.minij.com/api/",
    "https://lilith-test-api.minij.com/api/",
    "wss://lilith.minij.com/",
    "https://app.minij.com/",
    "login/loginByPhone",
    "captcha/sendSmsCaptcha",
    "personal/getUserProfile",
    "device/v3/getDeviceInputBySnHash",
    "device/v3/deviceFunctionSettings",
    "device/deviceOperate",
    "device/v2/deviceOperate",
    "program_remain_time",
    "current_status",
    "current_temperature",
    "cloud_control_authorization",
    "V6-XNB",
)


def inspect(apk: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    with apk.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    with zipfile.ZipFile(apk) as archive:
        members = archive.infolist()
        native_name = "lib/arm64-v8a/libbloc.so"
        native = archive.read(native_name)
        observations = []
        for needle in NEEDLES:
            encoded = needle.encode()
            offsets = []
            start = 0
            while (offset := native.find(encoded, start)) != -1:
                offsets.append(hex(offset))
                start = offset + len(encoded)
            observations.append({"literal": needle, "file_offsets": offsets})
        native_output = output / "libbloc.so"
        native_output.write_bytes(native)
        result = {
            "apk": {
                "path": str(apk.resolve()),
                "sha256": digest,
                "bytes": apk.stat().st_size,
                "member_count": len(members),
                "dex_members": [
                    m.filename for m in members if m.filename.endswith(".dex")
                ],
                "native_members": [
                    m.filename for m in members if m.filename.endswith(".so")
                ],
            },
            "native": {
                "archive_member": native_name,
                "sha256": hashlib.sha256(native).hexdigest(),
                "bytes": len(native),
                "extracted_path": str(native_output.resolve()),
                "literal_observations": observations,
            },
            "limitations": [
                "Offsets refer to native file bytes, not runtime addresses.",
                "Adjacent Rust literals need pointer/length references "
                "to establish boundaries.",
                "Literal presence does not establish execution, an HTTP verb, "
                "or field meaning.",
                "An absent literal is only absent from this selected native member.",
                "APK signature authenticity and runtime behavior are not verified.",
            ],
        }
    (output / "apk-facts.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--output", type=Path, default=Path("analysis/native"))
    args = parser.parse_args()
    facts = inspect(args.apk, args.output)
    print(f"APK SHA-256: {facts['apk']['sha256']}")
    print(f"Evidence: {(args.output / 'apk-facts.json').resolve()}")
