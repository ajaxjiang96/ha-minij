# Validate a normal washer cycle

Goal: correlate the V6-XNB's physical behavior, MiniJ app display, and HA
reported values before adding completion automations, remaining time, or a
physical-offline indicator. Use a cycle you would normally run. Appliance
operation and firmware decisions remain yours.

## Prepare

Install the diagnostics development build, restart HA, and confirm the five
existing entities remain. Do not delete/recreate the integration. Record your
HA/integration versions and the washer's public model and firmware.

In **Settings → Devices & services → MiniJ**, use the existing entry's
three-dot menu → **Download diagnostics**. The export uses already-cached
readings and does not poll, log in, send SMS, or control the washer. Normal
polling remains once per minute. If the download option is absent, confirm
the new `diagnostics.py` file was copied and restart HA.

## Collect a small sequence

At each observation, note your local time, physical/app behavior, and the
HA status/program/process. Wait for the normal update if HA lags the app.
Download one diagnostics snapshot at these useful points:

| Point | What to compare |
| --- | --- |
| Before start | Idle state; whether program/process describe the last cycle |
| After your normal start | Status transition and active program |
| A normal stage change | Reported process against the app's current stage |
| Completion | Physical end/app completion against HA transition |
| Several minutes after completion | Whether idle values clear or persist |

A pause/cancel observation is optional, only if you would normally use it.
Do not create appliance faults, disconnect hardware, change firmware, trigger
rate limits, or revoke account sessions to produce evidence. If an error
naturally occurs, record its exact app message locally alongside the raw
status alias. `device_exception` alone does not establish a fault cause.

## Read the diagnostic snapshot correctly

The MiniJ `data` section contains:

- `captured_at`: UTC time of export, **not** the time the appliance changed
  state or the cached cloud data was last fetched.
- `entry_state`: HA's integration-entry lifecycle state.
- `last_cloud_refresh_success`: whether the coordinator's last refresh
  succeeded. False means cached values may be stale. Null means no coordinator
  is available; it is not a physical-offline value.
- `cached_devices`: model/type, firmware versions, the six allowlisted reported
  text fields, and the integer `reported_online_status` flag when provided.
  The flag is retained without interpreting its numeric values as online/offline.

No MiniJ token, phone, code, account/device identifier, serial, address, Wi-Fi
credentials, nickname, or arbitrary nested API fields are copied into this
section. Device records intentionally have no stable identifiers; do not infer
that list order tracks the same device between exports. HA adds its own system,
manifest, custom-integration, timing, and issue metadata around this section.
Review that wrapper before sharing; you can share only the MiniJ `data` section
and your public HA version if the extra system information is unnecessary.
Do not upload raw app logs, profile responses, or full network captures.

## Acceptance boundary

A complete correlated cycle can establish candidate start/stage/end meanings
for this model/firmware. Record observed aliases exactly, including unknowns;
do not guess enum mappings. This implementation does not yet label a
`working` → `resting` transition as successful completion: cancellation and
fault behavior have not been distinguished. It exposes no remaining-time
sensor or guessed physical-offline state.

After a normal HA restart, confirm the saved session still loads without SMS
and entity IDs/settings remain. Note whether the MiniJ app stayed signed in
after your SMS test. Observe natural authentication failures over time;
do not manufacture expiry. These results close the remaining session questions
separately from cycle-state validation.
