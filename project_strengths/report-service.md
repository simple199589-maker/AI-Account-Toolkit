# 上报服务

## 模块范围

这里的“上报服务”指注册完成后的 token/账号信息上送，以及上送后的账号池管理能力。

## `GPT-team` 的优点

- `gpt-team-new.py` 里有直接上传 CPA 的轻量链路，注册完成后可马上把 token JSON 推到管理接口。
- `build_token_dict` 会把 `access_token`、`refresh_token`、`account_id`、过期时间整理成统一结构，适合本地持久化与二次分发。
- `get_tokens.py` 额外补了一套 Sub2Api 上传逻辑，不只是简单上传：
  - 自动构造较完整的 OpenAI OAuth 账号 payload
  - 401 时支持用邮箱密码重新登录，刷新 bearer 后重试
- 这意味着 `GPT-team` 虽然主链路偏 Team，但上报能力并不弱，尤其适合“注册完成即上报”的短链路场景。

关键文件：

- `GPT-team/gpt-team-new.py`
- `GPT-team/get_tokens.py`

## `GPT_register+duckmail+CPA+autouploadsub2api` 的优点

- `chatgpt_register.py` 的 `_push_account_to_sub2api` 已经把上报接进主注册流程，注册成功后可以直接保存 token 并自动上送。
- `server.py` 把“上报服务”从单次上传扩展成了“账号池运维服务”，覆盖：
  - 账号池状态检查
  - 健康度阈值判断
  - 异常账号 refresh
  - 重复账号识别与去重
  - 异常账号批量探测、批量处理、批量删除
- `_build_dedupe_plan` 同时按邮箱和 `refresh_token` 做重复识别，保留最新记录，删除旧记录，适合实际长期运维。
- `/api/config` 对敏感配置做了掩码处理，Web 面板直接改配置的可用性也更高。
- `_list_tokens` 能直接把本地 token 文件整理给前端，方便把“本地结果”和“远端上报状态”统一展示。

关键文件：

- `GPT_register+duckmail+CPA+autouploadsub2api/chatgpt_register.py`
- `GPT_register+duckmail+CPA+autouploadsub2api/server.py`

## 模块结论

- 只看“注册完立即上报”，`GPT-team` 已经够轻、够直接。
- 只看“账号池持续运维”，`GPT_register+duckmail+CPA+autouploadsub2api` 明显更完整。
- 后续如果做统一平台，建议：
  - 保留 `GPT-team` 的 CPA 轻量上传适配器
  - 以上报主平台与池管理能力为核心，优先采用 `GPT_register.../server.py` 这一套
