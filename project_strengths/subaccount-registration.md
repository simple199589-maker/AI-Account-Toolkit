# 子账号注册

## 模块范围

这里的“子账号注册”不是泛注册，而是为了后续 Team 场景服务的子号生成流程。

## `GPT-team` 的优点

- 这是 `GPT-team` 最强的模块之一，`register_one_account` 是标准的子号全链路：
  - 创建临时邮箱
  - 纯 HTTP 注册
  - 自动发 Team 邀请
  - 邀请后等待生效
  - 再走 OAuth 获取 Codex token
  - 最后上传 CPA 并落本地文件
- 它不是“先注册，再人工处理”，而是围绕子号最终落到 Team 里来设计的完整编排。
- 即使邀请失败，也不会中断后续 token 获取尝试，说明这条链路对“补救”和“容错”考虑更完整。
- 单账号过程是顺序编排，更适合子号这种需要和母号状态联动的业务。

关键文件：

- `GPT-team/gpt-team-new.py`

## `GPT_register+duckmail+CPA+autouploadsub2api` 的优点

- 虽然没有 Team 子号语义，但它的很多能力可直接给子号注册链路补强：
  - 并发 worker
  - 代理池轮换
  - 邮箱 API 验证码提取
  - OAuth 获取 token
  - 失败后自动换代理重试
- 如果未来要做“先大量造号，再分批进 Team”，这一套可以作为前置账号工厂。

关键文件：

- `GPT_register+duckmail+CPA+autouploadsub2api/chatgpt_register.py`

## 模块结论

- 子账号注册主干应优先保留 `GPT-team`。
- `GPT_register+duckmail+CPA+autouploadsub2api` 更适合作为子号注册链路的性能增强层，而不是业务主线。
- 后续整合建议是：`GPT-team` 负责业务编排，`GPT_register...` 负责并发执行、代理调度和批量跑批能力。
