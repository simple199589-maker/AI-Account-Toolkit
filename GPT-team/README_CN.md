# GPT-Team 中文说明

## 项目用途

`GPT-team` 是一套基于纯 HTTP 协议的自动化脚本集合，主要用于：

- 注册新账号
- 读取临时邮箱验证码
- 登录团队母号并发送邀请
- 完成 Codex OAuth 登录
- 将 token 上传到 Sub2Api

当前目录里同时保留了主流程脚本、注册脚本、Codex 登录测试脚本，以及配置和运行结果文件。

## 目录文件说明

### 核心主流程

- `gpt-team-xianyu.py`
  当前主脚本。负责完整流程，包括注册、验证码处理、团队邀请、Codex 登录、Sub2Api 上传、邀请状态维护、母号 session 缓存等。

- `gpt-team-new.py`
  与 `gpt-team-xianyu.py` 同类的纯 HTTP 主流程版本，保留为并行实现/备用版本。很多底层逻辑和配置结构与 `gpt-team-xianyu.py` 一致。

- `get_tokens.py`
  简化版脚本。主要用于注册并获取 token，不走完整团队邀请管理流程。输出会写入 `results.txt`。

- `register.py`
  纯注册链路实现，包含注册五步流程、邮件验证码校验、部分 OAuth/登录辅助逻辑。可以理解为注册能力的独立实现版本。

### Codex 登录相关

- `codex_login_tool.py`
  Codex 登录共享入口。负责统一封装登录模式，并处理 `joini.cloud` 邮箱自动 OTP、其他邮箱手动 OTP 的分流规则。

- `codex_login_manual_test.py`
  Codex 登录测试脚本。当前支持：
  `joini.cloud` 邮箱自动读取验证码
  非 `joini.cloud` 邮箱手动输入验证码

- `codex_login_manual_test-shoudong.py`
  纯手动版 Codex 登录测试脚本。无自动收码逻辑，适合人工验证对照。

### 公共服务模块

- `mail_service.py`
  临时邮箱公共模块。提供创建邮箱、拉取邮件列表、提取验证码、等待 OTP 等基础能力。

- `sub2api_service.py`
  Sub2Api 上传公共模块。负责登录 Sub2Api、组织上传参数、推送账号 token。

### 配置与数据文件

- `config.yaml`
  主配置文件。所有核心脚本基本都从这里读取代理、临时邮箱、Sub2Api、输出路径、车头账号等配置。

- `accounts.txt`
  已注册账号列表。通常一行一条，保存邮箱、密码、时间等信息。

- `results.txt`
  `get_tokens.py` 的输出文件，通常记录邮箱、邮箱 token、密码、access_token 等结果。

- `invite_tracker.json`
  邀请状态跟踪文件。记录某个子号是否已发送邀请、是否已接受邀请。

- `team_session_cache.json`
  母号 session 缓存。用于缓存团队账号的登录态、token、workspace 等信息，减少重复登录。

- `output_tokens/`
  本地 token 输出目录。Codex 登录成功后生成的 token 文件通常会落在这里。

- `__pycache__/`
  Python 编译缓存目录，可忽略。

- `README.md`
  原始说明文档，内容较简略。

- `README_CN.md`
  当前中文说明文档。

- `requirements.txt`
  Python 依赖列表。

## 推荐从哪个脚本开始

- 只想测试注册拿 token：运行 `get_tokens.py`
- 想跑完整注册 + 邀请 + Codex + 上传流程：优先看 `gpt-team-xianyu.py`
- 想单独验证 Codex 登录：看 `codex_login_manual_test.py` 或 `codex_login_manual_test-shoudong.py`
- 想看公共登录分流逻辑：看 `codex_login_tool.py`

## config.yaml 配置解释

当前配置结构如下：

```yaml
total_accounts: 1
proxy:
  http: "127.0.0.1:7890"

temp_mail:
  worker_domain: "mail.joini.cloud"
  email_domains:
    - "joini.cloud"
  admin_password: "xxxx"

sub2api:
  base_url: "https://code.joini.cloud"
  bearer: ""
  email: "admin@sub2api.local"
  password: "xxxx"
  auto_upload_sub2api: true
  group_ids: [2]

cli_proxy:
  management_url: "http://xxx"
  password: "xxx"
  api_base: "http://xxx"
  upload_enabled: true

output:
  accounts_file: "accounts.txt"
  invite_tracker_file: "invite_tracker.json"
  results_file: "results.txt"

teams:
  - name: "tp1"
    email: "xxx@example.com"
    password: ""
    jwt: ""
    max_invites: 4
```

