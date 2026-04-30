#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mail_service.py
===============
共享临时邮箱服务，供 GPT-team 脚本复用。AI by zb
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests


@dataclass(frozen=True)
class TempMailConfig:
    """临时邮箱配置载体。AI by zb"""

    worker_domain: str
    admin_password: str


def create_temp_email(
    session: requests.Session,
    config: TempMailConfig,
    logger: Optional[logging.Logger] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """创建临时邮箱并返回 `(email, mail_token)`。AI by zb"""

    try:
        resp = session.get(
            f"https://{config.worker_domain}/api/generate",
            params={"mode": "human", "length": 16},
            headers={"X-Admin-Token": config.admin_password, "Content-Type": "application/json"},
            timeout=15,
            verify=False,
        )
        if resp.status_code == 200:
            data = resp.json()
            email = data.get("email")
            token = config.admin_password
            if email:
                if logger:
                    logger.info("创建临时邮箱成功: %s", email)
                return str(email), str(token or "")
        if logger:
            logger.warning("创建临时邮箱失败: HTTP %s | %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        if logger:
            logger.warning("创建临时邮箱异常: %s", exc)
    return None, None


def fetch_emails_list(
    session: requests.Session,
    config: TempMailConfig,
    email: str,
    jwt_token: str,
) -> List[Dict[str, Any]]:
    """按邮箱地址获取收件列表。AI by zb"""

    try:
        resp = session.get(
            f"https://{config.worker_domain}/api/emails",
            params={"mailbox": email, "limit": 10, "offset": 0},
            headers={"Authorization": f"Bearer {jwt_token}"},
            verify=False,
            timeout=30,
        )
        if resp.status_code == 200:
            rows = resp.json()
            return rows if isinstance(rows, list) else []
    except Exception:
        pass
    return []


def extract_otp(content: str) -> Optional[str]:
    """从邮件主题或正文中提取 OpenAI OTP。AI by zb"""

    if not content:
        return None

    match = re.search(r"code is\s+(\d{6,10})\b", content, re.IGNORECASE)
    if match:
        return match.group(1)

    match = re.search(r"background-color:\s*#F3F3F3[^>]*>[\s\S]*?(\d{6})[\s\S]*?</p>", content)
    if match:
        return match.group(1)

    for pattern in [r">\s*(\d{6})\s*<", r"(?<![#&])\b(\d{6})\b"]:
        for code in re.findall(pattern, content):
            if code != "177010":
                return code
    return None


def wait_for_otp(
    session: requests.Session,
    config: TempMailConfig,
    email: str,
    jwt_token: str,
    timeout: int = 120,
    logger: Optional[logging.Logger] = None,
) -> Optional[str]:
    """按邮箱地址轮询等待 OTP。AI by zb"""

    seen_ids: set = set()
    start = time.time()
    while time.time() - start < timeout:
        for item in fetch_emails_list(session, config, email, jwt_token):
            if not isinstance(item, dict):
                continue
            email_id = item.get("id")
            if email_id in seen_ids:
                continue
            seen_ids.add(email_id)

            code = extract_otp(str(item.get("subject") or ""))
            if not code:
                code = extract_otp(
                    str(item.get("raw") or item.get("content") or item.get("text") or "")
                )
            if code:
                if logger:
                    logger.info("收到验证码: %s", code)
                return code
        time.sleep(3)

    if logger:
        logger.warning("等待验证码超时（%ds）", timeout)
    return None
