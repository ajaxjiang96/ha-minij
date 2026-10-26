"""Check read-only cloud access using the same client as the integration."""

import argparse
import asyncio
import getpass
from pathlib import Path

import aiohttp

from custom_components.minij.api import MinijClient


async def main(token: str) -> None:
    async with aiohttp.ClientSession() as session:
        client = MinijClient(session, token)
        await client.async_get_profile()
        devices = await client.async_get_devices()
        print(f"Authentication verified; {len(devices)} bound appliance(s).")
        for device in devices:
            values = device.get("deviceCharacterMap") or {}
            print(
                device.get("deviceModel"),
                "status:",
                values.get("current_status_alias"),
                "child lock:",
                values.get("child_lock_status"),
                "cloud authorization:",
                values.get("cloud_control_authorization"),
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token-file", type=Path)
    args = parser.parse_args()
    token = (
        args.token_file.read_text().strip()
        if args.token_file
        else getpass.getpass("MiniJ session token: ").strip()
    )
    asyncio.run(main(token))
