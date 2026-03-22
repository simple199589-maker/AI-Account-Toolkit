# GPT-Team 全自动协议注册工具（CF 临时邮箱版）

> 禁止任何形式的外传

## 项目介绍

GPT-Team 是一个全自动协议注册工具，使用纯 HTTP 协议完成 ChatGPT 子账号的注册和团队管理，无需浏览器操作。目前仅绑卡步骤需要手动操作，其他流程均已自动化。

## 功能特性

- ✅ 纯 HTTP 协议注册子号（无浏览器）
- ✅ 母号自动登录获取 Token
- ✅ 自动拉 Team 邀请
- ✅ 自动 Codex OAuth 授权上传 Sub2Api
- ✅ 集成 Cloudflare Worker 临时邮箱（需自建）

## 使用方法

### 1. 部署临时邮箱

需要自建 Cloudflare Worker 临时邮箱服务：

1. 部署 CF Worker
2. 配置邮箱域名
3. 获取 Worker 域名和管理密码

### 2. 配置文件

编辑 `config.yaml` 文件。`gpt-team-new.py` 与 `get_tokens.py` 共用同一个 `temp_mail` 配置，母号 OTP 也从这里接收：

```yaml
total_accounts: 10              # 要创建的子号数量
temp_mail:                      # CF Worker 临时邮箱配置
  worker_domain: "your-worker.workers.dev"
  email_domains: ["yourdomain.com"]
  admin_password: "your-admin-password"

teams:                          # 母号配置
  - name: "team-1"
    email: "your@email.com"
    password: "password"        # 可留空，留空时自动走邮箱 OTP
    max_invites: 4

proxy:                          # 代理（可选）
  http: "http://proxy:port"
```

### 3. 运行脚本

#### 获取开卡 Team 信息

```bash
python get_tokens.py
```

> 注册之后，绑定完卡，写入到配置文件里面

#### 完整流程

```bash
python gpt-team-new.py
```

> 完整流程包括：注册+邀请+Codex+上传cpa

## 脚本说明

- `get_tokens.py` - 获取开卡 Team 的账号信息
- `gpt-team-new.py` - 完整团队管理（注册子号 + 邀请 + Codex + 上传 cpa）

## 压缩包内容

- `get_tokens.py` - 获取开卡 Team 信息
- `gpt-team-new.py` - 完整团队管理
- `config.yaml` - 配置模板
- `accounts.txt` - 账号信息存储文件

## 注意事项

1. 本工具仅用于个人学习和研究，请勿用于任何违法或不当用途
2. 使用前请确保已正确部署 Cloudflare Worker 临时邮箱服务
3. 绑卡步骤需要手动操作，请按照脚本提示完成
4. 如有问题，请检查网络连接和代理设置

## 免责声明

本工具仅供学习和研究使用，使用本工具产生的一切后果由使用者自行承担。
