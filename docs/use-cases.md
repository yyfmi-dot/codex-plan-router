# Use cases / 使用场景

## 1. A developer with authorized subscription access and an API standby

Keep the chosen coding model and one local conversation group while moving eligible new requests to another permitted credential. An interrupted request may still need user attention. API usage is charged by the provider.

个人开发者在有权使用的订阅和 API 备用通道之间接续工作，保留模型及本机会话分组。工具不创造额度，失败任务仍可能需要人工处理。

## 2. Existing CC Switch users

Reuse valid sign-ins and existing official API provider entries instead of maintaining another refresh-token store. Continue account additions and reauthentication in CC Switch.

已有 CC Switch 用户直接联动账号管理，不再复制 Refresh Token 或维护第二套长期登录。

## 3. Codex desktop and IDE users who need predictable local setup

Expose supported model choices, keep the provider identity stable, back up history metadata, and provide a reviewable restore path. This is a local continuity workflow, not a transcript synchronization or cloud-backup product.

桌面端和 IDE 用户需要模型选择、稳定历史分组和明确恢复入口。当前提供本机工作流连续性，不提供跨设备对话同步。

## 4. Teammates installing independently

A team can distribute the same installer while every developer keeps credentials on their own Mac. Pilot onboarding and support can be shared without distributing anyone's sign-in files.

同事共用安装包，各自在自己的电脑管理授权与数据。当前不提供集中账户池、账号分发或组织级权限管理。

## Boundaries

- Use only accounts and projects you are permitted to use, under applicable provider terms. Do not market or use this as a way to bypass usage restrictions, transfer keys, or share personal subscriptions.
- A linked installation currently discovers eligible CC Switch Codex credentials on that Mac. There is no per-project account allowlist. Do not combine credentials across incompatible organizational, confidentiality, or data-residency boundaries.
- Native `custom` history grouping is not guaranteed encrypted-context portability. Already-streaming requests are not replayed on another account.
- API billing, upstream limits, account approval, network availability, and client compatibility are outside the plugin's control.
- CI and simulation prove specific implementation paths. Real quota-exhaustion and fresh-machine acceptance remain separate release gates.

OpenAI's [Terms of Use](https://openai.com/policies/terms-of-use/) prohibit circumventing rate limits or restrictions. An open-source license does not grant permission to use a provider's service. This project does not represent multi-account use as categorically compliant.
