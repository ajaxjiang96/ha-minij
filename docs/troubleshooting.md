# Troubleshooting

## Installation and authentication

Setup offers experimental phone/SMS login and an advanced existing-token
method. SMS login uses the captured app request format but still needs live
validation with the integration's WEBSITE headers. See [authentication evidence](authentication.md).

Submit an 11-digit mainland China mobile number without `+86` to send one SMS.
Entering the SMS screen or opening reauthentication does not send anything.
Codes and tokens are masked; only the validated token is saved.

- **Rate limited:** wait before requesting or exchanging a code again. There
  is no verified server cooldown, so the integration invents no timer.
- **SMS request unconfirmed/rejected:** a code may already have been sent.
  Avoid repeated submissions. An unsupported challenge requires the MiniJ app
  and advanced token setup; no challenge bypass is attempted.
- **Login rejected/unconfirmed:** check the code and wait before retrying.
  The integration makes no automatic retry or resend.
- **Account access check failed after code acceptance:** Retry only repeats
  profile/device reads using the returned token; it never exchanges the code again.
- **Different account:** reauthentication stops without changing the saved
  token. Start again with the original MiniJ account.

To change a number or request a new SMS, cancel the flow and start again.
A new login's effect on other app sessions is still unknown. If SMS login is
unsupported, use a session token from your own signed-in app. Do not post
phone numbers, codes, or tokens in an issue or send them to a maintainer.

If setup cannot connect, check Home Assistant's Internet access and try again
later. A cloud outage is separate from a rejected session. MiniJ error
`MJ01201018` means missing/invalid request headers in the observed response;
it is not an established token-expiration code.

## Device values

The integration reports controller values. Idle program/process fields may
describe a previous or default cycle rather than a selection in the mobile
app. Remaining time is not exposed until its behavior is verified.

Unknown binary values appear as unknown, not off. Unknown status aliases are
preserved. Record the public model, firmware, and corresponding app behavior
when reporting a new value. Do not infer a specific appliance fault from the
`device_exception` alias alone.

The current preview checks cloud freshness and whether the device remains
bound. Appliance-offline semantics need further validation; reported status
should not yet be treated as a verified physical connectivity indicator.

## Updates and removal

Back up your Home Assistant configuration before changing custom integrations.
Replace the `custom_components/minij` directory and restart Home Assistant.
Keep entity and device IDs unchanged when changing credentials or versions.

To remove the integration, delete its config entry in Settings → Devices &
services, remove `custom_components/minij`, and restart Home Assistant.

## Bug reports

Include integration and HA versions, installation type, public/internal model,
device/Wi-Fi firmware, reproduction steps, and redacted errors. Remove tokens,
verification codes, phone numbers, serials, account/device IDs, personal names,
Wi-Fi details, IP addresses, and identifying URLs. Never upload APKs, raw
account responses, or complete app/network captures.
