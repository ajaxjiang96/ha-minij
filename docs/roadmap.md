# MiniJ Home Assistant Roadmap

Updated 2026-10-26. Proposed release scope: an open-source, cloud-based, read-only integration that another V6-XNB owner can install, sign into, and use for dependable washer monitoring.

The prototype already works on the user's Home Assistant installation. The next release should make that result reproducible for other users. Appliance controls follow after authentication and status semantics are established.

## Current baseline

- V6-XNB, internal model `minij.washer.x68`, is verified with live cloud requests and Home Assistant entities.
- The user's installed HA screenshot confirms five entities, a running program, and the observed transition `device_exception` → `working`. This does not establish the cause of the exception or a complete cycle lifecycle.
- Current entities: status, reported program, reported process, child lock, and cloud control authorization.
- Existing firmware baseline: Wi-Fi `1.0253`, device firmware `0 0003 1 0000`. No update has been installed by the agent.
- Token setup is verified. Experimental phone/SMS setup and same-account reauthentication are implemented; live SMS acceptance and token lifetime/renewal remain unknown.
- All 16 tests now pass with exit 0 on Linux ARM64. The earlier macOS-only finalization failure and its built-in-HA baseline remain documented. The live MiniJ HA smoke process also exits successfully.
- Local Git, MIT license, CI configuration, HACS metadata, maintainer, and the user-supplied brand icon are prepared. The public repository is created; validation and PR status are recorded in [foundation status](foundation.md).

The current `0.1.0` manifest/ZIP identifies a local prototype; it is not an existing public release.

## First public release contract

A fresh user can install through a HACS custom repository, configure their own account without APK analysis or an emulator, see accurate supported status fields, and recover from restarts, cloud outages, and rejected sessions. Unknown device values remain unknown; stale data is not presented as a fresh appliance reading.

Initial verified support is **V6-XNB on the tested firmware**, with a documented minimum HA version and an explicit cloud dependency. Other models are unverified until evidence is contributed. The first release includes monitoring and the states needed for user-created HA automations. Program selection, start/pause/stop, firmware management, LAN control, and MQTT are later work.

## Milestone 1 Publishable source and repeatable validation

This can run alongside authentication and status research.

