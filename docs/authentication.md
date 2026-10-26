# Authentication evidence and remaining session questions

Target: supplied Android MiniJ 1.7.1 (111), user-owned V6-XNB. Findings combine the earlier native trace, public web client, and the already-saved app-scoped log from the user's successful login on **2026-10-26, Asia/Shanghai**. This pass only read existing files: it did not navigate the emulator, send SMS, log in, log out, replace tokens, call an API, or send appliance commands.

## Confirmed SMS login sequence

| Step | Observed request | Evidence |
| --- | --- | --- |
| Request login code | `POST https://lilith.minij.com/api/captcha/sendSmsCaptcha`, JSON `{"phone":"<user input>","type":"login"}` | Runtime at 09:28:35–09:28:36: request URL at saved-log line 282/295, exact request fields at line 296, HTTP 200 at line 294. Native trace independently establishes POST and JSON body construction. |
| Exchange SMS code | `POST https://lilith.minij.com/api/login/loginByPhone`, JSON `{"captcha":"<user-entered SMS code>","phone":"<user input>"}` | Runtime at 09:28:47: URL at line 435/445, exact fields at line 446, HTTP 200 at line 444. Cached `JIResponse` at line 448 reports `success: true` and a User containing a token. |

The exact login SMS type is **`login`**. The earlier web-only `whitelist_group` finding is a different workflow and must not be used here. A redacted, structured extraction is saved in ignored `analysis/runtime/auth-events-redacted.json`; it retains source line numbers and times while excluding account identifiers, phone numbers, SMS codes, and token values. The raw log remains private under ignored `analysis/runtime/`.

SMS HTTP 200 alone does not expose its full business response; this log shows that the subsequent user-entered SMS code produced a successful login. The exact public-web header set and raw token transport are documented in [web-protocol.md](web-protocol.md). Those headers have been verified for authenticated profile/device reads by the root investigation, but an independent SMS/login call using `platform: WEBSITE` has **not** been tested. The native app's own headers for its successful SMS/login requests were not printed in this log.

## Challenge, throttling, and error boundary

The inspected login request contains only `phone` and `captcha`; the SMS request contains only `phone` and `type`. The log does not expose a challenge ID, image verification token, anti-abuse signature, or nonce for this successful sequence. This is a bounded observation of one login, not proof that challenges never occur. Retry limits, cooldown durations, SMS error codes, phone-number normalization/country-code rules, agreement requirements, and account lockout behavior remain unverified. Do not copy the whitelist web page's 60-second timer as an established login server limit.

## Session semantics established so far

- Successful phone login supplies a token inside the User payload. The observed token is an opaque, 40-character hexadecimal string, not a JWT with locally decodable claims. No token value is included here.
- The root investigation verified that this existing token, with the public web client headers, can read user profile and the user's bound appliance. Those reads did not require another SMS or login.
- The saved profile response includes a `token` field. Its top-level envelope is `data`, `errorCode`, `errorMessage`, `success`, and `traceId`. No expiration or refresh-token field is exposed in that inspected profile shape.
- Native code logs caching the successful User. This establishes caching activity, not its persistence duration or a refresh policy. Disk-cache behavior across a process/app restart was not exercised in this pass, to preserve the authenticated session.
- The bounded saved-log and native printable-string searches found no literal `refreshToken`, `refresh_token`, `expiresIn`, `expires_in`, `expireTime`, or `expiration`. This does not prove the service lacks refresh or expiry semantics; those may be in protected shell code, use different names, or be server-controlled.
- `login/logout` exists in native request routes. It was not called. Revocation, multiple simultaneous clients, session rotation on a new login, and logout effects on another client remain unknown.
- The earlier token-only HTTP 401 / `MJ01201018` was resolved by adding source-observed client headers. It is evidence of a header validation failure, **not** an expired-token error code.

## Next capture needed for a Home Assistant login flow

The request schemas and login SMS type are now established. Before treating an SMS config flow as verified, capture one **separately user-authorized** end-to-end login with the intended client headers and record redacted HTTP status, business success/error code, response field names, and whether a challenge is returned. Avoid repeated SMS attempts. Creating a new login may affect the current session; its rotation behavior is still unknown, so retain the existing token-based path until this can be checked deliberately.

For further passive app evidence, use the existing app PID (`adb -s emulator-5554 shell pidof -s com.minij.app`) and a bounded read-only `adb -s emulator-5554 logcat -d --pid=<current PID> -v threadtime`. Do not clear logcat, restart/clear the app, or log out just to obtain a new trace. Save raw output only under ignored `analysis/runtime/`; extract only route, field names, nonsecret enum constants, response status/error codes, and timestamps into reports. If a real user-triggered login is later needed, have the user operate the login UI and enter the SMS code; never include that code in recorded public fixtures.

For expiry, observe a naturally occurring authentication failure during an authorized read, retaining the HTTP status and MiniJ error code without exposing the token. Then verify the reauthentication flow with explicit user participation. Do not invent a token lifetime, refresh endpoint, automatic login retry, or expiry error mapping from the present evidence.

## Experimental integration flow

The integration now implements the captured request schemas with the existing
WEBSITE headers. It offers SMS and advanced token entry for both setup and
reauthentication. No real SMS/login was made during implementation. HTTP 429
has a dedicated rate-limit message; no cooldown duration, expiry code, or
refresh endpoint is invented. Unknown business rejection/challenge responses
stop setup. Unauthenticated POSTs omit any existing account token, prohibit
redirects, and never retry automatically.

A login token is validated through profile and bound-device reads before it is
saved. The stable user ID prevents duplicate accounts and different-account
reauthentication. Temporary read failures after code exchange retain the token
only in the active flow so Retry does not consume the code a second time.
Phone and code are not persisted. Existing entries need no data migration:
they continue to contain only the same session-token field.

Live acceptance still requires the account owner to submit their number and
code in the HA forms, confirm device visibility, and check the existing app
session afterward. Do not mark SMS compatibility, session rotation, expiry,
or renewal verified based only on fixture tests. Never deliberately revoke
or log out the existing session to manufacture an expiry observation.

The entry’s Reconfigure menu uses the same account check without requiring
expiry or entry removal. Follow [live acceptance](sms-acceptance.md) for the
account-owner test and restart/app-session checks.