### 顶层字段

- `total_accounts`
  计划注册的子号数量。主流程脚本会按这个数量循环执行。

- `proxy.http`
  HTTP 代理地址。为空则不走代理。通常格式为 `host:port` 或完整 `http://host:port`。

### temp_mail

- `temp_mail.worker_domain`
  临时邮箱服务域名。脚本会请求 `https://<worker_domain>/api/...`。

- `temp_mail.email_domains`
  临时邮箱可生成的邮箱域名列表。部分脚本会打印或依赖这个列表做展示/检查。

- `temp_mail.admin_password`
  临时邮箱管理口令。
  用途有两个：
  1. 创建临时邮箱
  2. 读取 `joini.cloud` 邮箱验证码

### sub2api

- `sub2api.base_url`
  Sub2Api 服务地址。

- `sub2api.bearer`
  可选的 Bearer Token。若服务端支持直接 Bearer 认证，可在这里配置。

- `sub2api.email`
  Sub2Api 登录邮箱。

- `sub2api.password`
  Sub2Api 登录密码。

- `sub2api.auto_upload_sub2api`
  是否在拿到 token 后自动上传到 Sub2Api。`true` 表示自动上传。

- `sub2api.group_ids`
  上传账号时默认归属的分组 ID 列表。

### cli_proxy

- `cli_proxy.management_url`
- `cli_proxy.password`
- `cli_proxy.api_base`
- `cli_proxy.upload_enabled`

这组配置属于旧版 CPA 兼容字段。当前主流程已经以 `sub2api` 配置为准，通常不再作为主要上传链路使用，但暂时保留以兼容历史脚本。

### output

- `output.accounts_file`
  注册账号结果输出文件。

- `output.invite_tracker_file`
  邀请状态跟踪文件。

- `output.results_file`
  `get_tokens.py` 的结果输出文件。

说明：
这些路径如果写相对路径，通常默认相对于 `GPT-team` 目录解析。

### teams

`teams` 是母号/车头账号列表，每一项对应一个团队账号。

- `teams[].name`
  车头名称，仅用于识别和日志输出。

- `teams[].email`
  车头邮箱。

- `teams[].password`
  车头密码。
  如果为空，脚本会把该车头视为 OTP 登录模式。

- `teams[].jwt`
  旧版兼容字段。当前版本多数情况下不要求手动填写，保留用于兼容旧配置。

- `teams[].max_invites`
  该车头可发送的最大邀请数量。主流程会参考这个值分配邀请任务。

## 当前 Codex 验证码策略

Codex 登录相关脚本当前采用以下规则：

- `@joini.cloud` 邮箱：自动读取邮箱验证码
- 非 `@joini.cloud` 邮箱：手动输入验证码

对应入口：

- `codex_login_tool.py`
- `codex_login_manual_test.py`

## 常见运行方式

### 1. 简化注册拿 token

```bash
python get_tokens.py
```

### 2. 完整主流程

```bash
python gpt-team-xianyu.py
```

### 3. Codex 登录测试

```bash
python codex_login_manual_test.py
```

### 4. Codex 手动登录测试

```bash
python codex_login_manual_test-shoudong.py
```

## 使用建议

- 优先维护 `gpt-team-xianyu.py`，它是当前主流程脚本。
- 调试 Codex OTP 时，优先用 `codex_login_manual_test.py` 和 `codex_login_manual_test-shoudong.py` 做对照。
- 修改 `config.yaml` 前，建议先备份当前可用配置。
- 如果出现母号登录异常，先检查 `team_session_cache.json` 是否是旧缓存导致。
- 如果出现重复邀请或状态异常，先检查 `invite_tracker.json`。

## 注意事项

- 目录中包含真实接口地址、邮箱和自动化流程能力，使用时请自行评估风险。
- 临时邮箱、OpenAI 登录、Sub2Api 上传都依赖网络环境和代理状态。
- 如果脚本行为异常，建议优先查看日志里对应的 step 编号定位问题。
