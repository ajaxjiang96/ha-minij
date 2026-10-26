# Contributing

Changes should work end to end for a verified appliance. Include the model,
firmware, expected behavior, and evidence that supports a new field or command.
Preserve unknown values instead of guessing their meaning.

## Development

Use Python 3.14.2 or newer and an isolated environment:

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m ruff check custom_components tests scripts
.venv/bin/python -m ruff format --check custom_components tests scripts
.venv/bin/python -m pytest -q
.venv/bin/python scripts/package_integration.py
```

The automated tests use a local HTTP server and synthetic device/account
records. They require no MiniJ login and must not request SMS codes or operate
appliances. CI runs on Linux against the declared minimum and current released
Home Assistant versions. A successful test run must exit 0.

## Evidence and privacy

Keep raw analysis in the ignored `analysis/` directory. Submit minimal fixtures
with synthetic identifiers such as `test-account` and `washer-test-device`.
Remove session tokens, verification codes, phone numbers, serials, account and
device IDs, Wi-Fi information, IP addresses, personal names, and identifying
image/link URLs. Inspect the complete diff and staged file list before commit.
Do not commit APKs, decompiled vendor code, private captures, or local tooling.

Live account checks are separate from unit tests. Requesting an SMS, signing
out, revoking a token, operating an appliance, or installing firmware requires
the account/appliance owner's participation. Never encode a credential in a
test, screenshot, log message, issue, or pull request.

## Pull requests

Describe the user-visible problem and resulting behavior, then state what was
tested and any remaining evidence limits. Keep the change focused. Existing
entity IDs must remain stable when credentials, names, or reported state change.
Additional-model support needs appliance evidence and regression fixtures.

Report ordinary bugs or model observations using the issue templates. If a
credential was exposed, revoke it through the account provider before sharing
any report; do not paste it into a public issue.
