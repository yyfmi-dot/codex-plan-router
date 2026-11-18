---
name: manage-router
description: Inspect, reopen settings, restore, or stop the installed local Codex Plan Router; use for routing failures, missing history, or disabling this plugin's routing.
---

Resolve ../../scripts/router.py from this skill directory. Use that controller, not raw credential files.

- Inspect: python3 "<router.py>" status. Output is redacted and includes actual route ownership, credential state, selected model, and pending history work.
- Open account settings: python3 "<router.py>" settings. Users enter keys only in this local page, never in chat.
- Retry history migration: python3 "<router.py>" history. Only do this while the router owns the current route. Native writer leases defer active threads.
- Restore original connection and original official-history labels: python3 "<router.py>" restore --history. It restores only fields the router owns, preserves unrelated later settings and new messages, and refuses to overwrite a route taken over by another tool. Report pending leased threads; close those conversations and retry their restoration before uninstalling.
- Stop after restoration: python3 "<router.py>" stop.
- Remove service registration after restoration: python3 "<router.py>" uninstall. This preserves private credentials and backup data; disabling the Codex plugin alone does not stop its independently installed background service.

In cc-switch mode accounts and Keys belong to CC Switch; status includes source connection and leases. Keep the companion open. After 30 seconds without a valid catalog, derived credentials are withdrawn. Configuration writes delegate to CC Switch in direct mode. In local mode API key removal remains in the plugin settings page. Never dump access.json, settings.json, engine configuration, OAuth files, request bodies, or upstream headers into chat. A quota failure, a stale login, and an inactive client route are separate states; diagnose from actual status rather than assuming the gateway sees the failing request.

Do not claim an automatic-failover E2E check from configuration alone. Distinguish simulated scheduling checks from real upstream inference. A unified list does not establish encrypted-context portability across accounts or API projects.
