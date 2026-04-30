# Telegram 按钮自动点击与自动回复

这个目录是独立的小工具，目标是用 **Telegram 用户账号会话** 去完成：

- 按按钮文字触发机器人菜单
- 点击失败时回退为发送同名文本
- 收到机器人消息后按关键词自动回复

## 适用场景

适合你截图里的这类机器人：

- 底部是 `Reply Keyboard` 按钮
- 机器人收到按钮文字后继续要求输入内容
- 你希望把“点按钮 -> 收到提示 -> 回复内容”串起来自动化

## 前置条件

运行前你需要准备：

1. `api_id`
2. `api_hash`
3. 你的 Telegram 登录手机号
4. 目标机器人用户名，例如 `some_bot`

注意：

- 这里只能用 **用户账号**
- 不是 `bot token`
- 仅有 `api_id` 不够，**还必须有 `api_hash`**
- 如果当前网络无法直连 Telegram，还需要本地代理

## 安装

```bash
cd telegram_button_automation
pip install -r requirements.txt
```

## 配置

先复制一份配置：

```bash
copy config.example.json config.json
```

然后修改 `config.json`：

```json
{
  "api_id": 12345678,
  "api_hash": "你的_api_hash",
  "phone": "+8613800000000",
  "session_name": "telegram_button_agent",
  "bot_username": "你的机器人用户名",
  "history_limit": 20,
  "proxy": {
    "enabled": false,
    "proxy_type": "socks5",
    "addr": "127.0.0.1",
    "port": 7890,
    "username": "",
    "password": "",
    "rdns": true
  },
  "startup_actions": [
    {
      "type": "message",
      "text": "/start",
      "delay_seconds": 1
    },
    {
      "type": "button",
      "text": "兑换卡密",
      "delay_seconds": 2
    }
  ],
  "message_rules": [
    {
      "keywords": [
        "请发送卡密"
      ],
      "actions": [
        {
          "type": "prompt_reply",
          "prompt": "机器人要求发送卡密，请输入本次卡密：",
          "delay_seconds": 1
        }
      ]
    }
  ]
}
```

## 动作说明

支持的 `type`：

- `message`：直接发送一条消息
- `button`：优先查找最近消息里的按钮并点击，点不到时发送同名文本
- `reply`：回复当前触发消息
- `prompt_reply`：收到消息后在终端手动输入，再把输入内容回复出去
- `sleep`：单纯等待，配合复杂流程使用

## 代理配置

如果日志持续出现这类内容：

```text
Connecting to 149.154.xxx.xxx:443/TcpFull...
Attempt 1 at connecting failed: TimeoutError
```

一般说明当前网络到 Telegram 的连接被阻断或未走代理。

此时请把 `config.json` 中的 `proxy.enabled` 改为 `true`，并填入你本地代理的实际监听端口，例如：

```json
"proxy": {
  "enabled": true,
  "proxy_type": "socks5",
  "addr": "127.0.0.1",
  "port": 7890,
  "username": "",
  "password": "",
  "rdns": true
}
```

说明：

- `proxy_type` 支持 `socks5`、`socks4`、`http`
- 优先建议使用 `socks5`
- 如果你用的是 Clash / Clash Verge，请以它当前显示的本地端口为准，不要直接照抄示例值

## 运行

```bash
cd telegram_button_automation
python main.py --config config.json
```

首次运行会要求你输入：

- 登录验证码
- 如果账号开启了二次验证，还会要求输入密码

登录成功后会在当前目录生成本地会话文件：

- `telegram_button_agent.session`

## 一个接近你截图的例子

如果机器人流程是：

1. 先点 `兑换卡密`
2. 机器人回复 `请发送卡密`
3. 脚本会在终端提示你手动输入卡密

那默认示例配置已经是这个流程，直接改掉以下字段即可：

- `api_id`
- `api_hash`
- `phone`
- `bot_username`

输入卡密时不需要改配置，运行过程中按提示键入即可。

## 常见说明

### 1. 为什么不用 Bot API

因为 Bot API 不能代替“用户”去点机器人按钮。这个工具走的是 **用户侧 Telethon 会话**。

### 2. 为什么按钮点击会回退成发送同名文本

你截图这类 `Reply Keyboard` 本质上通常等价于发一条同名文本，所以回退策略更稳。

### 3. 如果后面还有第二轮、第三轮交互怎么办

继续往 `message_rules` 里加规则即可，例如：

```json
{
  "keywords": ["请输入手机号"],
  "actions": [
    {
      "type": "reply",
      "text": "13800000000"
    }
  ]
}
```
