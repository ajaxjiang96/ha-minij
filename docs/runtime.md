# Android runtime evidence

Captured 2026-10-26 (Asia/Shanghai), targeting the user-owned MiniJ V6-XNB.

## Environment and actions

- Existing AVD: `Medium_Phone_API_36`, Android API 36 Google Play image, `arm64-v8a`.
- ADB serial: `emulator-5554`.
- The supplied APK contains an arm64 native library and is ABI-compatible with this AVD.
- No emulator was running. Started the existing AVD with `-no-snapshot-save -no-boot-anim`; its default boot snapshot was unavailable, so it cold-booted.
- Package `com.minij.app` was absent before install. `adb install /Users/ajax/Downloads/minij.apk` succeeded without replacing or clearing any prior installation.
- Launched the manifest-declared `com.minij.app.ui.login.SplashActivity` with `am start`; app process remained alive (observed PID 2494).

## Observed screen

First launch displays a User Agreement / Privacy Policy dialog headed `温馨提示`, with `不同意` and `同意并继续` choices, over a welcome screen with a login button. No consent choice was selected. No SMS, credentials, account action, or appliance command was sent. The crash log buffer had no entries at capture time.

Evidence:

- `analysis/runtime/minij-first-launch.png`: rendered launch screenshot (1080 x 2400).
- `analysis/runtime/minij-first-launch.xml`: UI Automator hierarchy identifying the consent dialog and buttons.
- `analysis/runtime/package-state.txt`: package installation state.
- `analysis/runtime/activity-state.txt`: activity state.
- `analysis/runtime/crash-log.txt`: empty crash buffer capture.
- `analysis/runtime/emulator.log`: emulator startup diagnostics.

## Initial handoff

The user needs to review and handle the displayed terms and sign in to their MiniJ account in the emulator. After the V6-XNB is visible, capture device-list and detail responses, establish authentication headers and token expiry behavior, and confirm actual model-specific status fields. Current evidence proves install and launch only; it does not establish API connectivity, successful login, account device visibility, or appliance control.

The emulator is intentionally left running at the consent dialog for this handoff. Neither the Android system proxy nor certificate trust was changed.

## Authenticated follow-up — 2026-10-26

The user signed in and authorized continued analysis. REA read process-scoped logcat for PID 2494; Evidence `ev_a78b1575ee6ce627e29d79dfda2433c73d8675fe010eb9e640c2df17c79cf6b7`. App logs contained a successful phone-login result, session token, and bound washer. Raw logs and account responses remain under ignored `analysis/runtime/`; the extracted token file has mode 0600. No token value is included in source, reports, or tests.

The agent dismissed optional nearby-device and notification prompts, entered the home screen, and captured `minij-home-ready.png` / `minij-home-ready.xml`. The screen shows the wall-mounted washer, `休息中` (resting), selected `筒自洁` (drum clean), and a 76-minute program estimate.

Authenticated reads with the exact public web client header set succeeded:

| Request | Result |
| --- | --- |
| GET `personal/getUserProfile` | HTTP 200, success true; stable userId verified locally |
| GET `device/getUserBindDeviceList` | HTTP 200, success true; one washer |
| GET `device/v2/getDeviceDetail?deviceId=…` | HTTP 200, success true; device status map |

Header source is documented in [web-protocol.md](web-protocol.md). A raw-token-only attempt returned HTTP 401 / `MJ01201018` / `请求头缺失或无效!`; adding the source-observed client headers resolved it. The integration's own aiohttp client subsequently read profile and device list successfully, independent of the initial urllib probe.

Observed appliance baseline:

- Public model supplied by user: V6-XNB; internal API model: `minij.washer.x68`, device type `washer`.
- Wi-Fi version `1.0253`, firmware `0 0003 1 0000`.
- `newOrOldAppOnlineStatus: 1` (other values not interpreted).
- `current_status_alias: resting`, `current_status: 休息中`.
- `current_mode: 标准`, `current_process: 主洗`, `child_lock_status: close`.
- `cloud_control_authorization: open`.
- Authorization description: if app remote control is needed, hold the device's Cloud Mode key for three seconds to authorize.
- `program_remain_time: 48`, `program_total_time: 48` despite the app's selected-program estimate of 76. These idle fields are not treated as validated active-cycle remaining time.

No system proxy/certificate changes, app instrumentation, extra login, appliance command, or firmware update was performed. The emulator is left signed in on the home screen. Session expiration, active-cycle values, offline semantics, and post-update behavior still require observation.
