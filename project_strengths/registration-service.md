# 注册服务

## 模块范围

这里的“注册服务”指账号创建主链路本身，不包含 Team 邀请与母号管理。

## `GPT-team` 的优点

- `ProtocolRegistrar` 是明显的纯 HTTP 五步注册流程，链路短，职责清晰，便于排查单账号问题。
- 注册链路和后续 OAuth 登录链路拆得比较清楚：
  - 注册负责把号创建出来
  - `perform_http_oauth_login` 负责再拿 Codex token
- 依赖更轻，核心就是 `requests + yaml`，部署和迁移门槛较低。
- 流程强约束，适合对子号注册这种“稳定优先、一步一步走”的场景。
- 单账号失败后也会保留账号信息，利于后续补救而不是整批直接丢失。

关键文件：

- `GPT-team/gpt-team-new.py`
- `GPT-team/get_tokens.py`

## `GPT_register+duckmail+CPA+autouploadsub2api` 的优点

- 并发注册能力更强，`run_batch` 直接基于线程池跑多账号。
- 代理体系明显更成熟，`ProxyPool` 覆盖：
  - 代理列表抓取
  - 可用性校验
  - 坏代理冷却
  - 稳定代理优先
  - 账号级重试与代理切换
- `curl_cffi` 加 `impersonate` 的方式更接近真实浏览器行为，适合高并发协议注册。
- 注册、OAuth、上报都做成了可配置开关，比如 `enable_oauth`、`oauth_required`、`auto_upload_sub2api`。
- 执行日志粒度更细，适合跑批时盯进度、定位失败原因。

关键文件：

- `GPT_register+duckmail+CPA+autouploadsub2api/chatgpt_register.py`

## 模块结论

- 如果追求高吞吐、代理调度、批量执行能力，优先保留 `GPT_register+duckmail+CPA+autouploadsub2api`。
- 如果追求单链路稳定、逻辑聚焦、方便和 Team 业务深度耦合，优先保留 `GPT-team`。
- 最适合的组合方式是：
  - 注册执行框架参考 `GPT_register...`
  - Team 相关的关键协议细节和后置流程参考 `GPT-team`
