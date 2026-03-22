#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sub2api_service.py
==================
共享 Sub2Api 上传服务，供 GPT-team 脚本复用。AI by zb
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import requests


DEFAULT_SUB2API_MODEL_MAPPING: Dict[str, str] = {
    "gpt-3.5-turbo": "gpt-3.5-turbo",
    "gpt-3.5-turbo-0125": "gpt-3.5-turbo-0125",
    "gpt-3.5-turbo-1106": "gpt-3.5-turbo-1106",
    "gpt-3.5-turbo-16k": "gpt-3.5-turbo-16k",
    "gpt-4": "gpt-4",
    "gpt-4-turbo": "gpt-4-turbo",
    "gpt-4-turbo-preview": "gpt-4-turbo-preview",
    "gpt-4o": "gpt-4o",
    "gpt-4o-2024-08-06": "gpt-4o-2024-08-06",
    "gpt-4o-2024-11-20": "gpt-4o-2024-11-20",
    "gpt-4o-mini": "gpt-4o-mini",
    "gpt-4o-mini-2024-07-18": "gpt-4o-mini-2024-07-18",
    "gpt-4.5-preview": "gpt-4.5-preview",
    "gpt-4.1": "gpt-4.1",
    "gpt-4.1-mini": "gpt-4.1-mini",
    "gpt-4.1-nano": "gpt-4.1-nano",
    "o1": "o1",
    "o1-preview": "o1-preview",
    "o1-mini": "o1-mini",
    "o1-pro": "o1-pro",
    "o3": "o3",
    "o3-mini": "o3-mini",
    "o3-pro": "o3-pro",
    "o4-mini": "o4-mini",
    "gpt-5": "gpt-5",
    "gpt-5-2025-08-07": "gpt-5-2025-08-07",
    "gpt-5-chat": "gpt-5-chat",
    "gpt-5-chat-latest": "gpt-5-chat-latest",
    "gpt-5-codex": "gpt-5-codex",
    "gpt-5.3-codex-spark": "gpt-5.3-codex-spark",
    "gpt-5-pro": "gpt-5-pro",
    "gpt-5-pro-2025-10-06": "gpt-5-pro-2025-10-06",
    "gpt-5-mini": "gpt-5-mini",
    "gpt-5-mini-2025-08-07": "gpt-5-mini-2025-08-07",
    "gpt-5-nano": "gpt-5-nano",
    "gpt-5-nano-2025-08-07": "gpt-5-nano-2025-08-07",
    "gpt-5.1": "gpt-5.1",
    "gpt-5.1-2025-11-13": "gpt-5.1-2025-11-13",
    "gpt-5.1-chat-latest": "gpt-5.1-chat-latest",
    "gpt-5.1-codex": "gpt-5.1-codex",
    "gpt-5.1-codex-max": "gpt-5.1-codex-max",
    "gpt-5.1-codex-mini": "gpt-5.1-codex-mini",
    "gpt-5.2": "gpt-5.2",
    "gpt-5.2-2025-12-11": "gpt-5.2-2025-12-11",
    "gpt-5.2-chat-latest": "gpt-5.2-chat-latest",
    "gpt-5.2-codex": "gpt-5.2-codex",
    "gpt-5.2-pro": "gpt-5.2-pro",
    "gpt-5.2-pro-2025-12-11": "gpt-5.2-pro-2025-12-11",
    "gpt-5.4": "gpt-5.4",
    "gpt-5.4-2026-03-05": "gpt-5.4-2026-03-05",
    "gpt-5.3-codex": "gpt-5.3-codex",
    "chatgpt-4o-latest": "chatgpt-4o-latest",
    "gpt-4o-audio-preview": "gpt-4o-audio-preview",
    "gpt-4o-realtime-preview": "gpt-4o-realtime-preview",
}


def normalize_group_ids(raw_group_ids: Any, default: Optional[List[int]] = None) -> List[int]:
    """将配置中的 group_ids 规范化为整数列表。AI by zb"""

    default = list(default or [3])
    if isinstance(raw_group_ids, list):
        normalized = [
            int(item) for item in raw_group_ids if str(item).strip().lstrip("-").isdigit()
        ]
        return normalized or default
    if str(raw_group_ids).strip().lstrip("-").isdigit():
        return [int(raw_group_ids)]
    return default


@dataclass(frozen=True)
class Sub2ApiConfig:
    """Sub2Api 配置载体。AI by zb"""

    base_url: str
    bearer: str
    email: str
    password: str
    group_ids: List[int]
    client_id: str
    model_mapping: Dict[str, str] = field(
        default_factory=lambda: DEFAULT_SUB2API_MODEL_MAPPING.copy()
    )


