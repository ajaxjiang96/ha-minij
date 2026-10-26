"""Save a session token from a local MiniJ app log without printing it."""

import argparse
import os
import re
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("log", type=Path)
parser.add_argument(
    "--output", type=Path, default=Path("analysis/runtime/session-token.txt")
)
args = parser.parse_args()
tokens = re.findall(r'\btoken: "([^"\s]+)"', args.log.read_text())
if not tokens:
    raise SystemExit("No session token was found in the supplied app log")
args.output.parent.mkdir(parents=True, exist_ok=True)
with os.fdopen(
    os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
) as output:
    output.write(tokens[-1] + "\n")
print(f"Session token saved locally to {args.output.resolve()}")
