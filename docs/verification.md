# Verification and release claims

## Evidence from the local prototype

- Python unit tests cover configuration restore, history provider metadata, native writer leases, access-only lease rotation, source loss, account removal/reauthorization, key rotation, model inheritance, and catalog rollback.
- Native Rust HTTP tests cover bridge authentication, Origin/Host rejection, access-only responses, model-catalog configuration, preservation of model preferences, route restore, and account removal.
- Local engine smoke checks exercise live configuration changes and a synthetic new-model catalog generation.
- CLI 0.167 and 0.169 app-server checks discovered both plugin skills and multiple native model choices, including gpt-6.2-sol.
- Real gpt-6.2-sol inference completed in a temporary subscription-only route and then an explicitly API-only continuation of the same thread. It retained a synthetic context marker.

## Real quota failover acceptance — 2026-11-18

[Redacted evidence](acceptance/real-exhaustion-2026-11-18.json), reproducible opt-in harness: `tests/live_failover.py`.

The real CC Switch bridge provided access-only leases. The provider usage endpoint identified two already-exhausted subscription credentials (100% used, `allowed=false`, `limit_reached=true`). Separate isolated gateways used the production engine version and routing configuration; eligible source sets were fixed before each request. No artificial upstream errors, quota edits, or mid-request mode changes were used.

| Case | Actual engine evidence | Native client outcome |
| --- | --- | --- |
| Exhausted Plan to available Plan | OAuth failure with usage-limit error, then OAuth success | Same thread completed in 6.38 s and retained the synthetic marker |
| Two exhausted Plans to official API | Two OAuth quota failures, then `auth_type=apikey` success | Same thread completed in 7.82 s and retained the marker |

Both requests and successful upstream responses retained `gpt-6.2-sol`. The user's native configuration digest remained unchanged. Raw usage records were reduced in memory to nonidentifying fields; public evidence contains no account IDs, login names, keys, tokens, raw headers, or private transcripts. The final opt-in run exited successfully with all assertions passing. Usage telemetry was enabled before each isolated engine started; production telemetry settings were unchanged.

## Clean macOS installation acceptance — 2026-11-18

[GitHub run](https://github.com/yyfmi-dot/codex-plan-router/actions/runs/44253380230) · [redacted report](acceptance/clean-macos-2026-11-18.json) · harness: `tests/clean_macos_install.py`.

All **18 checks passed** on a new GitHub-hosted Apple Silicon VM running **macOS 15.8.2**, with **official Codex CLI 0.169.0**. The test used the real VM user's home, first asserted no existing CC Switch/router/native authentication/configuration, then downloaded the published `0.3.0-beta.1` share ZIP and verified its SHA-256. No developer checkout, existing engine binary, user login, or credential fixture was used as the installed payload.

Covered: both executable installer commands; full Python installer; companion placement and signature verification; LaunchAgent/engine start; empty-account bridge connection; no implicit activation or native auth creation; private runtime file permissions; native plugin/skill discovery and writer-lease handling; repeated installation; uninstall stopping the engine while retaining private data. The native loader subtest used an additional temporary `CODEX_HOME` on that VM. The full installation kept the actual user home and did not repurpose `HOME`.

**First-download security approval remains an open manual gate.** The runner reported `assessments enabled` and `spctl --assess` rejected the ad-hoc-signed companion. The test did not set browser-download quarantine, disable Gatekeeper, approve an OS prompt, or perform interactive OAuth. A successful unquarantined VM installation therefore does not establish a frictionless Finder/browser installation on a physical Mac. Developer ID signing/notarization and interactive first-install/login acceptance remain outstanding.

## What remains unverified

These tests begin with already-exhausted credentials. They do not observe natural depletion from available to exhausted, quota reset, automatic return after real replenishment, or replay of an already-streaming response. Simulated cooldown/recovery tests remain separate evidence. A retained synthetic marker is not a guarantee that arbitrary encrypted reasoning state can move between accounts/projects. No Intel or Apple-notarization claim is made.

The public-beta packaging reuses the companion implementation. Private runtime reports, real identifiers, credential stores, conversation logs, and development-path artifacts are excluded from public source.

## Reproduce safely

Run unit tests without credentials. Use synthetic fixtures for engine/native smoke checks. Real inference requires explicit `CODEX_ROUTER_LIVE_PROBE=1`, an installed native client, an authorized running companion, and valid Plan/API access. It can incur charges. Never use another person's login as an implicit test fixture.
