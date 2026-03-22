# 邮箱服务

## 模块范围

这里的“邮箱服务”只看临时邮箱创建、已有邮箱复用、邮件轮询、验证码提取这几层能力。

## `GPT-team` 的优点

- 自建 Cloudflare Worker 邮箱模型更可控，邮箱生命周期、域名和管理接口都掌握在自己手里。
- `gpt-team-new.py` 的 `create_temp_email` 创建地址时直接返回 `jwt`，子号注册后续可以直接拿来轮询 OTP。
- `gpt-team-new.py` 的 `_get_jwt_for_address` 能为“已存在邮箱”补拿 JWT，而且做了多路径兜底：
  - 先尝试直接创建/复用地址。
  - 再按多种搜索参数查地址。
  - 最后全量翻页找地址 ID，再尝试多个 token 端点生成 JWT。
- 这一套对母号特别有价值，因为它支持“已有母号邮箱”重新接入系统，而不是只支持新建临时邮箱。
- 子号邮箱和母号 OTP 邮箱可以统一走同一套 Worker 服务，减少跨服务不一致问题。

关键文件：

- `GPT-team/gpt-team-new.py`
- `GPT-team/get_tokens.py`

## `GPT_register+duckmail+CPA+autouploadsub2api` 的优点

- DuckMail 接口更标准化，`/generate`、`/emails`、`/email/{id}` 这种结构更适合快速接入第三方邮箱服务。
- `chatgpt_register.py` 同时支持：
  - 直接读取邮件列表里的 `verification_code`
  - 拉取单封邮件详情再读 `verification_code`
  - 最后再从 `html/text/preview` 用正则兜底提码
- 对验证码提取做了误判过滤，显式跳过已知错误码 `177010`。
- 邮件 API Session 支持代理与浏览器指纹伪装，天然适合并发注册场景。
- `mailbox_ref` 设计简单，整个注册链路里复用成本低。

关键文件：

- `GPT_register+duckmail+CPA+autouploadsub2api/chatgpt_register.py`

## 模块结论

- 如果要的是邮箱服务可控、母号可复用、支持已有邮箱回收 JWT，优先保留 `GPT-team`。
- 如果要的是标准 API 邮箱接入、并发环境下的验证码读取稳定性，优先保留 `GPT_register+duckmail+CPA+autouploadsub2api`。
- 后续整合时，推荐保留两层：
  - 底层邮箱抽象接口参考 `GPT_register...`
  - “已有邮箱补 JWT” 这类高价值能力直接移植自 `GPT-team`
