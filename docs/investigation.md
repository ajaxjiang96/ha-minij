# V6-XNB investigation

## Identity and evidence

- Target model: **V6-XNB**, supplied by the user; authenticated device record reports `minij.washer.x68` and `washer`.
- APK source: `/Users/ajax/Downloads/minij.apk`.
- APK SHA-256: `526257fb35167b8fe03db087440d193aff49e0f4f9a35d2385c8b613534d6473`.
- Package/version: `com.minij.app` / 1.7.1 (111), from the JADX-decoded manifest.
- Native core: `lib/arm64-v8a/libbloc.so`, SHA-256 `d5acc1f30c00aff1f6d4bbaf0d39f0cc45077ed6572a17becaea5fb6010f76a9`.
- Native/core architecture: ELF64 ARM64; Rust symbols, Crux effect types, and UniFFI exports are present.
- Protection: manifest selects `com.stub.StubApp`; the DEX exposes this loader, resource class, and Tianyu helper classes. `assets/libjiagu_a64.so` is present. Static Java inspection has not recovered the API shell implementation.

## Questions and status

| Question | Status | Evidence / remaining work |
| --- | --- | --- |
| Is Rea usable here? | Answered | Installation, scoped doctor, and real MCP self-test pass. MCP tools are now connected; app-scoped logcat was read through REA. |
| Can this APK be inventoried? | Answered | REA inventory: 2,400 archive occurrences; raw evidence retained locally. |
| Where is the application protocol? | Partially answered | Rust core exposes concrete HTTP paths; protected shell behavior remains unresolved. |
| How are login requests constructed? | Partially answered | Native and logged POST JSON schemas proven; SMS type `login` recovered. Token + public web client headers verified for reads. Independent SMS using HA client headers, challenges, and expiry/refresh remain unknown. |
| How are bound devices read? | Answered for this account | HTTP 200, `success: true` for profile, bound devices, and v2 detail. One washer returned. |
| Can the app run on the emulator? | Answered | User signed in on `emulator-5554` (ARM64 API 36); appliance home screen rendered. See [runtime evidence](runtime.md). |
| Which fields does V6-XNB return? | Answered for initial states | Live idle fields and the user's installed HA `working` / `device_exception` screenshot are observed. Full cycle, timing, and exception semantics remain unverified. |
| Are local LAN control or MQTT supported? | Unresolved | BLE provisioning and WebSocket clues do not establish a local control protocol. |
| Does a Home Assistant integration work? | Answered for local live core runtime | Real config flow, coordinator, five entities and unload succeeded using live appliance GETs; smoke process exited 0. Separate automated-test teardown limitation is documented in [validation.md](validation.md). No deployed HA instance was supplied. |

## Device/status clues

Native serialized metadata contains fields including `deviceModel`, `deviceSerialId`, `newOrOldAppOnlineStatus`, `deviceCharacterMap`, `current_status`, `current_mode`, `current_process`, `child_lock_status`, `program_remain_time`, `program_total_time`, and `fault_code`.

These are application-wide fields. Their presence is not proof that V6-XNB supports them, that their units are minutes, or that any numeric enum has a particular meaning. `scripts/inspect_apk.py` emits exact file offsets for a bounded selection; native assembly and pointer/length evidence establish request boundaries separately.

## Next evidence needed

1. SMS type `login` is confirmed. Verify the intended HA client headers through a separately authorized login, then session lifetime, challenges, and renewal behavior. The unrelated whitelist SMS type does not apply.
2. Compare actual device detail while idle and during a normal cycle to establish status enums, offline behavior, and duration units.
3. Before any firmware update, retain this baseline: `wifiVersion: 1.0253`, `firmwareVersion: 0 0003 1 0000`, `cloud_control_authorization: open`. The API describes holding the physical Cloud Mode button for three seconds to authorize app control. No update was installed.
4. Validate the packaged integration on the user's actual Home Assistant instance, then add appliance controls only after tracing and verifying their request/response semantics.

The implementation follows Home Assistant's [config-flow](https://contributors.home-assistant.io/core/integrations/config-flow/) and [shared fetching/coordinator](https://contributors.home-assistant.io/core/integrations/fetching-data/) patterns and targets released 2026.10.4 APIs.

The user performed login in the emulator. The resulting session token was read from app-scoped logs for authorized status requests and retained only in ignored local files. No SMS was requested by the agent and no appliance command or firmware update was sent.
