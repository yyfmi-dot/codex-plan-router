# Contributing

Start with a small issue or pull request describing the user problem, affected surface, and observed behavior. Keep routing decisions in CLIProxyAPI, account/refresh decisions in CC Switch, and setup/history/catalog projection in this project.

## Local checks

Python 3.9+ requires no pip install for unit tests; TOMLKit is vendored with its license.

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m compileall -q plugin/scripts/cpr
node --check plugin/scripts/ui/app.js
git add <intended-source-files>
python3 scripts/audit_source.py
```

Run smoke tests on macOS with an installed Codex client and the checksum-verified engine. They use isolated directories. `live_cc_probe.py` requires an explicit opt-in and makes billable real inference requests; do not run it in CI or with another person's credentials. Never include its private fixtures in a PR.

## Companion changes

Run `scripts/prepare_companion.py` to reconstruct the checksum-pinned upstream source in the ignored `companion/cc-switch` directory. Do not overwrite an existing checkout; choose another destination for patch validation. Preserve the upstream MIT license and update the patch/provenance together. The patch is the maintained source of our changes, not an independently maintained copy of the entire upstream UI.

Build prerequisites include the pinned Rust toolchain, Node, pnpm, and Xcode Command Line Tools. The source preparation script does not install compilers or accept new platform agreements for you.

## PR evidence

Describe what changed, why, relevant validation, and limitations. Separate mocked failures, native client checks, and real upstream inference. Never label a successful configuration write as demonstrated failover. Preserve dirty work and native writer leases.

Do not post authentication files, tokens, keys, raw request bodies, real account lists, conversation logs, or unredacted diagnostics. Use synthetic fixture names and the security policy for sensitive findings.
