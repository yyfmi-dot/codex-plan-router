# Third-party components

| Component | Role | License / provenance |
| --- | --- | --- |
| [CC Switch](https://github.com/farion1231/cc-switch) 4.0.34 | Companion UI, account manager, native config writer | MIT, Copyright 2025 Jason Young. Pinned commit and archive hash in `companion/UPSTREAM.json`; changes in `companion/patches/plan-router-bridge.patch` |
| [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) 8.0.76 | Routing engine | MIT; official binary URLs and SHA-256 in `plugin/scripts/engine-release.json`; its license is retained when downloaded |
| CLIProxyAPI 8.0.76 embedded catalogs | Offline bootstrap definitions | Copied from the MIT-licensed release source. File hashes and source are in `plugin/scripts/catalog/ORIGIN.json`, license alongside the files |
| [TOMLKit](https://github.com/python-poetry/tomlkit) 0.13.3 | TOML editing | MIT, full notice at `plugin/scripts/vendor/TOMLKIT-LICENSE`, provenance at `plugin/scripts/vendor/ORIGIN.json` |

CC Switch and CLIProxyAPI have their own dependency trees and notices; a companion build retains upstream licensing. This project does not claim authorship of those applications or endorsement from their maintainers.

The separate [model-update repository](https://github.com/router-for-me/models) did not expose an explicit license when reviewed on 2026-11-18. Its latest snapshots are not vendored or included in our public source/release package. The runtime may retrieve those public update documents into the user's private local cache. This does not relabel upstream content under this project's MIT license. An existing private cache is preserved during an upgrade.

OpenAI, Codex, CC Switch, and other names belong to their respective owners. This is an independent integration.