- [x] Initialize Git and establish intended repository/maintainer: `ajaxjiang96/ha-minij`.
- [x] Create the requested public repository `ajaxjiang96/ha-minij`.
- [x] Validate and merge [foundation PR #1](https://github.com/ajaxjiang96/ha-minij/pull/1): merged as `502f89d`; both branch validation workflows passed and Codex reported no findings.
- [x] Select an open-source license and add `LICENSE`; include only authored integration code, documentation, and sanitized fixtures in the initial history. Keep APKs, decompilation, account logs, tokens, network identifiers, and raw responses out of publication.
- [x] Separate user installation/support instructions from reverse-engineering notes; remove workstation-specific prerequisites from the normal setup path.
- [x] Add issue templates for bugs and model-support reports, contribution instructions, and a documented method for submitting redacted evidence.
- [x] Add Linux CI with supported Python/HA versions, transport tests, HA runtime tests, Ruff, hassfest, and HACS validation. Test the declared minimum and current released HA version; recheck versions when implementing.
- [x] Get a full test process to exit 0 on the release CI environment. Keep the macOS finalization reproducer separate; do not hide nonzero exits or count assertions alone as green CI.

**Acceptance:** a clean checkout has one documented development command sequence, all required CI jobs pass with exit 0, and the initial public history contains no private artifacts. Real repository URLs and maintainer identity are ready for the manifests.

## Milestone 2 Account setup and session lifecycle

This is the largest usability blocker: log-extracted tokens are suitable for the prototype, not the normal first-release setup.

- [x] Recover the exact phone-login SMS `type`: `login`, confirmed by the successful app login log. See [authentication evidence](authentication.md).
- [ ] Establish challenge/cooldown behavior. The unrelated web whitelist SMS type must not be reused.
- [x] Implement a HA phone → request code → enter code → verify account/device access flow (fixture-tested; live acceptance remains pending). Send SMS only on the user's explicit submission; handle incorrect codes, timeouts, challenges, and server limits with actionable messages.
- [ ] Establish token behavior across HA restart, additional app logins, expiry/revocation, and logout. Use an actual renewal mechanism only if observed; otherwise use the same SMS flow for reauthentication.
- [ ] Complete live reauthentication acceptance; runtime tests verify matching-account credentials preserve entity IDs and registry names. A different account must not silently replace the original account's credentials.
- [x] Keep token entry available as an explicitly documented advanced method if useful; normal installation must not depend on reading app logs.

**Acceptance:** a fresh owner can configure and later reauthenticate entirely through HA, without an emulator or developer tools. Both fixture tests and a real account exercise the flow. If a login challenge prevents this, keep the build labeled an advanced beta and resolve that blocker before calling it the first general release.

## Milestone 3 Dependable washer state

Use the existing installation to collect a user-run normal cycle. Physical appliance actions and firmware changes remain user-operated during validation.

- [ ] Record redacted API snapshots and corresponding app/HA observations for idle, cycle start, stage transitions, completion, and a user-performed pause/cancel when supported. Capture naturally occurring errors without deliberately causing an appliance fault.
- [ ] Investigate the screenshot's `device_exception` → `working` transition. Preserve the raw alias and correlate any fault information before labeling it as a specific problem.
- [ ] Verify device-offline, cloud-unreachable, and unknown-status behavior separately. Implement appliance availability and stale-data handling from observed semantics; current availability only checks cloud refresh and whether the device remains bound.
- [ ] Translate known status aliases in English and Chinese while preserving stable machine-readable states and raw diagnostic values for new aliases.
- [ ] Establish whether program/process fields describe the active cycle or the last/default cycle. Retain accurate labels for idle values.
- [ ] Add remaining time only after validating units, countdown behavior, and idle/completed semantics. The earlier idle `48` versus app estimate `76` is not a validated countdown.
- [ ] Expose useful fault information only when its source and meaning are confirmed. Refresh device metadata when firmware or naming changes.
- [ ] Test restart, reload, temporary outage, recovery, removed devices, and multiple bound devices. Add a small redacted HA diagnostics export for support.

**Acceptance:** one complete real cycle is correlated end to end; completion, cancellation, error, and unknown values cannot be confused in supported automation inputs. Offline data behaves truthfully. Unverified optional fields remain omitted. Firmware-specific support is recorded explicitly.

## Milestone 4 HACS beta and independent installation

Depends on Milestones 1–3 for the normal-user beta.

- [ ] Complete `hacs.json`, real manifest documentation/issue URLs, maintainer ownership, and permitted brand assets. The missing icon in the user's screenshot belongs here.
- [ ] Validate installation from the public HACS custom repository, upgrade from the beta, uninstall, and reinstall. Verify stable device/entity IDs across upgrades.
- [ ] Publish a tagged prerelease such as `0.1.0-beta.1` with release notes, supported model/firmware, cloud behavior, known limitations, and troubleshooting.
- [ ] Have another owner perform a fresh installation using only the README. Record their model, firmware, HA version, and results; do not claim additional-model support from successful installation alone.
- [ ] Complete a proposed 48-hour soak including a normal cycle, HA restart, and session recovery; review polling/error behavior and user-visible states.

**Acceptance:** an independent V6-XNB owner completes installation and monitoring without direct developer intervention; required checks are green and no release-blocking authentication, state, privacy, or upgrade defects remain.

## Milestone 5 First stable public release

- [ ] Resolve beta blockers and rerun the release checks against the exact release commit.
- [ ] Publish `v0.1.0` with install instructions, a tested support matrix, screenshots, migration/upgrade notes where relevant, and a minimal completion-automation example based on verified state transitions.
- [ ] Document the support policy and how unknown models/firmware are reported. State that this is an unofficial MiniJ cloud integration.

**Acceptance:** another user can install, authenticate, monitor a real cycle, restart HA, and recover authentication using the released documentation and artifact. Default HACS-store inclusion can be requested after beta feedback; custom-repository installation is the initial distribution route.

## After the first release

1. **Controls:** trace model-supported commands, required cloud authorization, parameter semantics, and acknowledgements. Add one command end to end with verified device outcome before expanding. Keep user-selected versus controller-reported programs distinct.
2. **Firmware compatibility:** compare the retained baseline with a user-chosen update, including authorization and recovery behavior; add fixtures for observed differences rather than speculative compatibility paths.
3. **More models:** accept model/firmware evidence and add capabilities from actual responses, without creating a generic appliance framework in advance.
4. **Local operation and HA Core:** investigate LAN support if evidence warrants it. Consider a separately published API library when another consumer or a Core submission makes that boundary useful.

## Next work order

Milestone 1 is merged. Complete **Milestone 2 live SMS/session acceptance** using the experimental HA flow. Collect cycle evidence during normal use in parallel. Build the public beta after those results establish a usable setup flow and truthful monitoring behavior.

## Upstream requirements

- [HACS general requirements](https://www.hacs.xyz/docs/publish/start/): public GitHub repository, user documentation, and root HACS manifest.
- [HACS integration requirements](https://www.hacs.xyz/docs/publish/integration/): integration layout, required manifest metadata, and brand assets.
- [HACS validation action](https://www.hacs.xyz/docs/publish/action/): repository validation and hassfest guidance.
- [Home Assistant integration manifest](https://contributors.home-assistant.io/core/integrations/manifest/): integration identity and metadata.

These requirements were checked on 2026-10-26; recheck them when preparing the release.
