from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from telethon import TelegramClient, events
from telethon.tl.custom.message import Message


LOGGER = logging.getLogger("telegram_button_automation")


def setup_logging() -> None:
    """初始化日志输出格式，方便观察自动化过程。AI by zb"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def parse_args() -> argparse.Namespace:
    """解析命令行参数，允许外部指定配置文件路径。AI by zb"""
    parser = argparse.ArgumentParser(description="Telegram 按钮自动点击与自动回复工具")
    parser.add_argument(
        "--config",
        default="config.json",
        help="配置文件路径，默认读取当前目录下的 config.json",
    )
    return parser.parse_args()


def load_config(config_path: Path) -> dict[str, Any]:
    """读取并校验配置文件，缺失关键字段时直接抛错。AI by zb"""
    if not config_path.exists():
        raise FileNotFoundError(f"未找到配置文件: {config_path}")

    config = json.loads(config_path.read_text(encoding="utf-8"))
    required_fields = ["api_id", "api_hash", "phone", "bot_username"]
    missing_fields = [field for field in required_fields if not config.get(field)]
    if missing_fields:
        missing_text = ", ".join(missing_fields)
        raise ValueError(f"配置缺少必要字段: {missing_text}")

    config.setdefault("history_limit", 20)
    config.setdefault("session_name", "telegram_button_agent")
    config.setdefault("startup_actions", [])
    config.setdefault("message_rules", [])
    config.setdefault("proxy", {"enabled": False})
    return config


def normalize_text(text: str) -> str:
    """统一文本匹配格式，减少大小写差异带来的干扰。AI by zb"""
    return text.casefold().strip()


def match_keywords(message_text: str, keywords: list[str]) -> bool:
    """判断消息是否命中任意关键词。AI by zb"""
    normalized_text = normalize_text(message_text)
    return any(normalize_text(keyword) in normalized_text for keyword in keywords if keyword)


def build_proxy_config(config: dict[str, Any]) -> dict[str, Any] | None:
    """将配置文件中的代理项转换为 Telethon 可识别的格式。AI by zb"""
    proxy = config.get("proxy")
    if not isinstance(proxy, dict) or not proxy.get("enabled"):
        return None

    proxy_type = str(proxy.get("proxy_type", "")).strip().lower()
    addr = str(proxy.get("addr", "")).strip()
    port = proxy.get("port")

    if not proxy_type or not addr or not port:
        raise ValueError("启用代理时，proxy_type、addr、port 都必须填写")

    proxy_config: dict[str, Any] = {
        "proxy_type": proxy_type,
        "addr": addr,
        "port": int(port),
    }

    username = str(proxy.get("username", "")).strip()
    password = str(proxy.get("password", "")).strip()
    if username:
        proxy_config["username"] = username
    if password:
        proxy_config["password"] = password
    if "rdns" in proxy:
        proxy_config["rdns"] = bool(proxy.get("rdns"))

    return proxy_config


async def click_button_from_recent_messages(
    client: TelegramClient,
    chat: Any,
    button_text: str,
    history_limit: int,
) -> bool:
    """从最近消息中查找并点击指定按钮，成功返回 True。AI by zb"""
    async for message in client.iter_messages(chat, limit=history_limit):
        if not message.buttons:
            continue

        try:
            await message.click(text=button_text)
            LOGGER.info("已点击按钮: %s", button_text)
            return True
        except Exception:
            continue

    return False


async def send_plain_message(client: TelegramClient, chat: Any, text: str) -> None:
    """向目标会话发送普通消息。AI by zb"""
    await client.send_message(chat, text)
    LOGGER.info("已发送消息: %s", text)


async def send_reply_message(client: TelegramClient, chat: Any, event_message: Message, text: str) -> None:
    """针对指定消息发送回复，适合机器人要求继续输入的场景。AI by zb"""
    await client.send_message(chat, text, reply_to=event_message.id)
    LOGGER.info("已回复消息: %s", text)


async def prompt_input_text(prompt_text: str) -> str:
    """在终端中等待手动输入，并返回去除首尾空白后的结果。AI by zb"""
    return (await asyncio.to_thread(input, prompt_text)).strip()


async def execute_action(
    client: TelegramClient,
    chat: Any,
    action: dict[str, Any],
    history_limit: int,
    event_message: Message | None = None,
) -> None:
    """执行单个动作，支持发送消息、点击按钮、回复消息和等待。AI by zb"""
    delay_seconds = float(action.get("delay_seconds", 0))
    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)

    action_type = str(action.get("type", "")).strip().lower()

    if action_type == "sleep":
        seconds = float(action.get("seconds", 0))
        if seconds > 0:
            LOGGER.info("等待 %.1f 秒", seconds)
            await asyncio.sleep(seconds)
        return

    text = str(action.get("text", "")).strip()
    if action_type in {"message", "button", "reply"} and not text:
        raise ValueError(f"动作缺少 text 字段: {action}")

    if action_type == "message":
        await send_plain_message(client, chat, text)
        return

    if action_type == "reply":
        if event_message is None:
            raise ValueError("reply 动作必须绑定消息事件")
        await send_reply_message(client, chat, event_message, text)
        return

    if action_type == "prompt_reply":
        if event_message is None:
            raise ValueError("prompt_reply 动作必须绑定消息事件")
        prompt_text = str(action.get("prompt", "请输入回复内容: "))
        input_text = await prompt_input_text(prompt_text)
        if not input_text:
            LOGGER.warning("输入为空，已跳过本次回复")
            return
        await send_reply_message(client, chat, event_message, input_text)
        return

    if action_type == "button":
        clicked = await click_button_from_recent_messages(client, chat, text, history_limit)
        if not clicked:
            LOGGER.info("未找到按钮，回退为发送同名文本: %s", text)
            await send_plain_message(client, chat, text)
        return

    raise ValueError(f"不支持的动作类型: {action_type}")


async def execute_actions(
    client: TelegramClient,
    chat: Any,
    actions: list[dict[str, Any]],
    history_limit: int,
    event_message: Message | None = None,
) -> None:
    """按顺序执行动作列表。AI by zb"""
    for action in actions:
        await execute_action(
            client=client,
            chat=chat,
            action=action,
            history_limit=history_limit,
            event_message=event_message,
        )


async def run_automation(config_path: Path) -> None:
    """启动 Telegram 自动化主流程，完成登录、监听和规则处理。AI by zb"""
    setup_logging()
    config = load_config(config_path)
    session_path = config_path.parent / str(config["session_name"])
    proxy = build_proxy_config(config)
    if proxy:
        LOGGER.info("已启用代理: %s://%s:%s", proxy["proxy_type"], proxy["addr"], proxy["port"])

    client = TelegramClient(
        str(session_path),
        int(config["api_id"]),
        str(config["api_hash"]),
        proxy=proxy,
    )
    await client.start(phone=str(config["phone"]))

    bot_entity = await client.get_entity(str(config["bot_username"]))
    history_limit = int(config["history_limit"])
    message_rules = list(config["message_rules"])
    startup_actions = list(config["startup_actions"])

    @client.on(events.NewMessage(chats=bot_entity))
    async def handle_bot_message(event: events.NewMessage.Event) -> None:
        """处理机器人新消息，命中规则后执行对应动作。AI by zb"""
        message_text = event.raw_text or ""
        LOGGER.info("收到消息: %s", message_text.replace("\n", " | "))

        for rule in message_rules:
            keywords = list(rule.get("keywords", []))
            actions = list(rule.get("actions", []))
            if not keywords or not actions:
                continue
            if match_keywords(message_text, keywords):
                LOGGER.info("命中规则关键词: %s", ", ".join(keywords))
                await execute_actions(
                    client=client,
                    chat=bot_entity,
                    actions=actions,
                    history_limit=history_limit,
                    event_message=event.message,
                )

    if startup_actions:
        LOGGER.info("开始执行启动动作")
        await execute_actions(
            client=client,
            chat=bot_entity,
            actions=startup_actions,
            history_limit=history_limit,
        )

    LOGGER.info("已进入监听状态，按 Ctrl+C 退出")
    await client.run_until_disconnected()


def main() -> None:
    """程序入口，负责拼装配置路径并启动异步逻辑。AI by zb"""
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    asyncio.run(run_automation(config_path))


if __name__ == "__main__":
    main()
