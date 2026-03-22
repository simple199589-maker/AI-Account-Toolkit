# 两个项目优点拆分

本目录用于沉淀当前两个项目的可复用优势，便于后续合并、重构或按模块抽取。

当前默认对比的两个项目：

- `GPT-team`：偏纯 HTTP 协议流、子账号注册、团队邀请、母号 Session 管理、CPA 上传。
- `GPT_register+duckmail+CPA+autouploadsub2api`：偏 DuckMail 邮箱接入、并发注册、代理池、Sub2Api 上报与 Web 运维。

## 模块索引

| 模块 | 当前更强侧重点 | 文档 |
| --- | --- | --- |
| 邮箱服务 | `GPT-team` 更强可控性，`GPT_register...` 更强标准化对接 | [mail-service.md](./mail-service.md) |
| 上报服务 | `GPT_register...` 更完整，`GPT-team` 更轻量 | [report-service.md](./report-service.md) |
| 注册服务 | `GPT_register...` 更强吞吐与代理能力，`GPT-team` 更聚焦纯协议稳定链路 | [registration-service.md](./registration-service.md) |
| 子账号注册 | `GPT-team` 明显更完整 | [subaccount-registration.md](./subaccount-registration.md) |
| 团队管理 | `GPT-team` 明显更完整 | [team-management.md](./team-management.md) |

## 配置合并

- 精简合并说明：[config-merge.md](./config-merge.md)
- 精简配置模板：[merged-config.minimal.yaml](./merged-config.minimal.yaml)

## 快速结论

- 如果目标是做 Team 子号全链路，主干优先保留 `GPT-team`。
- 如果目标是做高并发注册工厂或 Sub2Api 账号池运维，主干优先保留 `GPT_register+duckmail+CPA+autouploadsub2api`。
- 最适合后续整合的方向是：`GPT-team` 负责团队域能力，`GPT_register...` 负责代理池、并发执行、Web 运维面板和 Sub2Api 池管理。
