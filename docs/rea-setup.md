# Rea setup — 2026-10-26

Installed package: `rea-agents@6.7.0`, locally under `.tools/rea`, using npm with lifecycle scripts disabled. The official registry's TLS connection failed; `registry.npmmirror.com` was reachable. `tools/package-lock.json` records the resolved versions, download origins, and integrity values. Integrity values from that mirror are recorded provenance, not an independently verified upstream signature.

Setup was applied for Codex only:

- MCP configuration: `/Users/ajax/.codex/config.toml`.
- Existing configuration backup: `/Users/ajax/.codex/config.toml.rea.backup`.
- Installed skill: `/Users/ajax/.agents/skills/reverse-engineer-anything`.
- MCP executable: `/Users/ajax/Projects/ha-minij/.tools/rea/node_modules/.bin/rea mcp`.

The executable lives in this workspace; retain `.tools/rea` or update the registration if moving/removing the workspace. `scripts/rea` is a convenience wrapper for the same installation.

## Verification

`rea doctor --client codex --skill --json` returned `healthy: true` for the selected Codex/skill scope. The full environment is not healthy because optional analysis providers are missing.

`rea mcp doctor --json` completed a real stdio initialization, tools/prompts inventory, identity check, and `binary_session` request:

- Server: 6.7.0.
- Tools: 207 expected, 207 observed; no missing, unexpected, or duplicate tools.
- Prompts: 6 expected, 6 observed.
- Request flow: passed.

Results are retained in `analysis/rea-setup-result.json`, `analysis/rea-doctor.json`, and `analysis/rea-mcp-doctor.json`. This proves the server launches locally; it does not prove the running Codex chat has reloaded its tool registry. Restart/reconnect Codex to discover the new MCP tools. CLI analysis already works in this chat.

REA successfully inventoried the actual APK and inspected the Rust library. Evidence:

- APK: `ev_d3be4226b58febe5b822ba06259b9212ba9363d37e58d0c94b3ceb6b52d27db6`.
- Rust metadata: `ev_c822c924f4b4db0d1d987b27c59eebd8b9f0d8ef78c24cc9e394312f0017d1d8`.

## Android and native provider boundaries

Installed tools: JADX 1.5.3 and Temurin JDK 21.0.9. JADX decoded the manifest/resources and exposed the protection loader. Apple's LLVM objdump provided the native disassembly used in the HTTP report.

REA's Android adapter additionally requires the separate `jadx-headless-mcp` 0.7.1 JAR; installed JADX alone does not satisfy it. Download attempts to GitHub and its API failed at TLS connection setup. No JAR was installed and `REA_JADX_MCP_JAR` is not configured. No Hopper, Ghidra, or IDA provider was installed.

The repository-main docs describe APK signature inspection, but installed Rea 6.7.0 does not advertise that CLI command. Signature authenticity is unverified. Do not confuse artifact inventory success with signature validation.

## Reinstall the local package

From the project root:

```sh
mkdir -p .tools/rea
cp tools/package.json tools/package-lock.json .tools/rea/
npm ci --prefix .tools/rea --ignore-scripts --no-audit --no-fund
./scripts/rea --version
./scripts/rea mcp doctor --json
```

This restores the package, not global client registration. On a different machine, review a new scoped setup plan before applying it.

Sources: [official Rea repository](https://github.com/morluto/rea), [Android provider guide](https://github.com/morluto/rea/blob/main/docs/android-analysis.md), [official Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp).
