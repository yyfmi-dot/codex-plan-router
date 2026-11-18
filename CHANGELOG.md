# Changelog

## 0.3.0-beta.1 — first public beta

- Product-facing English and Simplified Chinese documentation, use cases, security boundaries, roadmap, and contribution guide.
- Reconstructable CC Switch companion using a checksum-pinned upstream archive and a maintained patch.
- Public source excludes user data, development caches, local reports, compiled output, and unlicensed latest-catalog snapshots.
- MIT-licensed bootstrap catalogs; newer catalogs refresh into private runtime storage on first use and periodically.
- Source audit and deterministic unit CI; a separate manual companion build workflow.

## 0.2.1 — local prototype

- User-controlled default model, including validated gpt-6.2-sol transport and model-picker entries.
- Preserve reasoning and model preferences during same-model activation.
- Persistent catalog updates with rollback, shared client model catalog, and native writer-lease-aware history migration.

## 0.2.0 — local prototype

- Authenticated CC Switch loopback bridge, access-only leases, account/key synchronization, delegated activation/restore, and macOS companion packaging.

## 0.1.x — local prototype

- Standalone local router, setup/manage Codex skills, API standby, and backed-up history migration.

## Post-release acceptance — 2026-11-18

- Real already-exhausted Plan to Plan/API failover passed through the native client, preserving model and same-thread synthetic context.
- The published macOS share ZIP passed 18 core installation checks on a fresh Apple Silicon macOS 15.8.2 hosted VM.
- Added opt-in real inference and credential-free clean installation harnesses, redacted reports, and a manual CI workflow.
- Browser quarantine approval, interactive first login, signing/notarization, natural depletion transitions, and reset recovery remain separate open gates.
- Release ZIPs are unchanged; their recorded checksums still identify the exact installer accepted by the hosted run.
