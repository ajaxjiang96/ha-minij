# MiniJ for Home Assistant

<img src="custom_components/minij/brand/icon.png" alt="MiniJ app icon" width="80">

An unofficial, read-only integration for MiniJ cloud-connected appliances.
Verified with the **V6-XNB** wall-mounted washer/dryer (`minij.washer.x68`).

This is an advanced preview. Setup offers experimental phone/SMS login and
an advanced session-token method. The SMS wire format comes from a successful
app login; independent SMS login with this integration still needs live validation. The integration
depends on MiniJ cloud and does not provide local control.

## Features and support

| Entity | Reported value |
| --- | --- |
| Status | Controller status alias and original status label |
| Reported program | Controller-reported program |
| Reported process | Controller-reported cycle stage |
| Child lock enabled | Explicit open/close state |
| Cloud control authorized | Explicit authorization state |

One shared request updates devices every 60 seconds. Unknown binary values
remain unknown. Entity IDs are stable across token changes; rejected sessions
trigger reauthentication for the same account.

V6-XNB was tested with Wi-Fi `1.0253` and device firmware `0 0003 1 0000`,
including `resting`, `working`, and `device_exception` observations. Other
models and firmware remain unverified.

## Installation

Requires Home Assistant **2026.10.4+**; the tested runtime is 2026.10.4.

1. Copy `custom_components/minij` into your HA configuration's
   `custom_components/` directory. Alternatively generate a ZIP using
   `python scripts/package_integration.py` and extract it into your HA
   configuration directory.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → Add integration → MiniJ**.
4. Choose **Phone and SMS code (experimental)** or **Existing session token
   (advanced)**. Phone login currently accepts mainland China mobile numbers
   only: 11 digits without `+86`.
5. For SMS login, submit your phone number to send one code, then enter that
   code. Nothing sends automatically. If account/device validation fails
   after login, Retry repeats only the status reads. Cancel and restart to
   change the number or explicitly request another code; avoid repeated SMS.

A new login may affect your MiniJ app session; this remains unverified.
Unsupported challenges and rejected responses stop setup. If that happens,
use your existing app token instead. The integration does not guess cooldowns,
refresh tokens automatically, or log you out.

Tokens and SMS codes use masked fields. Only the validated session token is
stored in the HA config entry; the phone number and SMS code are not saved.
Reauthentication offers both methods and requires the original account. Use
the entry’s **Reconfigure** menu to change authentication explicitly without
removing devices.
Never paste a token into an issue. The advanced extraction method and
confirmed SMS request format are in [authentication.md](docs/authentication.md).

Source repository: [ajaxjiang96/ha-minij](https://github.com/ajaxjiang96/ha-minij).
The source layout and HACS metadata are prepared; this is not yet a tagged
release or a default HACS listing.

## Known limitations

- Phone/SMS setup is implemented but live acceptance, challenges, cooldowns,
  token lifetime, session rotation, and renewal remain unverified. HTTP 401/403
  on status reads triggers reauthentication; unknown business errors are not
  guessed to mean expiry. No refresh endpoint is assumed.
- Idle program/process fields may describe a previous/default cycle rather
  than a selection in the mobile app.
- Remaining time is omitted until countdown behavior and units are verified.
- Current availability reflects cloud freshness and device binding; physical
  offline behavior needs validation.
- `device_exception` alone does not identify a specific appliance fault.
- Controls, firmware management, LAN operation, and MQTT are outside this preview.

See [troubleshooting](docs/troubleshooting.md) for errors, upgrades, and removal.

## Development and evidence

See [CONTRIBUTING.md](CONTRIBUTING.md) for development, tests, and redacted
model reports. Automated tests need no app account or physical appliance.

- [Roadmap](docs/roadmap.md)
- [Foundation status](docs/foundation.md)
- [Validation results and limits](docs/validation.md)
- [Authentication](docs/authentication.md) and [live SMS test steps](docs/sms-acceptance.md)
- [Native HTTP trace](docs/native-http.md) and [public web client](docs/web-protocol.md)
- [Runtime evidence](docs/runtime.md) and [Rea tooling](docs/rea-setup.md)

Authored source uses the [MIT license](LICENSE). The user-supplied MiniJ app
icon and product names identify supported products; they are not relicensed
as original project artwork. This project is not affiliated with MiniJ.
