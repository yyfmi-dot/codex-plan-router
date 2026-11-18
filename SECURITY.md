# Security policy

This beta has access to valuable local credentials and conversation metadata. Do not open a public issue containing credentials or private transcripts. Use GitHub's **Report a vulnerability** feature when available; otherwise open a minimal issue requesting a private contact without including exploit details or private data.

## Ownership boundaries

- The companion uses CC Switch's existing account manager and refresh-generation coordination. The router receives short access-only leases, not refresh tokens.
- The local bridge and settings service bind to 127.0.0.1, authenticate requests, restrict Host/Origin, and keep private discovery/state files at 0600 within private directories.
- In linked mode, connection activation and restoration delegate to CC Switch's canonical writer. History migration uses backups and native writer leases.
- An authorized local process under the same macOS user can generally access that user's files. This is not isolation against a compromised user account.
- Inference goes to configured OpenAI services. Engine downloads and catalog updates contact the sources listed in the pinned manifests. Catalogs contain model instructions as well as metadata; treat catalog sources as trusted configuration.

## Current limits

There is no central account service, key sharing, team RBAC, per-project account allowlist, data-residency policy engine, or spending ceiling. A linked installation discovers eligible CC Switch Codex credentials on that machine. Keep each installation within a single approved data/policy boundary. A provider's authentication success does not establish permission to forward an organization's data to that account.

The beta is not Apple-notarized. Follow standard OS approval prompts; do not disable security protections to install it. Provider terms, account rules, and usage limits continue to apply.

Use synthetic data for reproduction. For a leaked key, rotate it with its issuer rather than sending it to maintainers. Backups can contain obsolete refresh credentials; do not restore an old generation blindly.
