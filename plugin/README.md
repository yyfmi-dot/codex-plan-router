# Codex Plan Router（macOS 0.3.0-beta.1）

CC Switch 联动版负责账号、Key 和登录刷新；本插件负责订阅优先路由及统一 Codex 对话分组。每位同事使用自己电脑上的账号库，安装包不含账号、密钥或聊天记录。

## 安装

首次完整联动请使用配套 share.zip：在原 CC Switch 保存编辑并退出一次，解压后双击「安装.command」。安装器将配套 App 放入 ~/Applications，保留原版及现有 ~/.cc-switch 账号库，再通过 Codex 原生命令安装插件和后台服务。需要 Apple Silicon、macOS 12+、Python 3.9+、Codex CLI 0.167+，以及首次下载路由引擎所需的网络。Intel 配套 App 尚未构建。

已经安装配套 App 时，可在 Codex 运行本插件的设置操作。插件 ZIP 本身不含 App。有效的 CC Switch 账号会自动显示，无需重新登录；失效账号请在 CC Switch 重新认证。仅同步明确配置为 https://api.openai.com/v1 的官方 API Key。

默认沿用当前模型，也可以选择设置页提供的其他模型。点击「启用路由并统一历史」，再重启 Codex 一次。安装本身不启用模型路由；未支持的模型不会偷偷映射为其他模型。CC Switch 的 Codex 应使用直连模式：其中的 Plan Router 卡指向本插件的本机路由，避免两层代理循环。

配套 App 基于 CC Switch 4.0.34 修改，保留原作者 MIT 许可证。它与原版使用相同 bundle ID，通过原有单实例机制互斥；配套版不从普通版更新源自动覆盖自身，后续用配套包升级。当前采用 ad-hoc 签名，尚无 Developer ID 签名和 Apple 公证，同事首次打开可能需要本人按 macOS 提示允许。安装器不会关闭 Gatekeeper。

## 请求与状态边界

Codex（固定 custom）→ 本机 CLIProxyAPI → 可用 Plan → 官方 API 备用。

CC Switch（账号、Key、刷新、客户端配置）→ 认证的本机桥接 → 短期访问凭据投影 → 路由引擎。

账号目录约每 5 秒同步一次。新增、删除、重新认证和更换 Key 随后生效。CC Switch 的管理器负责刷新；插件只续取 Access Token，路由引擎不持有这些账号的 Refresh Token。CC Switch 原有的原生 Codex 登录代际协调逻辑保留。

请求优先 Plan；某个账号额度或登录不可用时，CLIProxyAPI 尝试其他可用 Plan，再用 API，冷却结束后重新优先尝试 Plan。切换依赖实际请求的上游响应，不保证提前获知所有账号余额。已有输出的请求不跨账号重放。API 按用量计费，同一组织的多个 Key 可能共享额度。

CC Switch 失联时来源缓存最多保留 30 秒，随后撤下派生凭据；重新连上自动恢复。撤下不取消已在处理的上游请求。桥接仅监听 127.0.0.1，随机认证凭据每次启动轮换，发现文件 0600，拒绝浏览器 Origin 及非本机 Host；状态不含 Key 或 Token。

## 配置与历史

联动模式的启用和恢复委托 CC Switch ProviderService，在其原有切换锁与 Codex 写入流程内完成。插件不直接写 config.toml 或 auth.json。只有本插件明确的本机路由卡保留当前原生登录，普通第三方卡仍使用原策略。

Plan/API 切换在网关内，Codex 始终使用 custom，因此不随账号更换历史列表。已有官方会话迁入前备份，只改 provider 元数据，保留正文；持有原生 writer lease 的线程延后处理。支持 state_5.sqlite 和未压缩 JSONL，压缩旧日志暂不迁移。统一列表不保证跨账号或 API 项目的加密推理上下文可移植。

恢复操作会请 CC Switch 切回原供应商，并按账本恢复原官方分组；若其他工具已改变路由则拒绝覆盖，新消息保留。关闭活动会话后重试剩余还原，再卸载后台服务。仅禁用 Codex 插件不会停止 LaunchAgent。卸载默认保留私有数据与恢复点。

不使用 CC Switch 时可显式运行 router.py setup --source local，使用独立 OAuth/API 页面；此模式需要退出同目录 CC Switch 以避免配置写入冲突。改变凭据来源前先恢复当前路由。

运行目录默认 ~/.local/share/codex-plan-router，目录 0700、私有文件 0600。CLIProxyAPI 8.0.76 按官方 release 固定 SHA-256 下载；TOMLKit 0.13.3 随插件分发，保留 MIT 许可证。实际额度耗尽的端到端切换尚未验收，模拟调度检查与真实推理检查分开报告。

模型列表以 MIT 许可的 CLIProxyAPI 内置目录启动；首次启动即尝试更新，此后每 3 小时检查更新，也可点击「更新可选模型」。有效目录保存在本机，更新失败继续使用上次版本。启用时 CC Switch 会将包含多个模型的目录交给 Codex，之后用户可在 Codex 中切换模型；账号和 Plan/API 切换保持请求模型。gpt-6.2-sol 等新模型需要成功更新目录后才可选择。真实推理验证与验收边界见项目 docs/verification.md。
