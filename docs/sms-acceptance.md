# Live SMS acceptance on an existing Home Assistant installation

This is an account-owner test of the experimental flow, not a public-release
claim. Automated fixtures do not establish live login compatibility. Keep the
phone number, SMS code, token, and raw responses out of chat and GitHub.

## Install the test build

1. Use the `feat/sms-authentication` branch of
   [ha-minij](https://github.com/ajaxjiang96/ha-minij/tree/feat/sms-authentication).
   Generate an install archive with `python scripts/package_integration.py`,
   or use the locally prepared `dist/ha-minij-0.1.0.zip` from that branch.
   This file identifies a development build, not a tagged release.
2. Back up your HA configuration. Replace only the integration's
   `custom_components/minij` folder with this build, then restart HA.
   Do not delete the existing MiniJ entry or devices.
3. Confirm the existing five entities still appear and retain their IDs,
   custom names, area assignments, and automations. Record their IDs locally.
   Confirm the existing MiniJ mobile app can still see the washer.

## One deliberate login

1. Open **Settings → Devices & services → MiniJ**, open the existing entry's
   three-dot menu, and choose **Reconfigure**. Choose **Phone and SMS code
   (experimental)**. Opening either screen must not send an SMS.
2. Enter the same account's mainland China mobile number: 11 digits without
   `+86`. Submitting sends one SMS. A new login may invalidate another app
   session; this remains unverified, so perform the test when that is acceptable.
3. Enter the code only in HA's masked SMS field and submit once. Do not share
   it in this chat. If MiniJ returns a challenge or an unconfirmed result, stop
   and report only the HA error label. Avoid repeated sends or code guesses.
4. If login is accepted but account/device reads fail, use **Retry**. This
   repeats only those reads using the returned session; it sends no SMS and
   does not exchange the code again. If the account has no bound appliances,
   bind one using the official app before retrying.
5. On success, confirm the existing entry reloads, all five entities update,
   and the IDs/settings recorded earlier remain unchanged. Do not start or
   change an appliance cycle just for this login test.
6. Open the MiniJ mobile app and check whether its existing session still
   works. Report only whether it stayed signed in or asked you to log in.

## Restart and failure observations

Restart HA once after success and confirm the saved session loads without
another SMS. This establishes restart persistence, not a token lifetime.
If authentication naturally fails later, use the repair's Reauthenticate flow
and the same account. Do not replace the saved token with a fake value, call
logout, or revoke the live session to simulate expiry.

Wrong-account rejection, throttling, outages, and invalid response shapes are
covered by automated tests. Do not trigger real rate limits or switch to
another person's account for acceptance. The server's expiry duration, refresh
mechanism, business expiry codes, and session-rotation rules remain unknown
until observed.

Report: HA version, build commit, whether SMS arrived, the HA error label or
success, five-entity visibility, unchanged entity IDs/settings, restart result,
and whether the mobile app stayed signed in. No screenshots of credentials or
raw logs are needed. A failed test leaves the original entry credentials
unchanged; use advanced token Reconfigure if a fresh app token is needed.
