# Public MiniJ web HTTP protocol

Fetched public, unauthenticated assets on 2026-10-26:

- `https://app.minij.com/` → `analysis/web/index.html`
- `https://app.minij.com/js/index-ce2bc1d3.js` → `analysis/web/index-ce2bc1d3.js`
- `https://app.minij.com/js/utils-eefb2a10.js` → `analysis/web/utils-eefb2a10.js`

No credentials were included in these requests. No authenticated API requests or emulator interactions were performed in this investigation.

## Exact central-client headers

In `index-ce2bc1d3.js`, `de()` at character offsets 2970–3400 builds these default headers for an ordinary browser:

```json
{"platform":"WEBSITE","version":"1.3.0","spm":"","frp":""}
```

The central Axios wrapper `class Wn` at character offsets 29840–31124 creates its instance with `headers: {"X-Requested-With":"XMLHttpRequest", ...de()}`. `request(e)` sets `e.headers={token:ve.token||""}`; Axios merges per-request headers with defaults. The request interceptor sets `Content-Type` to `application/json`, except FormData uses `multipart/form-data`. The instance uses `https://lilith.minij.com` as its base URL; individual paths include `/api/` where needed.

Therefore the public web app's ordinary JSON request includes:

```text
X-Requested-With: XMLHttpRequest
platform: WEBSITE
version: 1.3.0
spm:
frp:
token: <raw user token, no Bearer prefix in this source>
Content-Type: application/json
```

These are direct source observations, not proof that every header is mandatory. The root investigation's `MJ01201018` missing/invalid-header response cannot be narrowed to one header without a separate controlled request.

## Embedded-app and mini-program alternatives

`de()` changes defaults according to browser user agent:

- UA contains `MinijApp`: `platform` becomes `APP_ANDROID` when it also contains `Android`, otherwise `APP_IOS`. `version`, `spm`, and `frp` are extracted from underscore-delimited UA tokens identified by `VERSION`, `SPM`, and `FRP`.
- WeChat mini-program: `platform` becomes `MINI_PROGRAM_ANDROID` or `MINI_PROGRAM_IOS`; `version` comes from URL `miniProgramVersion` with fallback `1.3.0`; `spm` and `frp` come from URL query parameters.

The Android app's literal UA/version values must come from its own runtime, not be inferred from this parser.

## Token source and signing boundary

`ho(e)` at character offsets 42856–43050 converts incoming `e.token`/`e.userId` to strings and stores them in `ve`. Startup obtains user data from the native `userData` DSBridge method inside `MinijApp`, or from `minijToken` URL query data in mini-program context. The ordinary browser fallback provides an empty token.

The inspected central `Wn` client does **not** construct a per-request signature, timestamp, nonce, hash, or token prefix. The bundle's `signature` occurrences found here belong to WeChat JS SDK initialization via `/wechat/officialAccount/createJsapiSignature`, not a generic MiniJ API signing interceptor. This conclusion covers the inspected wrapper; it does not rule out independent endpoint-specific logic in lazy-loaded chunks.

Exact source excerpts are saved as `analysis/web/header-defaults.snippet.js`, `http-client.snippet.js`, and `token-state.snippet.js`; offsets count decoded JavaScript characters. Main bundle SHA-256: `af76658a37b2d8ae766b59c4c9c332fdda30aa4411931e587caff7a0b709efac`. Shared HTTP dependency SHA-256: `1906af8cb1f48c58ab1be228bddcb58bde8adb8dd3366b5181e7d520a642bd45`.

## Follow-up: SMS type and device labels

Searched the main bundle and all 114 additional referenced route chunks fetched in `analysis/web/download-inventory.json` (572,374 additional bytes, excluding already-fetched dependencies and large UI/PDF/debug dependencies). This bounded search found one caller of the exported SMS function `Hn`/`cD`: `index-17fb4a34.js`, the whitelist-registration page. It sends `POST /api/captcha/sendSmsCaptcha` with `{phone: ..., type: "whitelist_group"}`. That is **not a login type** and must not be reused for phone login. The fetched web source contains no `loginByPhone` implementation; main startup obtains authenticated data through native/mini-program bridging. A login SMS type remains unresolved from these web artifacts.

No clean washer status enum map for `current_status`, `current_process`, `current_mode`, `program_remain_time`, or `child_lock_status` was found in these fetched route chunks. This is not evidence that no such map exists elsewhere.

The generic test-control page `control-ea29331d.js` does show a server-driven alternative: it fetches `/deviceIntelligentControlSetting/findTestDeviceDetail` with `deviceId`, then displays `buttonList`, `switchList`, `chooseList`, and `queryList`. Each item includes `code`, `name`, `value`, and `valueList`; UI display selects `valueList.find(option => option.value === item.value)?.label`, falling back to the raw value. This proves a dynamic code-to-label UI pattern, not washer code meanings or this endpoint's accessibility for ordinary users. Its write instruction endpoint and manual-query operation were not exercised.

For Home Assistant, prefer actual device detail metadata and captured value/label pairs for the user's appliance. Do not derive status names from arbitrary integer values or reuse whitelist SMS parameters.

## Later runtime evidence resolves the login SMS type

The subsequent retrospective inspection of the already-saved user-operated login log established `type: "login"` for `captcha/sendSmsCaptcha`, followed by `login/loginByPhone` with `phone` and `captcha` and a successful User/token result. See [authentication.md](authentication.md) for source line references and limitations. This resolves the earlier web-only uncertainty; it does not turn the whitelist page's `whitelist_group` type into a login option. No new SMS, login, or session change was made to obtain this evidence.