class Sub2ApiUploader:
    """Sub2Api 上传器。AI by zb"""

    def __init__(
        self,
        session: requests.Session,
        config: Sub2ApiConfig,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.session = session
        self.config = config
        self.logger = logger
        self._auth_lock = threading.Lock()
        self._bearer_holder = [config.bearer]

    @staticmethod
    def _decode_jwt_payload(token: str) -> Dict[str, Any]:
        """解码 JWT payload，不校验签名。AI by zb"""

        try:
            parts = token.split(".")
            if len(parts) != 3:
                return {}
            payload = parts[1]
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding
            decoded = base64.urlsafe_b64decode(payload)
            data = json.loads(decoded)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def login(self) -> str:
        """登录 Sub2Api 并返回 bearer token。AI by zb"""

        if not self.config.base_url or not self.config.email or not self.config.password:
            return ""
        try:
            resp = self.session.post(
                f"{self.config.base_url}/api/v1/auth/login",
                json={"email": self.config.email, "password": self.config.password},
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                timeout=15,
                verify=False,
            )
            data = resp.json()
            token = (
                data.get("token")
                or data.get("access_token")
                or (data.get("data") or {}).get("token")
                or (data.get("data") or {}).get("access_token")
                or ""
            )
            return str(token).strip()
        except Exception as exc:
            if self.logger:
                self.logger.warning("[Sub2Api] 登录失败: %s", exc)
            return ""

    def build_account_payload(self, email: str, tokens: Dict[str, Any]) -> Dict[str, Any]:
        """构建 Sub2Api 上传 payload。AI by zb"""

        access_token = str(tokens.get("access_token") or "")
        refresh_token = str(tokens.get("refresh_token") or "")
        id_token = str(tokens.get("id_token") or "")

        at_payload = self._decode_jwt_payload(access_token) if access_token else {}
        at_auth = at_payload.get("https://api.openai.com/auth") or {}
        chatgpt_account_id = at_auth.get("chatgpt_account_id", "") or tokens.get("account_id", "")
        chatgpt_user_id = at_auth.get("chatgpt_user_id", "")
        exp_timestamp = at_payload.get("exp", 0)
        expires_at = (
            exp_timestamp
            if isinstance(exp_timestamp, int) and exp_timestamp > 0
            else int(time.time()) + 863999
        )

        it_payload = self._decode_jwt_payload(id_token) if id_token else {}
        it_auth = it_payload.get("https://api.openai.com/auth") or {}
        organization_id = it_auth.get("organization_id", "")
        if not organization_id:
            organizations = it_auth.get("organizations") or []
            if organizations:
                organization_id = (organizations[0] or {}).get("id", "")

        return {
            "auto_pause_on_expired": True,
            "concurrency": 10,
            "credentials": {
                "access_token": access_token,
                "chatgpt_account_id": chatgpt_account_id,
                "chatgpt_user_id": chatgpt_user_id,
                "client_id": self.config.client_id,
                "expires_in": 863999,
                "expires_at": expires_at,
                "model_mapping": self.config.model_mapping,
                "organization_id": organization_id,
                "refresh_token": refresh_token,
            },
            "extra": {
                "email": email,
                "openai_oauth_responses_websockets_v2_enabled": True,
                "openai_oauth_responses_websockets_v2_mode": "off",
            },
            "group_ids": list(self.config.group_ids or [3]),
            "name": email,
            "notes": "",
            "platform": "openai",
            "priority": 1,
            "type": "oauth",
            "rate_multiplier": 1,
        }

    def push_account(self, email: str, tokens: Dict[str, Any]) -> bool:
        """上传账号到 Sub2Api，401 时自动刷新 bearer 后重试。AI by zb"""

        if not self.config.base_url or not str(tokens.get("refresh_token") or "").strip():
            return False

        url = f"{self.config.base_url}/api/v1/admin/accounts"
        payload = self.build_account_payload(email, tokens)

        def _do_request(bearer: str) -> Tuple[int, str]:
            try:
                resp = self.session.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {bearer}",
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/plain, */*",
                        "Referer": f"{self.config.base_url}/admin/accounts",
                    },
                    timeout=20,
                    verify=False,
                )
                return resp.status_code, resp.text
            except Exception as exc:
                return 0, str(exc)

        bearer = self._bearer_holder[0]
        status, body = _do_request(bearer)

        if status == 401 and self.config.email and self.config.password:
            with self._auth_lock:
                if self._bearer_holder[0] == bearer:
                    new_token = self.login()
                    if new_token:
                        self._bearer_holder[0] = new_token
            bearer = self._bearer_holder[0]
            status, body = _do_request(bearer)

        ok = status in (200, 201)
        if self.logger:
            if ok:
                self.logger.info("[Sub2Api] 上传成功: %s | HTTP %s", email, status)
            else:
                self.logger.warning("[Sub2Api] 上传失败: %s | HTTP %s | %s", email, status, body[:500])
        return ok
