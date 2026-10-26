# Native HTTP trace — MiniJ Android 1.7.1 (111)

Static observations from `analysis/native/libbloc.so`, extracted from the user-supplied APK. The library retains Rust symbols. This trace uses Apple's LLVM objdump, not REA decompilation. No target code was executed and no MiniJ requests were sent.

## Proven request construction

| Operation | Method and route | Evidence |
| --- | --- | --- |
| Phone/SMS login | POST `login/loginByPhone`, JSON keys `phone`, `captcha` | User `update` branch at `0x4ddf9c`; route fat-string at `0x719850` points to `0x110357`, length 18. `Http::post` call at `0x4ddfd8`. Key bytes at `0x10f30e` length 5 and `0x10f364` length 7 are copied, converted to JSON values, inserted in a BTreeMap. `body()` at `0x4de0e8`, `expect_json()` at `0x4de0f4`, then send. |
| Request SMS | POST `captcha/sendSmsCaptcha`, JSON keys `phone`, `type` | Route fat-string at `0x7198c8` -> `0x1103aa`, length 22; `Http::post` at `0x4df400`; key bytes `0x10f30e` length 5 and `0x1050bc` length 4; `body()` at `0x4df510`. The required `type` value is not established by this trace. |
| User profile | GET `personal/getUserProfile` | Route fat-string `0x719a58` -> `0x1104e0`, length 23; `Http::get` at `0x4de9a8`. |
| Bound devices | GET `device/getUserBindDeviceList` | Route fat-string `0x7160e0` -> `0x10dff9`, length 28; FullURL at `0x496964`, `Http::get` at `0x496978`, `expect_json` then send at `0x496990`. No route-specific body/query in this branch. |
| Device detail v2 | GET `device/v2/getDeviceDetail`, query `deviceId` | Route fat-string `0x716040` -> `0x10df7b`, length 25; `Http::get` at `0x499b5c`. Key bytes at `0x104ed0`, length 8, passed into a one-entry HashMap; `query` at `0x499ba4`; send at `0x499bdc`. |
| Device detail v3 | GET `device/v3/getDeviceDetail` | Route fat-string `0x716018` -> `0x10df62`, length 25; `Http::get` at `0x4a1328`. Parameters not traced here. |
| Bound device detail | GET `device/getUserBindDevice` | Fat-string `0x715ba0` -> `0x10da6e`, length 24; `Http::get` at `0x4a0298`. Parameters not traced here. |
| Washer buckets | GET `multiBucketWasher/getDeviceBucketList` | Fat-string `0x7160b8` -> `0x10dfd4`, length 37; `Http::get` at `0x4a18c0`. Parameters not traced here. |
| Fridge detail | GET `deviceFridgeWarehouse/findDeviceFridgeWarehouseDetail` | Fat-string `0x715fa0` -> `0x10def1`, length 53; `Http::get` at `0x49da10`. Parameters not traced here. |
| Fridge temperature | POST `deviceFridgeWarehouse/fridgeWarehouseTemperatureAdjust` | Fat-string `0x716388` -> `0x10e2cf`, length 54; `Http::post` at `0x4976c4`. Parameters not traced here. |
| Fridge function | POST `deviceFridgeWarehouse/functionOnOrOff` | Fat-string `0x716338` -> `0x10e27c`, length 37; `Http::post` at `0x49c600`. Parameters not traced here. |
| Fridge mode | POST `deviceFridgeWarehouse/fridgeWarehouseModeOnOff` | Fat-string `0x716360` -> `0x10e2a1`, length 46; `Http::post` at `0x4a0e9c`. Parameters not traced here. |

`FullURL::full_url` at `0x65c774` selects a base string using an environment state bit, then formats the base together with the supplied route. At `0x65c7ac`/`0x65c7b4` the constants resolve to `0x116888` length 29 (`https://lilith.minij.com/api/`) and `0x1168a5` length 38 (`https://lilith-test-api.minij.com/api/`). This proves compiled production/test alternatives, not the environment selected at runtime.

`RequestBuilder::body` at `0x5e35b4` calls `Body::from<serde_json::Value>` at `0x5e35f4`, then `copy_content_type_from_body` at `0x5e364c`. This supports JSON body construction, beyond the mere presence of field-name strings.

## Authentication remains incomplete

The user model includes a `token` field in serialized metadata, but this trace has **not** established the wire header name, prefix, expiry, refresh behavior, or any signing requirement. Do not assume `Authorization: Bearer` or a raw `token` header. Rust core requests are emitted as Crux effects, so Android shell code may add authentication or other headers. The protected Java app code remains a likely next boundary.

No SMS was requested, no account was accessed, and no appliance commands were sent. These are compiled paths, not proof of current server acceptance. A real request capture or a complete shell HTTP trace is still required before claiming a working integration.

## Reproduce and inspect

Raw disassembly is saved in `analysis/native/user-update.asm`, `device-update.asm`, `full-url.asm`, `http-builders.asm`, and `request-body.asm`. The matching `.annotated.asm` files add comments for adjacent ADRP/ADD constant pairs only; they do not infer register dataflow across branches.

`analysis/native/annotate-strings.py` maps ELF PT_LOAD segments and AArch64 RELATIVE relocations to recover Rust fat-string constants. All addresses above are ELF virtual addresses. `.data.rel.ro` virtual addresses differ from file offsets by `0x2000`; treating them as direct file offsets would give incorrect route attribution.

## Focused follow-up: constructor defaults

A bounded constructor trace found more than a bare `tokenxxx` string, but still does not establish real session authentication:

- `ji_http::config::Config::new` (`0x675e70`) parses `https://minij.com/api` from `0x117737`, length 21, at `0x675ef4`.
- At `0x675f3c`–`0x675f58` it constructs a string slice pointing to `0x117751`, length 3, exactly `xxx`.
- At `0x675f5c`–`0x675f6c` it converts bytes at `0x11774c`, length 5, exactly `token`, through `HeaderName::from`.
- `ToHeaderValues` runs at `0x675f78`; the resulting key/value is inserted into a HashMap at `0x675fe4`, then copied into the returned configuration.
- `ji_http::Http::new` calls this constructor at `0x5c8e94`, clones its header-map storage through `RawTable::clone` at `0x5c8f08`, and passes the configuration into `Client::new` at `0x5c8f68`.

Therefore the native HTTP library has a constructor default resembling `token: xxx` alongside a placeholder host. The literal is reached by construction code, so calling it merely an unused test string would be inaccurate. However, the inspected `Http::get`/`post`, `Client::new`, and `Client::send` path did not establish where an actual login token replaces this placeholder or whether the default map reaches the emitted request. Do not infer real wire authentication from this default.

Additional saved disassembly: `http-config.asm`, `client-new.asm`, `client-send.asm`, and `client-send-inner.asm`. This follow-up remains static and did not execute any app code or make network requests.
