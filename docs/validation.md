# Validation — 2026-10-26

Test runtime: Home Assistant 2026.10.4, CPython 3.14.8 on macOS ARM64.

## Live appliance → Home Assistant

`analysis/runtime/live-homeassistant.py` exercised the actual config flow, API client, polling coordinator, entity platforms, and unload against the user's signed-in MiniJ account. It used real MiniJ GET requests for profile and device list; no API method was mocked. The harness supplied an externally owned aiohttp session through the Home Assistant session accessor so it could run without starting a web server or unrelated network discovery.

The process exited **0** and produced `analysis/runtime/live-homeassistant-summary.json`:

| Entity | Actual value |
| --- | --- |
| Status | `resting` |
| Reported program | `标准` |
| Reported process | `主洗` |
| Child lock enabled | `off` |
| Cloud control authorized | `on` |

One device was registered as `MiniJ`, model `minij.washer.x68`, software `1.0253 0 0003 1 0000`. Entry setup and unload both succeeded. This is real Home Assistant core/entity behavior with live appliance data. It is not a deployment or frontend acceptance test on the user's production Home Assistant installation.

## Automated tests

- **12 API transport tests pass, exit 0.** Local aiohttp server verifies the exact GET/header contract, profile data minimization, authentication rejection, malformed/duplicate device data, cloud errors, and refusal to follow redirects with credentials.
- **4 Home Assistant runtime tests pass their assertions**, covering config flow, five entities and device metadata, shared refresh, unknown binary values, removed devices, reauthentication, wrong-account rejection, duplicate account prevention, reload, and unload. After the assertions pass, the Python test process crashes during interpreter shutdown with exit 139 (one diagnostic run produced 138). These runs are not reported as a green suite.
- A separate baseline importing only Home Assistant's built-in `input_boolean`, with no MiniJ module or source path, creates an entity and stops successfully, then reproduces the same interpreter-finalization crash. Faulthandler reports CPython garbage collection / `dictkeys_decref` / module finalization. The exact native dependency or interpreter defect is not isolated. Baseline script/log: `analysis/runtime/ha-baseline-repro.py` and `.log`.
- Ruff lint and format checks, Python compilation, and all component JSON parsing pass.

The initial combined run reports **16 passed** before the same shutdown crash (exit 139), retained in `analysis/final-tests.log`. The initial archive contained 12 Python/JSON component files; the foundation archive adds the user-supplied MiniJ app icon unchanged. Packaging includes only `custom_components/minij/` runtime files, with archive integrity and absence of the live session token checked before delivery.

The live one-entry smoke test exits cleanly. No production workaround or forced process exit was added to conceal the separate test teardown failure.

Linux CI is configured but unexecuted. Local Docker image transfers fail with
TLS timeouts/EOF, so no Linux pass is claimed. See [foundation.md](foundation.md).

## Coverage limits

Live local API/HA checks established idle status on the user's V6-XNB. The
user's installed HA screenshot additionally shows `working` and a prior
`device_exception` transition; it does not establish a complete cycle or the
cause of that exception. Existing login logs establish SMS type `login` and
the phone/code request schemas. Independent SMS login using the intended HA
client headers, session lifetime/renewal, active-cycle timing, offline states,
controls, other models, and updated firmware remain unverified. The current
integration performs only reads.
