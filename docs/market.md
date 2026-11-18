# Product thesis / 产品判断

Research snapshot: 2026-11-18. Counts are observations, not estimates of paying customers.

| Project | Observed signal | Implication |
| --- | --- | --- |
| [CC Switch](https://github.com/farion1231/cc-switch) | 155,324 stars | Broad demand for agent/provider setup tools; its scope is much wider than this product |
| [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) | 58,900 stars | Routing is an established ecosystem capability, not our defensible invention |
| [Codex Switcher](https://github.com/Lampese/codex-switcher) | 930 stars; [automatic quota-switch request](https://github.com/Lampese/codex-switcher/issues/207) | Users articulate the switching problem; alternatives already exist |
| [QuotaCrew](https://github.com/erkanpulat/codex-quotacrew) | Windows app, 19 stars, experimental continuation | Continuity and account management already have direct competitors |
| [ccswap](https://github.com/errhythm/ccswap) | 62 stars, account/usage management | Even a narrow developer-tool niche has multiple implementations |

## Judgment

There is a credible niche for a dependable local Codex workflow utility. The evidence does not establish a large standalone paid market. Routing plus automatic switching is easy for existing tools or the platform vendor to absorb. Our strongest initial wedge is a coherent macOS setup/restore experience, CC Switch integration, model fidelity, conversation continuity, and measurable reliability.

先做可信的开源开发者工具，有实际需求；目前没有证据支持“大市场”或付费转化率判断。竞争能力来自安装与恢复体验、清晰的凭据边界和真实兼容性验收，不应只靠“多个账号自动换”宣传。

## First validation cohort

Recruit ten independent macOS testers. Proposed gates, not current results:

- At least eight install and restore without live maintainer assistance.
- At least five continue using it weekly over two weeks.
- Collect ten consented, redacted real failover/recovery observations without lost conversation content or unexpected model changes.
- Observe no credential exposure. Record every compatibility failure and support intervention.

Use interviews to learn whether users value installation support, signed distribution, compatibility maintenance, or approved team deployment enough to pay. Do not infer willingness to pay from GitHub stars. Keep local core functionality open while evaluating support or managed deployment services only after retention evidence.

## Risks

The companion fork creates maintenance costs. Native account switching may improve upstream. Client/model protocols change. Unsigned installation and a Chinese-only settings UI reduce adoption. Team governance and spending controls are absent. Provider restrictions are material: OpenAI's [Terms of Use](https://openai.com/policies/terms-of-use/) prohibit circumventing rate limits or restrictions. Key resale, credential sharing, and promises of unlimited quota are unsuitable positioning.
