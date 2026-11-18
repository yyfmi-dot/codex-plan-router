<p align="center"><img src="docs/hero.svg" alt="Codex Plan Router — 模型由你选，账号留本机，会话保持连续" width="860"></p>

<p align="center"><a href="README.md">English</a> · <a href="https://github.com/yyfmi-dot/codex-plan-router/releases">下载安装</a> · <a href="docs/architecture.md">架构设计</a> · <a href="docs/roadmap.md">路线图</a></p>

# Codex Plan Router

**为 Codex 提供订阅优先路由、API 备用通道和连续的会话体验。**

Codex Plan Router 通过 macOS 本机配套应用和 Codex 插件，将 CC Switch 管理的账号接入 Codex。它自动选择可用凭据，保留你选择的模型，让订阅和 API 通道之间的切换保持同一个连接与会话分组。

> **公开测试版 · macOS · Apple Silicon**

## 核心功能

| 功能 | 说明 |
| --- | --- |
| CC Switch 自动联动 | 复用已有的有效 Codex 登录和官方 OpenAI API 配置，账号变化自动同步。 |
| 订阅优先路由 | 优先使用可用 Plan；当前账号不可用时尝试其他 Plan，再使用 API 备用通道。 |
| 自由选择模型 | 默认沿用当前模型，并向 Codex 提供支持的模型列表。切换凭据时保留请求中的模型。 |
| 连续的会话体验 | 保持稳定的连接配置，将已有对话统一到本机会话分组，迁移前自动备份。 |
| 本机凭据管理 | CC Switch 负责登录与刷新凭据；经过认证的本机桥接向路由提供短期访问凭据。 |
| 配置恢复 | 恢复原连接和历史分组，同时保留新消息与其他设置。 |

## 适用场景

- **同时使用 Codex Plan 和 API 的开发者**：通过备用通道接续工作，减少反复修改连接配置。
- **已有 CC Switch 用户**：让现有账号管理直接联动 Codex 路由和模型选择。
- **需要统一安装流程的团队**：分发同一套安装包，每位开发者在自己的 Mac 保存授权凭据和会话数据。

完整使用场景及部署边界见 [使用场景说明](docs/use-cases.md)。

## 快速开始

### 环境要求

| 组件 | 要求 |
| --- | --- |
| Mac | Apple Silicon，macOS 12 或更新版本 |
| Python | 3.9 或更新版本 |
| Codex | 客户端包含 Codex CLI 0.167 或更新版本 |
| 网络 | 能够访问路由引擎及模型目录下载源 |

当前设置页使用中文。配套应用采用 ad-hoc 签名，尚未完成 Apple 公证；首次运行可能需要在 macOS **隐私与安全性**中手动允许。

### 安装步骤

1. 在 [Releases](https://github.com/yyfmi-dot/codex-plan-router/releases) 下载 macOS **share.zip 完整安装包**。
2. 保存编辑，并退出正在运行的 CC Switch 一次。
3. 解压后打开 **安装.command** 或 **Install.command**。
4. 在本机设置页检查已发现的账号，沿用当前模型或选择默认模型，然后启用路由。
5. 完全退出并重新打开 Codex，载入模型目录；使用 IDE 扩展时，重启编辑器窗口。

安装器将配套应用放入 `~/Applications`，注册 Codex 插件并打开本机设置页。原版 CC Switch 应用和已有账号库会保留。CC Switch 的 Codex 连接模式保持 **Direct / 直连**。

首次完整安装请使用 share.zip。较小的插件 ZIP 适用于已安装配套应用的环境。

## 日常使用

保持配套应用运行，继续在 Codex 中选择模型。在 CC Switch 中管理账号、API Key 和重新认证。账号变化通常约五秒同步；本机模型目录会定期更新，也可以在设置页手动刷新。

API 备用通道由 OpenAI 按用量计费，同一组织的多把 Key 可能共享限额。请在同一许可和组织数据边界内使用授权账号。连接、上下文及路由的具体使用边界见 [使用说明](docs/use-cases.md#boundaries)。

### 管理与恢复

在源码目录中运行：

```sh
python3 plugin/scripts/router.py status
python3 plugin/scripts/router.py settings
python3 plugin/scripts/router.py restore --history
python3 plugin/scripts/router.py stop
```

已安装版本使用插件目录中的 `scripts/router.py`。停止或卸载后台服务前，先恢复连接配置。仅禁用 Codex 插件时，单独安装的 LaunchAgent 仍会运行。

需要独立管理凭据时，可使用 `setup --source local`。配置方式见 [设置技能说明](plugin/skills/setup-router/SKILL.md)。

## 文档

- [架构设计](docs/architecture.md)：组件职责与本机联动原理
- [使用场景](docs/use-cases.md)：工作流程、账号边界与计费
- [兼容性与验证说明](docs/verification.md)：版本支持与发布范围
- [路线图](docs/roadmap.md)：后续产品计划
- [贡献指南](CONTRIBUTING.md)：源码准备、构建与开发
- [安全说明](SECURITY.md)：凭据处理与漏洞反馈

## 许可证与致谢

本项目代码采用 [MIT 许可证](LICENSE)，基于 [CC Switch](https://github.com/farion1231/cc-switch)、[CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) 和 TOMLKit 构建。许可证及来源见 [第三方声明](THIRD_PARTY_NOTICES.md)。

Codex Plan Router 由社区独立维护，与 OpenAI 及上游维护者不存在隶属或官方背书关系。
