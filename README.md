<p align="center"><img src="docs/hero.svg" alt="Codex Plan Router — Your models. Your accounts. One local workflow." width="860"></p>

<p align="center"><a href="README.zh-CN.md">简体中文</a> · <a href="https://github.com/yyfmi-dot/codex-plan-router/releases">Downloads</a> · <a href="docs/architecture.md">Architecture</a> · <a href="docs/use-cases.md">Use cases</a></p>

# Codex Plan Router

**Keep working in Codex with your chosen model, local account ownership, and an API standby.**

Codex Plan Router is a local macOS companion and Codex plugin. It connects accounts managed by CC Switch to an existing routing engine, keeps one conversation provider, and preserves the model you selected. Independent community project, unaffiliated with OpenAI or the upstream projects.

> **Public beta · Apple Silicon · macOS 12+**. Requires Python 3.9+ and a Codex client with CLI 0.167+. The companion is ad-hoc signed and is not Apple-notarized. The settings UI is currently Chinese; CC Switch itself supports English. See the roadmap before treating this as a managed enterprise product.

## Why this exists

An account switch should not require reconstructing your local setup or finding another copy of your conversation. This project connects three existing layers instead of replacing them:

- **CC Switch** owns sign-ins, refresh credentials, and Codex connection configuration.
- **CLIProxyAPI** owns credential selection, retries, and cooldowns.
- **This plugin** owns setup, short access-token projections, model-catalog updates, and backed-up history migration.

The client keeps `custom` as its provider ID. Account changes happen behind that endpoint. You choose the model; the router preserves the model name in the request.

## What you can do

| Capability | Current behavior |
| --- | --- |
| CC Switch integration | Discover its Codex accounts and explicit official OpenAI API-key providers; no second login for valid accounts |
| Routing | Prefer eligible subscription credentials, then API credentials; use the existing engine's error and cooldown rules |
| Model choice | Inherit the current default or select an available model; expose the complete supported catalog to Codex |
| Conversation history | Back up and unify provider metadata; defer active native writer leases |
| Local ownership | Keep credentials and backups on your Mac; the bridge listens on loopback with per-launch authentication |
| Recovery | Restore the previous provider and original history labels without deleting new messages |

This does not increase your entitlement, buy credits, or guarantee uninterrupted execution. Only use accounts you are authorized to use, within provider terms and organizational rules. API calls are billed by your provider. Different keys can share an organization limit. See [use boundaries](docs/use-cases.md#boundaries).

## Install

1. Download the **macOS share ZIP** from [Releases](https://github.com/yyfmi-dot/codex-plan-router/releases).
2. Save edits and quit the running CC Switch once. Extract the ZIP and open **Install.command** (or **安装.command**).
3. The installer puts the companion in `~/Applications`, keeps the original App and account store, registers the Codex plugin, and opens local settings.
4. Check the discovered accounts, choose a default model or keep the current one, and enable routing. Keep CC Switch's Codex connection mode on **Direct**; its Plan Router card points to the separate local engine.
5. Fully quit and reopen Codex once to load its model catalog. Restart the editor window for an IDE extension.

A Codex-plugin ZIP alone does not install the companion App. Use the share ZIP for the complete integration. macOS may require you to approve the unsigned-distribution beta in its standard Privacy & Security UI. The installer does not disable Gatekeeper.

Each teammate installs their own copy and uses their own authorized credentials. No keys, user profiles, or conversation data are included in a release.

## Daily use

Keep the companion open. Account changes normally sync within about five seconds. Choose models inside Codex after setup. Directory updates can be requested in local settings and are checked periodically. Invalid sign-ins still require reauthentication in CC Switch.

For terminal management, resolve `router.py` from the installed plugin or this source checkout:

```sh
python3 plugin/scripts/router.py status
python3 plugin/scripts/router.py settings
python3 plugin/scripts/router.py restore --history
python3 plugin/scripts/router.py stop
```

Restore before stopping or uninstalling so the client is not left pointing to a stopped endpoint. Disabling the Codex plugin alone does not stop the separately installed LaunchAgent.

Standalone mode is also available with `setup --source local`. It creates independent OAuth authorizations and refuses to compete with CC Switch over the same Codex configuration directory.

## What is verified

The local prototype was exercised with Codex CLI 0.167 and 0.169, including native plugin discovery and model-picker responses. Real `gpt-6.2-sol` requests completed with a subscription-only first turn and an explicitly API-only continuation of the same thread. Model and reasoning settings were preserved during activation.

Automatic exhaustion/cooldown scenarios were validated using a local simulated upstream. **A real account-exhaustion end-to-end test has not been completed.** Cross-account encrypted reasoning context may be incompatible. Requests already producing output are not replayed through another account. Intel, Windows, Linux desktop installation, Apple notarization, per-project routing policies, and spend ceilings are not shipped in this beta. See [verification](docs/verification.md).

## Build and contribute

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/prepare_companion.py
cd companion/cc-switch
pnpm install --frozen-lockfile
pnpm tauri build --features plan-router-bridge --config src-tauri/tauri.plan-router.conf.json --bundles app --ci
cd ../..
python3 build_companion.py
python3 build.py
```

The companion is a small patch over a checksum-pinned CC Switch release. Its full checkout, dependencies, credentials, and build outputs are excluded from this repository. See [CONTRIBUTING](CONTRIBUTING.md), [third-party notices](THIRD_PARTY_NOTICES.md), and the [roadmap](docs/roadmap.md).

MIT for this project's code. Upstream notices remain in their respective components. Model data from update services is downloaded for local use; unlicensed update snapshots are not redistributed in this repository.
