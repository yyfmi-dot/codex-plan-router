# Verification and release claims

## Evidence from the local prototype

- Python unit tests cover configuration restore, history provider metadata, native writer leases, access-only lease rotation, source loss, account removal/reauthorization, key rotation, model inheritance, and catalog rollback.
- Native Rust HTTP tests cover bridge authentication, Origin/Host rejection, access-only responses, model-catalog configuration, preservation of model preferences, route restore, and account removal.
- Local engine smoke checks exercise live configuration changes and a synthetic new-model catalog generation.
- CLI 0.167 and 0.169 app-server checks discovered both plugin skills and multiple native model choices, including gpt-6.2-sol.
- Real gpt-6.2-sol inference completed in a temporary subscription-only route and then an explicitly API-only continuation of the same thread. It retained a synthetic context marker.

## What those checks do not establish

The real inference canary explicitly changes mode; it does not prove actual account-exhaustion failover. Automatic quota and cooldown tests use a simulated local upstream. Encrypted context can still be account/project-specific. Installer behavior on the development Mac is not independent fresh-Mac acceptance. No Intel or Apple-notarization claim is made.

The public-beta packaging changes reuse the same companion implementation. Tests and CI state are visible in the repository; do not infer a passed CI run from the presence of a workflow file. Private runtime reports, real identifiers, credential stores, conversation logs, and development-path artifacts are intentionally excluded from public source.

## Reproduce safely

Run unit tests without credentials. Use synthetic fixtures for engine/native smoke checks. Real inference requires explicit `CODEX_ROUTER_LIVE_PROBE=1`, an installed native client, an authorized running companion, and valid Plan/API access. It can incur charges. Never use another person's login as an implicit test fixture.
