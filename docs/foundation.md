# Open-source foundation status

Prepared 2026-10-26. The user selected `ajaxjiang96/ha-minij` as the public
repository and explicitly requested its creation.

## Prepared locally

- Git initialized with a minimal main base and review branch
  `feat/open-source-foundation`.
- MIT license, authored source, sanitized synthetic tests, contribution
  instructions, troubleshooting, and bug/model-report templates.
- HACS metadata, maintainer, and documentation/issue URLs targeting the
  requested repository. Those URLs become usable once creation succeeds.
- User-supplied MiniJ app icon in the component's `brand/` folder, copied
  unchanged. The obsolete placeholder artwork was removed.
- Reproducible manual-install ZIP containing only runtime files.
- Commit-pinned GitHub Actions for minimum/current released HA tests on
  Linux, Ruff, hassfest, HACS validation, and package verification.
- Dependabot configuration for action and Python dependency updates.

Private analysis, APKs, raw logs, credentials, captures, local tooling, and
environments remain ignored. Staged source is audited against known private
credential/account/device values without printing those values.

## Publication

The public repository [ajaxjiang96/ha-minij](https://github.com/ajaxjiang96/ha-minij)
was created through the user's signed-in GitHub browser session after the
proxy stabilized. The earlier connection EOF and `ERR_CONNECTION_CLOSED`
errors did not establish an invalid credential. SSH authentication succeeds
with password prompts and Keychain use explicitly disabled.

Publication uses a review branch and pull request; no merge or release is
performed as part of this foundation work.

## Linux validation

Initial image transfers failed during the proxy disruption. After recovery,
the official Python image was downloaded with manifest, config, layer, and
uncompressed layer digest verification, then imported into the local Docker
daemon. Only component source, synthetic tests, test configuration, and test
requirements are mounted read-only; private analysis and account files are excluded.
The actual test result is recorded in [validation.md](validation.md).

The complete Linux command exited 0: Home Assistant 2026.10.4, Python 3.14.9,
Ruff lint/format, and all 16 tests passed. The earlier macOS finalization
failure did not reproduce in this Linux run.

The first public image pull invoked Docker's existing credential helper and
was cancelled. Subsequent probes used an isolated configuration containing
only `{}`, with no credentials or helpers. No password was entered and the
user's global Docker configuration and Keychain were not changed.

## Release boundary

Inspect all hosted jobs and resolve failures before claiming green CI.
The first stable release remains gated on the roadmap's authentication,
state semantics, and independent installation evidence.

The exact SMS login type is now confirmed as `login`. Independent login
using the intended HA headers, challenge handling, and session lifetime
still require deliberate account-owner validation; the current session was preserved.
