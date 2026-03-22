# 团队管理

## 模块范围

这里的“团队管理”指母号登录、团队邀请、车头分配、邀请状态跟踪这部分能力。

## `GPT-team` 的优点

- `chatgpt_http_login` 能走 `chatgpt.com` 的 NextAuth/OAuth 体系拿到母号 `access_token` 和 `account_id`。
- `refresh_team_session_http` 既支持母号密码登录，也支持“无密码 + 邮箱 OTP”模式，对已有母号接入更友好。
- `load_invite_tracker`、`get_available_team`、`auto_invite_to_team` 组成了完整的车头分配机制：
  - 记录每个车头已经邀请了谁
  - 按 `max_invites` 选择可用车头
  - 防止同一个邮箱被重复邀请
- `invite_to_team` 对 401 做了自动刷新后重试，说明母号 session 生命周期也被纳入了设计。
- 如果邀请失败，会把 tracker 中预占的邮箱回滚，避免计数污染。
- 多车头场景下已经具备基础负载分配能力，不是单车头脚本。

关键文件：

- `GPT-team/gpt-team-new.py`

## `GPT_register+duckmail+CPA+autouploadsub2api` 的优点

- 没有真正落地的 Team 管理逻辑，这是它的明显空白。
- 但它已有的 `server.py` 可以作为未来团队管理后台的壳：
  - Web API
  - SSE 日志推送
  - 配置读写
  - 列表页和任务状态页
- 也就是说，它更适合作为管理界面与运维面板，而不是 Team 业务核心。

关键文件：

- `GPT_register+duckmail+CPA+autouploadsub2api/server.py`

## 模块结论

- 团队管理能力应直接以 `GPT-team` 为核心保留。
- 如果后面要做“可视化 Team 管理台”，可以把 `GPT_register.../server.py` 的 Web 运维层接到 `GPT-team` 的团队逻辑外面。
