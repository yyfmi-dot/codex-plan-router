---
name: setup-router
description: Set up the macOS Codex Plan Router, connect an installed CC Switch companion, and open local routing settings; also supports explicitly requested independent OAuth setup.
---

Resolve ../../scripts/router.py relative to this SKILL.md. Use the packaged controller, not a guessed installed path.

Check macOS and Python 3.9+, then run python3 "<router.py>" setup. Setup prepares a pinned, checksum-verified CLIProxyAPI and private user service. It detects CC Switch's bridge; the colleague installer explicitly selects --source cc-switch. If integration is requested but the companion is missing, use the App from the share.zip first. The plugin ZIP alone does not contain that App. Do not silently replace requested integration with an independent login.

In linked mode CC Switch owns accounts, API Keys, refresh tokens and Codex configuration. Valid accounts appear automatically; add/remove/reauthorize accounts and edit Keys in CC Switch. Never import native or CC Switch refresh tokens. --cc-switch-home is only for an explicitly configured custom CC data directory.

In the local page select an actually offered model and enable routing. CC Switch's Codex mode must be direct; its Plan Router card points to the local engine. Unsupported models are reported, never silently renamed. Installation alone does not activate routing. Restart Codex once after activation, then run python3 "<router.py>" status and report actual running/active state and pending history work.

If the user explicitly chooses independent credential management, use setup --source local. Users authorize fresh OAuth or enter Keys only in the local page, never chat or tool arguments. This mode refuses activation while CC Switch owns the same Codex directory. Restore the current route before changing source.

Keep provider ID custom stable across Plan/API switches. History migration backs up metadata and defers native writer leases. Do not kill sessions or rewrite active logs. Compressed legacy rollouts stay explicitly deferred. Shared history does not guarantee encrypted-context portability. Do not report simulated failover as real quota-exhaustion verification.
