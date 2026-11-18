# Codex Plan Router

**Subscription-first routing, API standby, and conversation continuity for Codex.**

A macOS companion and Codex plugin that connects accounts managed by CC Switch to a local routing engine. Choose your model in Codex, manage sign-ins in CC Switch, and keep conversations under one stable connection as eligible credentials change.

[English documentation](https://github.com/yyfmi-dot/codex-plan-router) · [中文文档](https://github.com/yyfmi-dot/codex-plan-router/blob/main/README.zh-CN.md) · [Downloads](https://github.com/yyfmi-dot/codex-plan-router/releases)

## Features

- Automatic discovery of valid CC Switch Codex accounts and official OpenAI API providers.
- Eligible Plan credentials preferred before API standby, with engine-managed retries and cooldowns.
- User-selected models and an automatically updated model catalog.
- Backed-up conversation-provider migration and restoration that preserves new messages.
- Local credential ownership: CC Switch manages refresh credentials; the router receives short-lived access leases.

## Install

Download the **macOS share ZIP** for the complete companion and plugin installation. Save edits and quit CC Switch once, extract the archive, and open **Install.command** or **安装.command**. Review the discovered accounts in local settings, choose a default model, enable routing, and restart Codex.

Keep CC Switch's Codex connection mode on **Direct**. Manage account additions, API keys, and reauthentication in CC Switch. The plugin ZIP alone is intended for an existing companion installation.

Requires Apple Silicon, macOS 12+, Python 3.9+, and Codex CLI 0.167+. This is a public beta with a Chinese settings UI. The companion is ad-hoc signed and is not Apple-notarized; macOS may require manual first-launch approval.

## Manage and restore

Use the setup and management skills provided by this plugin, or run `scripts/router.py status` and `scripts/router.py settings` from its installed directory.

Run `scripts/router.py restore --history` before stopping or uninstalling the background service. Original settings, conversation metadata, and recovery points are handled through the documented restore workflow. Disabling the plugin alone leaves the separate LaunchAgent running.

Each developer installs their own copy and uses authorized credentials within an approved data-policy boundary. API standby is billed by OpenAI. See the [full documentation](https://github.com/yyfmi-dot/codex-plan-router) for architecture, usage boundaries, and recovery details.

MIT project code. CC Switch, CLIProxyAPI, and TOMLKit retain their respective licenses. Independent community project, unaffiliated with OpenAI or the upstream maintainers.
