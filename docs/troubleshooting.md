# Troubleshooting

## Installation and authentication

The current preview uses an existing MiniJ session token. It does not yet send
SMS or complete phone login. See [authentication evidence](authentication.md)
for the confirmed protocol and remaining validation work.

If setup rejects a token, obtain a replacement from your own account and use
the Home Assistant reauthentication form. It must belong to the same account.
Do not post the token in an issue or send it to a maintainer.

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
