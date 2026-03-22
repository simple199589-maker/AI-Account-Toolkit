#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gpt-team-xianyu.py
================
使用咸鱼号登录并拉空间
全新纯 HTTP 协议版本（无 Selenium / 无浏览器）
- 注册：使用 ProtocolRegistrar 五步 HTTP 流程 + Sentinel Token
- 母号登录：HTTP OAuth + PKCE，自动拉取 account_id / auth_token
- Codex 授权：HTTP 交换 code → token → 上传到 Sub2Api
- 子号邀请：注册成功后自动发送团队邀请
配置文件: config.yaml（兼容原格式）
"""

from __future__ import annotations

import base64
import csv
import datetime as dt
import hashlib
import json
import logging
import os
import random
import re
import secrets
import string
import sys
import time
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse

import requests
import urllib3
import yaml
from codex_login_tool import CodexLoginMode, CodexLoginTool
from mail_service import (
    TempMailConfig,
    create_temp_email as shared_create_temp_email,
    extract_otp as shared_extract_otp,
    fetch_emails_list as shared_fetch_emails_list,
    wait_for_otp as shared_wait_for_otp,
)
from sub2api_service import Sub2ApiConfig, Sub2ApiUploader, normalize_group_ids
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 消除 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# ① 读取 config.yaml
# ============================================================
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_FILE = os.path.join(_BASE_DIR, "config.yaml")


def _load_config() -> Dict[str, Any]:
    if not os.path.exists(_CONFIG_FILE):
        raise FileNotFoundError(f"找不到配置文件: {_CONFIG_FILE}\n请先创建 config.yaml")
    with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _as_bool(value: Any) -> bool:
    """将配置值规范化为布尔值。AI by zb"""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _resolve_local_path(path_value: Any, default_name: str) -> str:
    """将输出路径解析到脚本所在目录。AI by zb"""
    raw_path = str(path_value or default_name).strip() or default_name
    if os.path.isabs(raw_path):
        return raw_path
    return os.path.join(_BASE_DIR, raw_path)


_cfg = _load_config()
CODEX_LOGIN_MODE = CodexLoginMode.GPT_TEAM_WORKSPACE

# 账号总数
TOTAL_ACCOUNTS: int = int(_cfg.get("total_accounts", 2))

# 临时邮箱配置
TEMP_MAIL_WORKER_DOMAIN: str = _cfg["temp_mail"]["worker_domain"]
TEMP_MAIL_EMAIL_DOMAINS: List[str] = _cfg["temp_mail"]["email_domains"]
TEMP_MAIL_ADMIN_PASSWORD: str = _cfg["temp_mail"]["admin_password"]
MAIL_CONFIG = TempMailConfig(
    worker_domain=TEMP_MAIL_WORKER_DOMAIN,
    admin_password=TEMP_MAIL_ADMIN_PASSWORD,
)

# 输出文件
ACCOUNTS_FILE: str = _resolve_local_path(_cfg["output"].get("accounts_file", "accounts.txt"), "accounts.txt")
INVITE_TRACKER_FILE: str = _resolve_local_path(_cfg["output"]["invite_tracker_file"], "invite_tracker.json")
TEAM_SESSION_CACHE_FILE: str = _resolve_local_path(
    _cfg["output"].get("team_session_cache_file", "team_session_cache.json"),
    "team_session_cache.json",
)
INVITE_ONLY_TEST_EMAIL: str = "8eu4hijj@joini.cloud"

# Sub2Api 配置
_sub2api_cfg: Dict[str, Any] = _cfg.get("sub2api", {}) or {}
SUB2API_BASE_URL: str = str(_sub2api_cfg.get("base_url", "") or "").strip().rstrip("/")
SUB2API_BEARER: str = str(_sub2api_cfg.get("bearer", "") or "").strip()
SUB2API_EMAIL: str = str(_sub2api_cfg.get("email", "") or "").strip()
SUB2API_PASSWORD: str = str(_sub2api_cfg.get("password", "") or "").strip()
AUTO_UPLOAD_SUB2API: bool = _as_bool(_sub2api_cfg.get("auto_upload_sub2api", False))
SUB2API_GROUP_IDS: List[int] = normalize_group_ids(_sub2api_cfg.get("group_ids", [2]), default=[2])

# 车头（Teams）列表
TEAMS: List[Dict[str, Any]] = _cfg.get("teams", [])

# OAuth 常量（Codex CLI 客户端）
OPENAI_AUTH_BASE = "https://auth.openai.com"
OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OAUTH_REDIRECT_URI = "http://localhost:1455/auth/callback"
OAUTH_SCOPE = "openid profile email offline_access"

print(f"✅ 配置已加载: {_CONFIG_FILE}")
print(f"   注册数量: {TOTAL_ACCOUNTS} | 车头数量: {len(TEAMS)} | 邮箱域名: {TEMP_MAIL_EMAIL_DOMAINS}")

# ============================================================
# ② 日志（仅控制台输出，不写文件）
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("gpt-team")

# ============================================================
# ③ HTTP Session 工厂（带 Retry + Verify=False）
# ============================================================
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/145.0.0.0 Safari/537.36"
)

COMMON_HEADERS: Dict[str, str] = {
    "accept": "application/json",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/json",
    "origin": OPENAI_AUTH_BASE,
    "user-agent": USER_AGENT,
    "sec-ch-ua": '"Google Chrome";v="145", "Not?A_Brand";v="8", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

AUTH_JSON_HEADERS: Dict[str, str] = {
    "accept": "application/json",
    "accept-language": "zh-CN,zh;q=0.9",
    "content-type": "application/json",
    "priority": "u=1, i",
    "user-agent": USER_AGENT,
    "sec-ch-ua": COMMON_HEADERS["sec-ch-ua"],
    "sec-ch-ua-mobile": COMMON_HEADERS["sec-ch-ua-mobile"],
    "sec-ch-ua-platform": COMMON_HEADERS["sec-ch-ua-platform"],
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

NAVIGATE_HEADERS: Dict[str, str] = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": USER_AGENT,
    "sec-ch-ua": '"Google Chrome";v="145", "Not?A_Brand";v="8", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
}


def build_auth_json_headers(
    referer: str,
    device_id: str = "",
    include_datadog: bool = True,
    include_device_id: bool = True,
) -> Dict[str, str]:
    """构造与浏览器抓包尽量对齐的 auth JSON 请求头。AI by zb"""
    headers = dict(AUTH_JSON_HEADERS)
    headers["origin"] = OPENAI_AUTH_BASE
    headers["referer"] = referer
    if include_device_id and device_id:
        headers["oai-device-id"] = device_id
    if include_datadog:
        headers.update(generate_datadog_trace())
    return headers


def create_session(proxy: str = "") -> requests.Session:
    """创建带重试的 requests.Session"""
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    if proxy:
        s.proxies = {"http": proxy, "https": proxy}
    return s


# 全局 HTTP Session（供临时邮箱 / Sub2Api 等非 OpenAI 请求使用）
http_session = create_session()
_sub2api_uploader = Sub2ApiUploader(
    http_session,
    Sub2ApiConfig(
        base_url=SUB2API_BASE_URL,
        bearer=SUB2API_BEARER,
        email=SUB2API_EMAIL,
        password=SUB2API_PASSWORD,
        group_ids=SUB2API_GROUP_IDS,
        client_id=OAUTH_CLIENT_ID,
    ),
    logger,
)

# ============================================================
# ④ PKCE 工具
# ============================================================

def generate_pkce() -> Tuple[str, str]:
    """返回 (code_verifier, code_challenge)"""
    code_verifier = (
        base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")
    )
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


# ============================================================
# ⑤ Datadog Trace（模拟浏览器追踪头）
# ============================================================

def generate_datadog_trace() -> Dict[str, str]:
    trace_id = str(random.getrandbits(64))
    parent_id = str(random.getrandbits(64))
    trace_hex = format(int(trace_id), "016x")
    parent_hex = format(int(parent_id), "016x")
    return {
        "traceparent": f"00-0000000000000000{trace_hex}-{parent_hex}-01",
        "tracestate": "dd=s:1;o:rum",
        "x-datadog-origin": "rum",
        "x-datadog-parent-id": parent_id,
        "x-datadog-sampling-priority": "1",
        "x-datadog-trace-id": trace_id,
    }


# ============================================================
# ⑥ SentinelTokenGenerator（OpenAI 反机器人令牌）
# ============================================================

class SentinelTokenGenerator:
    """生成 openai-sentinel-token，绕过注册/登录反机器人检测"""
    MAX_ATTEMPTS = 500_000

    def __init__(self, device_id: Optional[str] = None):
        self.device_id = device_id or str(uuid.uuid4())
        self.requirements_seed = str(random.random())
        self.sid = str(uuid.uuid4())

    @staticmethod
    def _fnv1a_32(text: str) -> str:
        h = 2166136261
        for ch in text:
            h ^= ord(ch)
            h = (h * 16777619) & 0xFFFFFFFF
        h ^= h >> 16
        h = (h * 2246822507) & 0xFFFFFFFF
        h ^= h >> 13
        h = (h * 3266489909) & 0xFFFFFFFF
        h ^= h >> 16
        h &= 0xFFFFFFFF
        return format(h, "08x")

    @staticmethod
    def _b64(data: Any) -> str:
        js = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        return base64.b64encode(js.encode("utf-8")).decode("ascii")

    def _get_config(self) -> List[Any]:
        now = dt.datetime.now(dt.timezone.utc).strftime(
            "%a %b %d %Y %H:%M:%S GMT+0000 (Coordinated Universal Time)"
        )
        perf_now = random.uniform(1000, 50000)
        time_origin = time.time() * 1000 - perf_now
        return [
            "1920x1080", now, 4294705152, random.random(), USER_AGENT,
            "https://sentinel.openai.com/sentinel/20260124ceb8/sdk.js",
            None, None, "en-US", "en-US,en", random.random(),
            "vendorSub−undefined", "location", "Object",
            perf_now, self.sid, "", random.choice([4, 8, 12, 16]), time_origin,
        ]

    def generate_requirements_token(self) -> str:
        cfg = self._get_config()
        cfg[3] = 1
        cfg[9] = round(random.uniform(5, 50))
        return "gAAAAAC" + self._b64(cfg)

    def generate_token(self, seed: Optional[str] = None, difficulty: Optional[str] = None) -> str:
        if seed is None:
            seed = self.requirements_seed
            difficulty = difficulty or "0"
        cfg = self._get_config()
        start = time.time()
        for i in range(self.MAX_ATTEMPTS):
            cfg[3] = i
            cfg[9] = round((time.time() - start) * 1000)
            data = self._b64(cfg)
            hash_hex = self._fnv1a_32(seed + data)
            if hash_hex[: len(difficulty or "0")] <= (difficulty or "0"):
                return "gAAAAAB" + data + "~S"
        return "gAAAAAB" + self._b64(str(None))


# ============================================================
# ⑦ 从 Sentinel 服务器拉取挑战并构建完整 Token
# ============================================================

def fetch_sentinel_challenge(
    session: requests.Session, device_id: str, flow: str = "authorize_continue"
) -> Optional[Dict[str, Any]]:
    gen = SentinelTokenGenerator(device_id=device_id)
    body = {"p": gen.generate_requirements_token(), "id": device_id, "flow": flow}
    headers = {
        "Content-Type": "text/plain;charset=UTF-8",
        "Referer": "https://sentinel.openai.com/backend-api/sentinel/frame.html",
        "User-Agent": USER_AGENT,
        "Origin": "https://sentinel.openai.com",
        "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }
    try:
        resp = session.post(
            "https://sentinel.openai.com/backend-api/sentinel/req",
            data=json.dumps(body),
            headers=headers,
            timeout=15,
            verify=False,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def build_sentinel_token(
    session: requests.Session, device_id: str, flow: str = "authorize_continue"
) -> Optional[str]:
    """获取 Sentinel 挑战并求解，返回 openai-sentinel-token 字符串"""
    challenge = fetch_sentinel_challenge(session, device_id, flow)
    if not challenge:
        # 无法获取挑战时降级：只用本地生成 token
        gen = SentinelTokenGenerator(device_id=device_id)
        return json.dumps({
            "p": gen.generate_requirements_token(), "t": "", "c": "",
            "id": device_id, "flow": flow,
        })
    c_value = challenge.get("token", "")
    pow_data = challenge.get("proofofwork", {})
    gen = SentinelTokenGenerator(device_id=device_id)
    if isinstance(pow_data, dict) and pow_data.get("required") and pow_data.get("seed"):
        p_value = gen.generate_token(
            seed=pow_data.get("seed"), difficulty=pow_data.get("difficulty", "0")
        )
    else:
        p_value = gen.generate_requirements_token()
    return json.dumps({"p": p_value, "t": "", "c": c_value, "id": device_id, "flow": flow})


# ============================================================
# ⑧ 临时邮箱 API（与 get_tokens.py 共用）
# ============================================================

def create_temp_email() -> Tuple[Optional[str], Optional[str]]:
    """共享临时邮箱创建入口。AI by zb"""
    return shared_create_temp_email(http_session, MAIL_CONFIG, logger)


def _get_jwt_for_address(email_address: str) -> str:
    """旧 JWT 获取逻辑兼容保留，当前流程已不再使用。AI by zb"""
    return ""


def fetch_emails_list(email: str, jwt_token: str) -> List[Dict[str, Any]]:
    """共享收件列表入口。AI by zb"""
    return shared_fetch_emails_list(http_session, MAIL_CONFIG, email, jwt_token)


def _extract_otp_from_raw(content: str) -> Optional[str]:
    """共享 OTP 提取入口。AI by zb"""
    return shared_extract_otp(content)


def wait_for_otp(email: str, jwt_token: str, timeout: int = 120) -> Optional[str]:
    """共享 OTP 轮询入口。AI by zb"""
    return shared_wait_for_otp(
        http_session,
        MAIL_CONFIG,
        email,
        jwt_token,
        timeout=timeout,
        logger=logger,
    )


MAIL_TIMEZONE = dt.timezone(dt.timedelta(hours=8))
OTP_FALLBACK_SEND_DELAY_SECONDS = 8


def build_mail_item_identity(item: Dict[str, Any]) -> str:
    """构造邮件唯一标识，便于过滤旧验证码邮件。AI by zb"""
    if not isinstance(item, dict):
        return ""
    mail_id = str(item.get("id") or "").strip()
    if mail_id:
        return mail_id
    subject = str(item.get("subject") or "")
    raw = str(item.get("raw") or item.get("content") or item.get("text") or "")
    return f"{subject}|{raw[:120]}"


def snapshot_mail_identities(email: str, jwt_token: str) -> set:
    """抓取当前邮箱中的邮件标识快照。AI by zb"""
    identities: set = set()
    for item in fetch_emails_list(email, jwt_token):
        identity = build_mail_item_identity(item)
        if identity:
            identities.add(identity)
    return identities


def parse_mail_item_time(item: Dict[str, Any]) -> Optional[dt.datetime]:
    """解析邮件时间并统一转换到 +08:00。AI by zb"""
    if not isinstance(item, dict):
        return None

    time_keys = [
        "received_at", "receivedAt", "created_at", "createdAt",
        "date", "timestamp", "time", "updated_at", "updatedAt",
    ]

    for key in time_keys:
        value = item.get(key)
        if value in (None, ""):
            continue

        try:
            if isinstance(value, (int, float)):
                timestamp = float(value)
                if timestamp > 10**12:
                    timestamp /= 1000.0
                return dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc).astimezone(MAIL_TIMEZONE)

            raw = str(value).strip()
            if not raw:
                continue
            if raw.isdigit():
                timestamp = float(raw)
                if timestamp > 10**12:
                    timestamp /= 1000.0
                return dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc).astimezone(MAIL_TIMEZONE)

            normalized = raw.replace("Z", "+00:00")
            parsed = dt.datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                # 邮件接口里的 received_at 通常是 UTC，无时区时统一按 UTC 转到 +08:00。
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed.astimezone(MAIL_TIMEZONE)
        except Exception:
            continue

    return None


def sort_mail_items_newest_first(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """尽量按时间倒序排列邮件，优先尝试最新验证码。AI by zb"""
    def sort_key(item: Dict[str, Any]) -> float:
        parsed_time = parse_mail_item_time(item)
        return parsed_time.timestamp() if parsed_time else 0.0

    return sorted(items, key=sort_key, reverse=True)


def extract_otp_from_mail_item(item: Dict[str, Any]) -> Optional[str]:
    """从邮件对象中提取 OTP，优先使用结构化字段。AI by zb"""
    if not isinstance(item, dict):
        return None

    direct_code = str(item.get("verification_code") or "").strip()
    if re.fullmatch(r"\d{6}", direct_code):
        return direct_code

    for key in ("subject", "preview", "raw", "content", "text"):
        code = _extract_otp_from_raw(str(item.get(key) or ""))
        if code:
            return code

    return None


# ============================================================
# ⑨ 随机用户信息生成
# ============================================================

def generate_random_name() -> Tuple[str, str]:
    first = ["James", "Robert", "John", "Michael", "David", "Mary", "Jennifer", "Linda", "Emma", "Olivia"]
    last = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller"]
    return random.choice(first), random.choice(last)


def generate_random_birthday() -> str:
    year = random.randint(1992, 2003)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return f"{year:04d}-{month:02d}-{day:02d}"


def generate_random_password(length: int = 16) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%"
    pwd = list(
        secrets.choice(string.ascii_uppercase)
        + secrets.choice(string.ascii_lowercase)
        + secrets.choice(string.digits)
        + secrets.choice("!@#$%")
        + "".join(secrets.choice(chars) for _ in range(length - 4))
    )
    random.shuffle(pwd)
    return "".join(pwd)


# ============================================================
# ⑩ ProtocolRegistrar：纯 HTTP 五步注册流程
# ============================================================

class ProtocolRegistrar:
    """
    纯 HTTP 注册器（来自 对比/gptzidong），无需 Selenium。
    步骤：
      step0: OAuth 会话初始化 + authorize/continue
      step2: 提交 email + password 注册
      step3: 触发 OTP 发送
      step4: 验证 OTP
      step5: 创建账号（填写姓名/生日）
    """

    def __init__(self, proxy: str = ""):
        self.session = create_session(proxy=proxy)
        self.device_id = str(uuid.uuid4())
        self.sentinel_gen = SentinelTokenGenerator(device_id=self.device_id)
        self.code_verifier: Optional[str] = None
        self.state: Optional[str] = None

    def _headers(self, referer: str, with_sentinel: bool = False) -> Dict[str, str]:
        h = dict(COMMON_HEADERS)
        h["referer"] = referer
        h["oai-device-id"] = self.device_id
        h.update(generate_datadog_trace())
        if with_sentinel:
            h["openai-sentinel-token"] = self.sentinel_gen.generate_token()
        return h

    def step0_init_oauth(self, email: str, client_id: str, redirect_uri: str) -> bool:
        """初始化 OAuth 会话并发送 authorize/continue 请求"""
        self.session.cookies.set("oai-did", self.device_id, domain=".auth.openai.com")
        self.session.cookies.set("oai-did", self.device_id, domain="auth.openai.com")

        code_verifier, code_challenge = generate_pkce()
        self.code_verifier = code_verifier
        self.state = secrets.token_urlsafe(32)

        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": "openid profile email offline_access",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": self.state,
            "screen_hint": "signup",
            "prompt": "login",
        }
        url = f"{OPENAI_AUTH_BASE}/oauth/authorize?{urlencode(params)}"
        try:
            resp = self.session.get(
                url, headers=NAVIGATE_HEADERS, allow_redirects=True, verify=False, timeout=30
            )
        except Exception as e:
            logger.warning("step0a 失败: %s", e)
            return False
        if resp.status_code not in (200, 302):
            logger.warning("step0a 状态异常: %s", resp.status_code)
            return False
        if not any(c.name == "login_session" for c in self.session.cookies):
            logger.warning("step0a 未获取 login_session cookie")
            return False

        h = self._headers(f"{OPENAI_AUTH_BASE}/create-account")
        sentinel = build_sentinel_token(self.session, self.device_id, flow="authorize_continue")
        if sentinel:
            h["openai-sentinel-token"] = sentinel
        try:
            r2 = self.session.post(
                f"{OPENAI_AUTH_BASE}/api/accounts/authorize/continue",
                json={"username": {"kind": "email", "value": email}, "screen_hint": "signup"},
                headers=h,
                verify=False,
                timeout=30,
            )
            if r2.status_code != 200:
                logger.warning("step0b 失败: %s | %s", r2.status_code, r2.text[:200])
            return r2.status_code == 200
        except Exception as e:
            logger.warning("step0b 异常: %s", e)
            return False

    def step2_register_user(self, email: str, password: str) -> bool:
        """提交注册表单（email + password）。AI by zb"""
        url = f"{OPENAI_AUTH_BASE}/api/accounts/user/register"
        payload = {"username": email, "password": password}
        attempts = [("plain", self._headers(f"{OPENAI_AUTH_BASE}/create-account/password", with_sentinel=False))]

        retry_headers = self._headers(f"{OPENAI_AUTH_BASE}/create-account/password", with_sentinel=False)
        retry_sentinel = build_sentinel_token(self.session, self.device_id, flow="authorize_continue")
        if retry_sentinel:
            retry_headers["openai-sentinel-token"] = retry_sentinel
            attempts.append(("sentinel_retry", retry_headers))

        for attempt_name, headers in attempts:
            try:
                resp = self.session.post(
                    url,
                    json=payload,
                    headers=headers,
                    verify=False,
                    timeout=30,
                )
            except Exception as e:
                logger.warning("step2 异常[%s]: %s | email=%s", attempt_name, e, email)
                continue

            if resp.status_code == 200:
                return True
            if resp.status_code in (301, 302):
                loc = resp.headers.get("Location", "")
                return "email-otp" in loc or "email-verification" in loc

            logger.warning("step2 失败[%s]: %s | %s", attempt_name, resp.status_code, resp.text[:200])
            if attempt_name == "plain" and resp.status_code in (400, 401, 403, 429):
                continue
            break

        return False

    def step3_send_otp(self) -> bool:
        """触发验证邮件发送"""
        try:
            h = dict(NAVIGATE_HEADERS)
            h["referer"] = f"{OPENAI_AUTH_BASE}/create-account/password"
            self.session.get(
                f"{OPENAI_AUTH_BASE}/api/accounts/email-otp/send",
                headers=h, verify=False, timeout=30, allow_redirects=True,
            )
            self.session.get(
                f"{OPENAI_AUTH_BASE}/email-verification",
                headers=h, verify=False, timeout=30, allow_redirects=True,
            )
            return True
        except Exception as e:
            logger.warning("step3 异常: %s", e)
            return False

    def step4_validate_otp(self, code: str) -> bool:
        """提交6位验证码"""
        h = self._headers(f"{OPENAI_AUTH_BASE}/email-verification")
        try:
            r = self.session.post(
                f"{OPENAI_AUTH_BASE}/api/accounts/email-otp/validate",
                json={"code": code},
                headers=h,
                verify=False,
                timeout=30,
            )
            if r.status_code != 200:
                logger.warning("step4 失败: %s | code=%s", r.status_code, code)
            return r.status_code == 200
        except Exception as e:
            logger.warning("step4 异常: %s", e)
            return False

    def step5_create_account(self, first_name: str, last_name: str, birthdate: str) -> bool:
        """填写姓名和生日，完成账号创建"""
        h = self._headers(f"{OPENAI_AUTH_BASE}/about-you")
        body = {"name": f"{first_name} {last_name}", "birthdate": birthdate}
        sentinel = build_sentinel_token(
            self.session,
            self.device_id,
            flow="oauth_create_account",
        )
        if sentinel:
            h["openai-sentinel-token"] = sentinel
        try:
            r = self.session.post(
                f"{OPENAI_AUTH_BASE}/api/accounts/create_account",
                json=body, headers=h, verify=False, timeout=30,
            )
            if r.status_code == 200:
                return True
            # 命中 sentinel 风控时重试
            if r.status_code == 403 and "sentinel" in r.text.lower():
                retry_sentinel = build_sentinel_token(
                    self.session,
                    self.device_id,
                    flow="oauth_create_account",
                )
                if retry_sentinel:
                    h["openai-sentinel-token"] = retry_sentinel
                rr = self.session.post(
                    f"{OPENAI_AUTH_BASE}/api/accounts/create_account",
                    json=body, headers=h, verify=False, timeout=30,
                )
                if rr.status_code in (200, 301, 302):
                    return True
                logger.warning(
                    "step5 sentinel 重试失败: HTTP %s | %s",
                    rr.status_code,
                    rr.text[:500],
                )
                return False
            if r.status_code in (301, 302):
                return True
            logger.warning("step5 失败: HTTP %s | %s", r.status_code, r.text[:500])
            return False
        except Exception as e:
            logger.warning("step5 异常: %s", e)
            return False

    def register(
        self,
        email: str,
        jwt_token: str,
        password: str,
        client_id: str = OAUTH_CLIENT_ID,
        redirect_uri: str = OAUTH_REDIRECT_URI,
    ) -> bool:
        """执行完整注册五步，成功返回 True"""
        first_name, last_name = generate_random_name()
        birthdate = generate_random_birthday()

        logger.info("[注册] step0 初始化 OAuth | email=%s", email)
        if not self.step0_init_oauth(email, client_id, redirect_uri):
            logger.warning("[注册] step0 失败 | email=%s", email)
            return False
        time.sleep(1)

        logger.info("[注册] step2 提交注册表单 | email=%s", email)
        if not self.step2_register_user(email, password):
            logger.warning("[注册] step2 失败 | email=%s", email)
            return False
        time.sleep(1)

        logger.info("[注册] step3 发送OTP | email=%s", email)
        if not self.step3_send_otp():
            logger.warning("[注册] step3 失败 | email=%s", email)
            return False

        logger.info("[注册] 等待验证码 | email=%s", email)
        code = wait_for_otp(email, jwt_token, timeout=120)
        if not code:
            logger.warning("[注册] 未收到验证码 | email=%s", email)
            return False

        logger.info("[注册] step4 验证OTP: %s | email=%s", code, email)
        if not self.step4_validate_otp(code):
            logger.warning("[注册] step4 失败 | email=%s", email)
            return False
        time.sleep(1)

        logger.info("[注册] step5 创建账号 | email=%s", email)
        ok = self.step5_create_account(first_name, last_name, birthdate)
        if not ok:
            logger.warning("[注册] step5 失败 | email=%s", email)
        return ok


# ============================================================
# ⑪ HTTP OAuth 登录（子号/母号通用）— 来自 对比/gptzidong
# ============================================================

def _extract_code_from_url(url: str) -> Optional[str]:
    if not url or "code=" not in url:
        return None
    try:
        return parse_qs(urlparse(url).query).get("code", [None])[0]
    except Exception:
        return None


def _follow_and_extract_code(
    session: requests.Session,
    url: str,
    oauth_issuer: str,
    max_depth: int = 10,
) -> Optional[str]:
    """跟随重定向，提取 OAuth code 参数"""
    if max_depth <= 0:
        return None
    try:
        r = session.get(
            url, headers=NAVIGATE_HEADERS, verify=False, timeout=15, allow_redirects=False,
        )
        if r.status_code in (301, 302, 303, 307, 308):
            loc = r.headers.get("Location", "")
            code = _extract_code_from_url(loc)
            if code:
                return code
            if loc.startswith("/"):
                loc = f"{oauth_issuer}{loc}"
            return _follow_and_extract_code(session, loc, oauth_issuer, max_depth - 1)
        if r.status_code == 200:
            return _extract_code_from_url(str(r.url))
    except requests.exceptions.ConnectionError as e:
        m = re.search(r"(https?://localhost[^\s'\"]+)", str(e))
        if m:
            return _extract_code_from_url(m.group(1))
    except Exception:
        pass
    return None


def perform_http_oauth_login(
    email: str,
    password: str = "",
    cf_token: str = "",
    worker_domain: str = "",
    oauth_issuer: str = OPENAI_AUTH_BASE,
    oauth_client_id: str = OAUTH_CLIENT_ID,
    oauth_redirect_uri: str = OAUTH_REDIRECT_URI,
    proxy: str = "",
) -> Optional[Dict[str, Any]]:
    """
    纯 HTTP OAuth 登录，返回包含 access_token/refresh_token 的字典。
    参考自 gptzidong/auto_pool_maintainer.py 的 perform_codex_oauth_login_http。
    """
    session = create_session(proxy=proxy)
    device_id = str(uuid.uuid4())

    session.cookies.set("oai-did", device_id, domain=".auth.openai.com")
    session.cookies.set("oai-did", device_id, domain="auth.openai.com")

    code_verifier, code_challenge = generate_pkce()
    state = secrets.token_urlsafe(32)

    # Step A: 获取 login_session cookie
    logger.info("[Codex] Step A: authorize | email=%s", email)
    authorize_params = {
        "response_type": "code",
        "client_id": oauth_client_id,
        "redirect_uri": oauth_redirect_uri,
        "scope": "openid profile email offline_access",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    authorize_url = f"{oauth_issuer}/oauth/authorize?{urlencode(authorize_params)}"
    try:
        session.get(
            authorize_url, headers=NAVIGATE_HEADERS,
            allow_redirects=True, verify=False, timeout=30,
        )
    except Exception as e:
        logger.warning("[Codex] Step A 失败: %s | email=%s", e, email)
        return None

    # Step B: 提交邮箱
    logger.info("[Codex] Step B: 提交邮箱 | email=%s", email)
    headers = dict(COMMON_HEADERS)
    headers["referer"] = f"{oauth_issuer}/log-in"
    headers["oai-device-id"] = device_id
    headers.update(generate_datadog_trace())

    sentinel_email = build_sentinel_token(session, device_id, flow="authorize_continue")
    if not sentinel_email:
        logger.warning("[Codex] Step B sentinel 失败 | email=%s", email)
        return None
    headers["openai-sentinel-token"] = sentinel_email

    try:
        resp = session.post(
            f"{oauth_issuer}/api/accounts/authorize/continue",
            json={"username": {"kind": "email", "value": email}},
            headers=headers, verify=False, timeout=30,
        )
    except Exception as e:
        logger.warning("[Codex] Step B 异常: %s | email=%s", e, email)
        return None
    if resp.status_code != 200:
        logger.warning("[Codex] Step B 失败: HTTP %s | email=%s", resp.status_code, email)
        return None

    # Step C: 提交密码
    logger.info("[Codex] Step C: 提交密码 | email=%s", email)
    headers["referer"] = f"{oauth_issuer}/log-in/password"
    headers.update(generate_datadog_trace())

    sentinel_pwd = build_sentinel_token(session, device_id, flow="password_verify")
    if not sentinel_pwd:
        logger.warning("[Codex] Step C sentinel 失败 | email=%s", email)
        return None
    headers["openai-sentinel-token"] = sentinel_pwd

    try:
        resp = session.post(
            f"{oauth_issuer}/api/accounts/password/verify",
            json={"password": password},
            headers=headers, verify=False, timeout=30, allow_redirects=False,
        )
    except Exception as e:
        logger.warning("[Codex] Step C 异常: %s | email=%s", e, email)
        return None
    if resp.status_code != 200:
        logger.warning("[Codex] Step C 失败: HTTP %s | email=%s", resp.status_code, email)
        return None

    continue_url = None
    page_type = ""
    try:
        data = resp.json()
        continue_url = str(data.get("continue_url") or "")
        page_type = str(((data.get("page") or {}).get("type")) or "")
    except Exception:
        pass
    logger.info("[Codex] Step C 结果 | continue_url=%s | page_type=%s | email=%s", (continue_url or "")[:80], page_type, email)
    if not continue_url:
        logger.warning("[Codex] Step C 无 continue_url | email=%s", email)
        return None

    # Step D（可选）：若需要邮箱验证码
    if page_type == "email_otp_verification" or "email-verification" in continue_url:
        logger.info("[Codex] Step D: 需要OTP验证 | email=%s", email)
        if not cf_token:
            logger.warning("[Codex] 无 cf_token，跳过OTP | email=%s", email)
            return None

        baseline_mail_ids = snapshot_mail_identities(email, cf_token)
        mail_trigger_time = dt.datetime.now(MAIL_TIMEZONE)

        verification_url = continue_url if continue_url.startswith("http") else f"{oauth_issuer}{continue_url}"
        try:
            session.get(
                verification_url,
                headers=NAVIGATE_HEADERS,
                verify=False,
                timeout=20,
                allow_redirects=True,
            )
            logger.info("[Codex] 打开 email-verification 页面: %s | email=%s", verification_url[:80], email)
        except Exception as e:
            logger.warning("[Codex] 打开 email-verification 异常: %s | email=%s", e, email)

        h_val = build_auth_json_headers(
            referer=f"{oauth_issuer}/email-verification",
            device_id=device_id,
            include_device_id=False,
        )

        fallback_otp_sent = False
        last_attempted_identity = ""
        start_time = time.time()
        code = None
        while time.time() - start_time < 120:
            all_emails = fetch_emails_list(email, cf_token)
            latest_candidate = None

            for e_item in sort_mail_items_newest_first(all_emails):
                if not isinstance(e_item, dict):
                    continue
                mail_time = parse_mail_item_time(e_item)
                is_new_by_time = bool(mail_time and mail_time > mail_trigger_time)
                identity = build_mail_item_identity(e_item)
                if identity and identity in baseline_mail_ids and not is_new_by_time:
                    continue
                if mail_time and mail_time <= mail_trigger_time:
                    continue
                latest_candidate = e_item
                break

            if not latest_candidate:
                if not fallback_otp_sent and time.time() - start_time >= OTP_FALLBACK_SEND_DELAY_SECONDS:
                    try:
                        r_otp_send = session.get(
                            f"{oauth_issuer}/api/accounts/email-otp/send",
                            headers=h_val,
                            verify=False,
                            timeout=30,
                        )
                        logger.info("[Codex] OTP fallback send: HTTP %s | email=%s", r_otp_send.status_code, email)
                        fallback_otp_sent = True
                    except Exception as e:
                        logger.warning("[Codex] OTP fallback send 异常: %s | email=%s", e, email)
                time.sleep(2)
                continue

            candidate_identity = build_mail_item_identity(latest_candidate)
            if candidate_identity and candidate_identity == last_attempted_identity:
                time.sleep(2)
                continue

            try_code = extract_otp_from_mail_item(latest_candidate)
            if not try_code:
                time.sleep(2)
                continue

            last_attempted_identity = candidate_identity or f"code:{try_code}"
            resp_val = session.post(
                f"{oauth_issuer}/api/accounts/email-otp/validate",
                json={"code": try_code},
                headers=h_val,
                verify=False,
                timeout=30,
            )
            if resp_val.status_code == 200:
                code = try_code
                try:
                    d2 = resp_val.json()
                    continue_url = str(d2.get("continue_url") or continue_url)
                    page_type = str(((d2.get("page") or {}).get("type")) or "")
                    logger.info(
                        "[Codex] OTP验证返回 | continue_url=%s | page_type=%s | email=%s",
                        continue_url[:120],
                        page_type,
                        email,
                    )
                except Exception:
                    pass
                logger.info("[Codex] OTP验证成功: %s | email=%s", try_code, email)
            else:
                logger.warning("[Codex] OTP验证失败: HTTP %s | %s", resp_val.status_code, resp_val.text[:200])
                if resp_val.status_code == 400 and "max_check_attempts" in resp_val.text:
                    logger.warning("[Codex] OTP 验证次数已达上限，停止继续尝试 | email=%s", email)
                    return None

            if code:
                break
            time.sleep(2)
        if not code:
            return None

        auth_session_data = decode_auth_session_cookie(session)
        workspace_id = extract_workspace_id(auth_session_data)
        normalized_page_type = str(page_type or "").strip().lower()
        normalized_continue_url = str(continue_url or "").strip().lower()
        explicit_workspace = normalized_page_type == "workspace" or "/workspace" in normalized_continue_url
        about_you_stage = normalized_page_type in {"about_you", "about-you"} or "/about-you" in normalized_continue_url

        if (explicit_workspace or about_you_stage) and not workspace_id:
            auth_session_data, workspace_id = ensure_workspace_context(
                session=session,
                oauth_issuer=oauth_issuer,
                email=email,
                log_prefix="[Codex]",
            )

        if explicit_workspace or (workspace_id and about_you_stage):
            continue_url = f"{oauth_issuer}/workspace"
            page_type = "workspace"
            logger.info("[Codex] OTP后进入 workspace 阶段 | workspace_id=%s | email=%s", workspace_id or "", email)
            logger.info("[Codex] workspace 已就绪，等待 2s 再继续登录流程 | email=%s", email)
            time.sleep(2)
        elif about_you_stage:
            logger.info("[Codex] OTP后仍处于 about-you/onboarding 阶段 | email=%s", email)

        # 处理 about-you 页面（新注册账号可能需要填写资料）
        if "about-you" in continue_url and not workspace_id:
            h_about = dict(NAVIGATE_HEADERS)
            h_about["referer"] = f"{oauth_issuer}/email-verification"
            try:
                resp_about = session.get(
                    f"{oauth_issuer}/about-you",
                    headers=h_about, verify=False, timeout=30, allow_redirects=True,
                )
                logger.info(
                    "[Codex] about-you 页面加载: HTTP %s | url=%s | email=%s",
                    resp_about.status_code,
                    str(resp_about.url)[:120],
                    email,
                )
            except Exception:
                return None

            if "consent" in str(resp_about.url) or "organization" in str(resp_about.url):
                continue_url = str(resp_about.url)
            else:
                first_name, last_name = generate_random_name()
                birthdate = generate_random_birthday()
                h_create = dict(COMMON_HEADERS)
                h_create["referer"] = f"{oauth_issuer}/about-you"
                h_create["oai-device-id"] = device_id
                h_create.update(generate_datadog_trace())
                resp_create = session.post(
                    f"{oauth_issuer}/api/accounts/create_account",
                    json={"name": f"{first_name} {last_name}", "birthdate": birthdate},
                    headers=h_create, verify=False, timeout=30,
                )
                logger.info(
                    "[Codex] about-you create_account: HTTP %s | body=%s | email=%s",
                    resp_create.status_code,
                    resp_create.text[:200],
                    email,
                )
                if resp_create.status_code == 200:
                    try:
                        data = resp_create.json()
                        continue_url = str(data.get("continue_url") or "")
                    except Exception:
                        pass
                elif resp_create.status_code == 400 and "already_exists" in resp_create.text:
                    continue_url = f"{oauth_issuer}/sign-in-with-chatgpt/codex/consent"

                auth_session_data, workspace_id = ensure_workspace_context(
                    session=session,
                    oauth_issuer=oauth_issuer,
                    email=email,
                    log_prefix="[Codex]",
                    max_attempts=5,
                )
                if workspace_id:
                    continue_url = f"{oauth_issuer}/workspace"
                    page_type = "workspace"
                    logger.info("[Codex] about-you 后补拿到 workspace_id=%s | email=%s", workspace_id, email)

        # 处理 consent 页面类型
        if "consent" in page_type:
            continue_url = f"{oauth_issuer}/sign-in-with-chatgpt/codex/consent"

        if not continue_url or "email-verification" in continue_url:
            return None

    # Step E: 跟随 consent/workspace 重定向获取 auth code
    if continue_url.startswith("/"):
        consent_url = f"{oauth_issuer}{continue_url}"
    else:
        consent_url = continue_url

    auth_code = None

    # 主流：GET consent_url，如果是重定向就提取 code
    try:
        resp_consent = session.get(
            consent_url, headers=NAVIGATE_HEADERS,
            verify=False, timeout=30, allow_redirects=False,
        )
        if resp_consent.status_code in (301, 302, 303, 307, 308):
            loc = resp_consent.headers.get("Location", "")
            auth_code = _extract_code_from_url(loc)
            if not auth_code:
                auth_code = _follow_and_extract_code(session, loc, oauth_issuer)
        elif resp_consent.status_code == 200:
            # 需要 POST 同意
            # 提取页面中的 state/nonce 等隐藏字段
            html = resp_consent.text
            state_m = re.search(r'["\']state["\']:\s*["\']([^"\'\ ]+)["\']', html)
            nonce_m = re.search(r'["\']nonce["\']:\s*["\']([^"\'\ ]+)["\']', html)
            # POST 到同一 URL 表示应允 consent
            consent_payload = {"action": "allow"}
            if state_m:
                consent_payload["state"] = state_m.group(1)
            if nonce_m:
                consent_payload["nonce"] = nonce_m.group(1)
            consent_h = {
                "accept": "application/json, text/plain, */*",
                "content-type": "application/json",
                "origin": oauth_issuer,
                "referer": consent_url,
                "user-agent": USER_AGENT,
                "oai-device-id": device_id,
            }
            try:
                r_consent_post = session.post(
                    consent_url, json=consent_payload,
                    headers=consent_h, verify=False, timeout=30,
                    allow_redirects=False,
                )
                if r_consent_post.status_code in (301, 302, 303, 307, 308):
                    loc2 = r_consent_post.headers.get("Location", "")
                    auth_code = _extract_code_from_url(loc2)
                    if not auth_code:
                        consent_url = loc2 if loc2.startswith("http") else f"{oauth_issuer}{loc2}"
                elif r_consent_post.status_code == 200:
                    try:
                        cdata = r_consent_post.json()
                        redirect_to = str(cdata.get("redirectTo") or cdata.get("redirect_url") or "")
                        if redirect_to:
                            auth_code = _extract_code_from_url(redirect_to)
                            if not auth_code:
                                consent_url = redirect_to
                    except Exception:
                        pass
            except requests.exceptions.ConnectionError as e:
                m = re.search(r"(https?://localhost[^\s'\"&]+)", str(e))
                if m:
                    auth_code = _extract_code_from_url(m.group(1))
        else:
            # 可能是其他页面，尝试跟随重定向
            auth_code = _extract_code_from_url(str(resp_consent.url))
            if not auth_code:
                auth_code = _follow_and_extract_code(session, str(resp_consent.url), oauth_issuer)
    except requests.exceptions.ConnectionError as e:
        m = re.search(r"(https?://localhost[^\s'\"]+)", str(e))
        if m:
            auth_code = _extract_code_from_url(m.group(1))
    except Exception:
        pass

    # 如果普通重定向拿不到 code，尝试 workspace/select 流程
    if not auth_code:
        session_data = decode_auth_session_cookie(session)
        workspace_id = extract_workspace_id(session_data)
        if session_data:
            logger.info("[Codex] auth-session snapshots: %s | email=%s", summarize_auth_session_cookies(session), email)

        if workspace_id:
            h_ws = build_auth_json_headers(
                referer=consent_url,
                device_id=device_id,
            )
            try:
                resp_ws = session.post(
                    f"{oauth_issuer}/api/accounts/workspace/select",
                    json={"workspace_id": workspace_id},
                    headers=h_ws, verify=False, timeout=30, allow_redirects=False,
                )
                if resp_ws.status_code in (301, 302, 303, 307, 308):
                    loc = resp_ws.headers.get("Location", "")
                    auth_code = _extract_code_from_url(loc)
                    if not auth_code:
                        auth_code = _follow_and_extract_code(session, loc, oauth_issuer)
                elif resp_ws.status_code == 200:
                    ws_data = resp_ws.json()
                    ws_next = str(ws_data.get("continue_url") or "")
                    ws_page = str(((ws_data.get("page") or {}).get("type")) or "")

                    if "organization" in ws_next or "organization" in ws_page:
                        org_url = ws_next if ws_next.startswith("http") else f"{oauth_issuer}{ws_next}"
                        org_id = None
                        project_id = None
                        ws_orgs = (ws_data.get("data") or {}).get("orgs", []) if isinstance(ws_data, dict) else []
                        if ws_orgs:
                            org_id = (ws_orgs[0] or {}).get("id")
                            projects = (ws_orgs[0] or {}).get("projects", [])
                            if projects:
                                project_id = (projects[0] or {}).get("id")

                        if org_id:
                            body: Dict[str, str] = {"org_id": org_id}
                            if project_id:
                                body["project_id"] = project_id
                            h_org = build_auth_json_headers(
                                referer=org_url,
                                device_id=device_id,
                            )
                            resp_org = session.post(
                                f"{oauth_issuer}/api/accounts/organization/select",
                                json=body, headers=h_org, verify=False,
                                timeout=30, allow_redirects=False,
                            )
                            if resp_org.status_code in (301, 302, 303, 307, 308):
                                loc = resp_org.headers.get("Location", "")
                                auth_code = _extract_code_from_url(loc)
                                if not auth_code:
                                    auth_code = _follow_and_extract_code(session, loc, oauth_issuer)
                            elif resp_org.status_code == 200:
                                org_data = resp_org.json()
                                org_next = str(org_data.get("continue_url") or "")
                                if org_next:
                                    full_next = org_next if org_next.startswith("http") else f"{oauth_issuer}{org_next}"
                                    auth_code = _follow_and_extract_code(session, full_next, oauth_issuer)
                        else:
                            auth_code = _follow_and_extract_code(session, org_url, oauth_issuer)
                    else:
                        if ws_next:
                            full_next = ws_next if ws_next.startswith("http") else f"{oauth_issuer}{ws_next}"
                            auth_code = _follow_and_extract_code(session, full_next, oauth_issuer)
            except Exception:
                pass
        else:
            logger.info("[Codex] workspace/select 跳过：未从 auth-session 中提取到 workspace_id | email=%s", email)

    # 最终 fallback: 带重定向再跟一次
    if not auth_code:
        try:
            resp_fallback = session.get(
                consent_url, headers=NAVIGATE_HEADERS,
                verify=False, timeout=30, allow_redirects=True,
            )
            auth_code = _extract_code_from_url(str(resp_fallback.url))
            if not auth_code and resp_fallback.history:
                for hist in resp_fallback.history:
                    loc = hist.headers.get("Location", "")
                    auth_code = _extract_code_from_url(loc)
                    if auth_code:
                        break
        except requests.exceptions.ConnectionError as e:
            m = re.search(r"(https?://localhost[^\s'\"]+)", str(e))
            if m:
                auth_code = _extract_code_from_url(m.group(1))
        except Exception:
            pass

    if not auth_code:
        logger.warning("[Codex登录] 未能获取 auth_code | email=%s", email)
        return None

    # Step F: 用 code 换取 token
    return _exchange_code_for_token(
        auth_code, code_verifier,
        oauth_issuer=oauth_issuer,
        oauth_client_id=oauth_client_id,
        oauth_redirect_uri=oauth_redirect_uri,
        proxy=proxy,
    )


def _exchange_code_for_token(
    code: str,
    code_verifier: str,
    oauth_issuer: str = OPENAI_AUTH_BASE,
    oauth_client_id: str = OAUTH_CLIENT_ID,
    oauth_redirect_uri: str = OAUTH_REDIRECT_URI,
    proxy: str = "",
) -> Optional[Dict[str, Any]]:
    """用 authorization_code 换取 access_token/refresh_token"""
    session = create_session(proxy=proxy)
    try:
        resp = session.post(
            f"{oauth_issuer}/oauth/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": oauth_redirect_uri,
                "client_id": oauth_client_id,
                "code_verifier": code_verifier,
            },
            verify=False,
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, dict) else None
        logger.warning("token 交换失败: HTTP %s | %s", resp.status_code, resp.text[:200])
        return None
    except Exception as e:
        logger.warning("token 交换异常: %s", e)
        return None


# ============================================================
# ⑫ JWT 解码（不验签）
# ============================================================

def decode_jwt_payload(token: str) -> Dict[str, Any]:
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


# ============================================================
# ⑬ Sub2Api 上传
# ============================================================

def _push_account_to_sub2api(email: str, tokens: Dict[str, Any]) -> bool:
    """共享 Sub2Api 上传入口。AI by zb"""
    return _sub2api_uploader.push_account(email, tokens)


def build_token_dict(email: str, tokens: Dict[str, Any]) -> Dict[str, Any]:
    """构造标准 token JSON（与 gptzidong 格式兼容）"""
    access_token = str(tokens.get("access_token") or "")
    refresh_token = str(tokens.get("refresh_token") or "")
    id_token = str(tokens.get("id_token") or "")

    payload = decode_jwt_payload(access_token)
    auth_info = payload.get("https://api.openai.com/auth", {})
    account_id = auth_info.get("chatgpt_account_id", "") if isinstance(auth_info, dict) else ""

    exp_timestamp = payload.get("exp", 0)
    now = dt.datetime.now(tz=dt.timezone(dt.timedelta(hours=8)))
    expired_str = ""
    if exp_timestamp:
        exp_dt = dt.datetime.fromtimestamp(exp_timestamp, tz=dt.timezone(dt.timedelta(hours=8)))
        expired_str = exp_dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")

    return {
        "type": "codex",
        "email": email,
        "expired": expired_str,
        "id_token": id_token,
        "account_id": account_id,
        "access_token": access_token,
        "last_refresh": now.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "refresh_token": refresh_token,
    }


_team_session_lock = threading.Lock()


def load_team_session_cache() -> Dict[str, Dict[str, Any]]:
    """读取母号登录态缓存。AI by zb"""
    if not os.path.exists(TEAM_SESSION_CACHE_FILE):
        return {}
    try:
        with open(TEAM_SESSION_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.warning("读取母号登录态缓存失败: %s", e)
    return {}


def save_team_session_cache(cache: Dict[str, Dict[str, Any]]) -> None:
    """保存母号登录态缓存。AI by zb"""
    try:
        with open(TEAM_SESSION_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("保存母号登录态缓存失败: %s", e)


def restore_team_session_state(team: Dict[str, Any]) -> bool:
    """从本地缓存恢复母号登录态。AI by zb"""
    team_email = str(team.get("email") or "").strip()
    if not team_email:
        return False

    with _team_session_lock:
        cache = load_team_session_cache()

    cached = cache.get(team_email)
    if not isinstance(cached, dict):
        return False

    auth_token = str(cached.get("auth_token") or "").strip()
    account_id = str(cached.get("account_id") or "").strip()
    if not auth_token or not account_id:
        return False

    team["auth_token"] = auth_token
    team["account_id"] = account_id
    if cached.get("session_updated_at"):
        team["session_updated_at"] = str(cached.get("session_updated_at"))

    logger.info(
        "复用本地母号登录态 | team=%s | email=%s | updated_at=%s",
        team.get("name", team_email),
        team_email,
        cached.get("session_updated_at", ""),
    )
    return True


def persist_team_session_state(team: Dict[str, Any]) -> None:
    """持久化当前母号登录态，便于下次复用。AI by zb"""
    team_email = str(team.get("email") or "").strip()
    auth_token = str(team.get("auth_token") or "").strip()
    account_id = str(team.get("account_id") or "").strip()
    if not team_email or not auth_token or not account_id:
        return

    session_updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "name": str(team.get("name") or ""),
        "email": team_email,
        "auth_token": auth_token,
        "account_id": account_id,
        "session_updated_at": session_updated_at,
    }

    with _team_session_lock:
        cache = load_team_session_cache()
        cache[team_email] = payload
        save_team_session_cache(cache)

    team["session_updated_at"] = session_updated_at


def prompt_for_email_otp(email: str, tag: str = "", timeout: int = 300) -> Optional[str]:
    """等待手动输入母号邮箱验证码。AI by zb"""
    prompt_tag = tag or email
    deadline = time.time() + max(timeout, 30)

    while time.time() < deadline:
        remain = max(1, int(deadline - time.time()))
        try:
            raw = input(
                f"\n[{prompt_tag}] 已向 {email} 发送邮箱验证码，请输入 6 位 code "
                f"(剩余 {remain}s，直接回车取消): "
            ).strip()
        except EOFError:
            logger.warning("  [%s] 当前环境无法读取手动输入 | email=%s", prompt_tag, email)
            return None

        if not raw:
            logger.warning("  [%s] 未输入验证码，已取消本次母号登录 | email=%s", prompt_tag, email)
            return None

        code = _extract_otp_from_raw(raw)
        if code:
            return code

        logger.warning("  [%s] 输入内容未识别到 6 位验证码，请重试", prompt_tag)

    logger.warning("  [%s] 等待手动输入 OTP 超时 | email=%s", prompt_tag, email)
    return None


def extract_workspace_id(payload: Any) -> Optional[str]:
    """从多种返回结构中提取 workspace_id。AI by zb"""
    if payload is None:
        return None

    if isinstance(payload, str):
        text = payload.strip()
        return text or None

    if isinstance(payload, list):
        for item in payload:
            found = extract_workspace_id(item)
            if found:
                return found
        return None

    if not isinstance(payload, dict):
        return None

    direct_workspace_id = str(payload.get("workspace_id") or "").strip()
    if direct_workspace_id:
        return direct_workspace_id

    workspaces = payload.get("workspaces")
    if isinstance(workspaces, list):
        # 团队邀请场景优先选 organization workspace，其次再回退 personal。
        preferred_items = [item for item in workspaces if isinstance(item, dict) and str(item.get("kind") or "").strip() == "organization"]
        fallback_items = [item for item in workspaces if isinstance(item, dict)]
        for item in preferred_items + fallback_items:
            ws_id = str(item.get("id") or item.get("workspace_id") or "").strip()
            if ws_id:
                return ws_id

    workspace = payload.get("workspace")
    if isinstance(workspace, dict):
        ws_id = str(workspace.get("id") or workspace.get("workspace_id") or "").strip()
        if ws_id:
            return ws_id

    for key in ("data", "items", "results", "value"):
        nested = payload.get(key)
        found = extract_workspace_id(nested)
        if found:
            return found

    direct_id = str(payload.get("id") or "").strip()
    if direct_id and any(k in payload for k in ("name", "slug", "projects")):
        return direct_id

    return None


def _decode_auth_session_cookie_value(cookie_value: str) -> Optional[Dict[str, Any]]:
    """解析单个 oai-client-auth-session 的 cookie value。AI by zb"""
    part = cookie_value.split(".")[0] if "." in cookie_value else cookie_value
    pad = 4 - len(part) % 4
    try:
        raw = base64.urlsafe_b64decode(part + ("=" * (pad if pad != 4 else 0)))
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def decode_auth_session_cookie(session: requests.Session) -> Optional[Dict[str, Any]]:
    """解析 oai-client-auth-session Cookie。AI by zb"""
    fallback_data: Optional[Dict[str, Any]] = None
    for cookie in session.cookies:
        if cookie.name != "oai-client-auth-session":
            continue
        data = _decode_auth_session_cookie_value(cookie.value)
        if isinstance(data, dict):
            if extract_workspace_id(data):
                return data
            if fallback_data is None:
                fallback_data = data
    return fallback_data


def summarize_auth_session_cookies(session: requests.Session) -> List[Dict[str, Any]]:
    """汇总当前所有 oai-client-auth-session cookie 状态。AI by zb"""
    summaries: List[Dict[str, Any]] = []
    for cookie in session.cookies:
        if cookie.name != "oai-client-auth-session":
            continue
        data = _decode_auth_session_cookie_value(cookie.value) or {}
        workspaces = data.get("workspaces") if isinstance(data, dict) else None
        workspace_items = workspaces if isinstance(workspaces, list) else []
        summaries.append({
            "domain": getattr(cookie, "domain", ""),
            "path": getattr(cookie, "path", ""),
            "session_id": str(data.get("session_id") or ""),
            "original_screen_hint": str(data.get("original_screen_hint") or ""),
            "email_verification_mode": str(data.get("email_verification_mode") or ""),
            "workspace_count": len(workspace_items),
            "workspace_kinds": [str((item or {}).get("kind") or "") for item in workspace_items if isinstance(item, dict)],
            "has_workspace_id": bool(extract_workspace_id(data)),
        })
    return summaries


def is_workspace_stage(page_type: str, continue_url: str) -> bool:
    """判断当前是否已经进入 workspace 选择阶段。AI by zb"""
    normalized_page_type = str(page_type or "").strip().lower()
    normalized_continue_url = str(continue_url or "").strip().lower()
    return (
        normalized_page_type in {"workspace", "about_you", "about-you"}
        or "/workspace" in normalized_continue_url
        or "/about-you" in normalized_continue_url
    )


def ensure_workspace_context(
    session: requests.Session,
    oauth_issuer: str,
    email: str,
    log_prefix: str,
    max_attempts: int = 3,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """主动加载 workspace 页面并轮询等待 workspace_id 出现。AI by zb"""
    workspace_url = f"{oauth_issuer}/workspace"
    session_data: Optional[Dict[str, Any]] = None
    workspace_id: Optional[str] = None

    for attempt in range(1, max_attempts + 1):
        try:
            resp = session.get(
                workspace_url,
                headers=NAVIGATE_HEADERS,
                verify=False,
                timeout=20,
                allow_redirects=True,
            )
            logger.info(
                "%s workspace 页面加载: HTTP %s | url=%s | attempt=%d | email=%s",
                log_prefix,
                resp.status_code,
                str(resp.url)[:100],
                attempt,
                email,
            )
        except Exception as e:
            logger.warning("%s workspace 页面加载异常: %s | email=%s", log_prefix, e, email)

        session_data = decode_auth_session_cookie(session)
        workspace_id = extract_workspace_id(session_data)
        logger.info("%s workspace snapshots: %s | email=%s", log_prefix, summarize_auth_session_cookies(session), email)
        if workspace_id:
            return session_data, workspace_id
        if attempt < max_attempts:
            time.sleep(1)

    return session_data, workspace_id



# ============================================================
# ⑭ 母号 Session 自动拉取（chatgpt.com 专用 HTTP 登录）
# ============================================================
# chatgpt.com 使用 NextAuth 体系，与 Codex OAuth 完全不同：
#   1. 访问 chatgpt.com/auth/login → 跳转 auth.openai.com 获取 login_session
#   2. 提交邮箱（authorize/continue）
#   3. 提交密码（password/verify）或 OTP
#   4. consent redirect → chatgpt.com/api/auth/callback/openai
#   5. 调用 /api/auth/session 获取 accessToken + organizationId

CHATGPT_BASE = "https://chatgpt.com"
CHATGPT_AUTH_CALLBACK = "https://chatgpt.com/api/auth/callback/openai"
CHATGPT_OAUTH_CLIENT_ID = "pdlLIX2Y72MIl2rhLhTE9VV9bN905kBh"
CHATGPT_OAUTH_REDIRECT_URI = "https://chatgpt.com/api/auth/callback/openai"


def chatgpt_http_login(
    email: str,
    password: str = "",
    cf_token: str = "",
    proxy: str = "",
    tag: str = "",         # 日志前缀：显示车头名称（如 "1" / "2"）
) -> Tuple[str, str]:
    """
    chatgpt.com 专用 HTTP 登录（NextAuth 体系）。
    返回 (access_token, org_id)，失败返回 ("", "")

    流程：
      A. GET chatgpt.com 首页 → POST chatgpt.com/api/auth/signin/openai（CSRF）
         → 跟随重定向到 auth.openai.com/oauth/authorize
         → auth.openai.com 设置 login_session Cookie
      B. 提交邮箱（authorize/continue），origin=auth.openai.com
      C. 提交密码 or 触发 OTP
      D. OTP 验证（可选）
      E. 跟随 consent 重定向到 chatgpt.com
      F. 读取 /api/auth/session
    """
    session = create_session(proxy=proxy)
    device_id = str(uuid.uuid4())
    tag = tag or email   # 日志前缀：优先用车头名称，否则用邮箱

    session.cookies.set("oai-did", device_id, domain=".chatgpt.com")
    session.cookies.set("oai-did", device_id, domain="chatgpt.com")
    session.cookies.set("oai-did", device_id, domain=".auth.openai.com")

    # ── Step A: NextAuth CSRF + OAuth authorize ──
    logger.info(f"  [{tag}] 获取 NextAuth CSRF token | email=%s", email)
    try:
        # 1. 访问首页建立 chatgpt.com session
        session.get(
            CHATGPT_BASE,
            headers=NAVIGATE_HEADERS,
            allow_redirects=True,
            verify=False,
            timeout=20,
        )
    except Exception:
        pass

    # 2. 获取 NextAuth CSRF token
    csrf_token = ""
    try:
        resp_csrf = session.get(
            f"{CHATGPT_BASE}/api/auth/csrf",
            headers={
                "accept": "application/json",
                "referer": f"{CHATGPT_BASE}/",
                "user-agent": USER_AGENT,
                "x-requested-with": "XMLHttpRequest",
            },
            verify=False,
            timeout=15,
        )
        if resp_csrf.status_code == 200:
            csrf_token = str(resp_csrf.json().get("csrfToken") or "")
            logger.info(f"  [{tag}] CSRF token 获取成功: %s...", csrf_token[:8])
    except Exception as e:
        logger.warning(f"  [{tag}] CSRF 获取失败: %s（继续尝试）", e)

    # 3. POST signin/openai 触发 OAuth 重定向（携带 CSRF）
    try:
        signin_headers = {
            "accept": "application/json",
            "content-type": "application/x-www-form-urlencoded",
            "origin": CHATGPT_BASE,
            "referer": f"{CHATGPT_BASE}/auth/login",
            "user-agent": USER_AGENT,
        }
        signin_data: Dict[str, str] = {"callbackUrl": CHATGPT_BASE}
        if csrf_token:
            signin_data["csrfToken"] = csrf_token
        resp_signin = session.post(
            f"{CHATGPT_BASE}/api/auth/signin/openai",
            data=signin_data,
            headers=signin_headers,
            allow_redirects=True,
            verify=False,
            timeout=30,
        )
        logger.info(f"  [{tag}] signin/openai %s → %s",
                    resp_signin.status_code, str(resp_signin.url)[:60])
    except Exception as e:
        logger.warning(f"  [{tag}] signin/openai 异常: %s（继续）", e)

    # 4. 确认已到 auth.openai.com 并有 login_session Cookie
    has_login_session = any(c.name == "login_session" for c in session.cookies)
    logger.info(f"  [{tag}] login_session Cookie: %s", "✅ 存在" if has_login_session else "❌ 未获取")

    if not has_login_session:
        # fallback：直接构建 authorize URL 访问
        logger.info(f"  [{tag}] 尝试直接访问 authorize URL...")
        try:
            code_verifier_fb, code_challenge_fb = generate_pkce()
            auth_params_fb = {
                "response_type": "code",
                "client_id": CHATGPT_OAUTH_CLIENT_ID,
                "redirect_uri": CHATGPT_OAUTH_REDIRECT_URI,
                "scope": "openid profile email offline_access",
                "code_challenge": code_challenge_fb,
                "code_challenge_method": "S256",
                "state": secrets.token_urlsafe(32),
            }
            auth_url_fb = f"{OPENAI_AUTH_BASE}/oauth/authorize?{urlencode(auth_params_fb)}"
            session.get(
                auth_url_fb,
                headers=NAVIGATE_HEADERS,
                allow_redirects=True, verify=False, timeout=30,
            )
            has_login_session = any(c.name == "login_session" for c in session.cookies)
            if has_login_session:
                logger.info(f"  [{tag}] fallback 成功获取 login_session ✅")
        except Exception as e:
            logger.warning(f"  [{tag}] fallback 失败: %s", e)

    if not has_login_session:
        logger.warning(f"  [{tag}] 无法获取 login_session Cookie，可能被风控 | email=%s", email)
        return "", ""

    # ── Step B: 提交邮箱（origin 必须是 auth.openai.com）──
    logger.info(f"  [{tag}] 提交邮箱 | email=%s", email)
    h_b = build_auth_json_headers(
        referer=f"{OPENAI_AUTH_BASE}/log-in",
        device_id=device_id,
    )
    sentinel_b = build_sentinel_token(session, device_id, flow="authorize_continue")
    if sentinel_b:
        h_b["openai-sentinel-token"] = sentinel_b
    try:
        resp_b = session.post(
            f"{OPENAI_AUTH_BASE}/api/accounts/authorize/continue",
            json={"username": {"kind": "email", "value": email}},
            headers=h_b, verify=False, timeout=30,
        )
        if resp_b.status_code != 200:
            logger.warning(f"  [{tag}] 失败: HTTP %s | %s",
                           resp_b.status_code, resp_b.text[:200])
            return "", ""
        # 解析 Step B 返回的 continue_url 并 GET 跟随（推进状态机）
        try:
            b_data = resp_b.json()
            b_continue = str(b_data.get("continue_url") or "")
            b_page_type = str(((b_data.get("page") or {}).get("type")) or "")
        except Exception:
            b_continue = ""
            b_page_type = ""
        # 判断走哪个分支：OTP / 密码 / 第三方 SSO
        lower_continue = b_continue.lower()
        if "email-verification" in lower_continue or b_page_type == "email_otp_verification":
            next_step = "otp"
        elif "accounts.google.com" in lower_continue or "appleid.apple.com" in lower_continue:
            next_step = "sso"
        else:
            next_step = "password"
        logger.info(f"  [{tag}] 登录方式: %s | continue_url=%s",
                    next_step, b_continue[:50])
        if b_continue:
            if b_continue.startswith("/"):
                b_continue_full = f"{OPENAI_AUTH_BASE}{b_continue}"
            else:
                b_continue_full = b_continue
            try:
                session.get(
                    b_continue_full,
                    headers=NAVIGATE_HEADERS,
                    allow_redirects=True,
                    verify=False,
                    timeout=15,
                )
                logger.info(f"  [{tag}] 跟随 continue_url → %s", b_continue_full[:60])
            except Exception:
                pass
        logger.info(f"  [{tag}] ✅ 邮箱提交 + 页面跳转完成")
        logger.info(f"  [{tag}] auth-session snapshots after email: %s", summarize_auth_session_cookies(session))
    except Exception as e:
        logger.warning(f"  [{tag}] 异常: %s", e)
        return "", ""

    continue_url = b_continue if b_continue else ""
    page_type = b_page_type if b_page_type else ""

    # ── Step C: 密码 OR OTP（根据 Step B 实际跳转目标决定）──
    if next_step == "password" and password:
        logger.info(f"  [{tag}] 提交密码 | email=%s", email)
        h2 = build_auth_json_headers(
            referer=f"{OPENAI_AUTH_BASE}/log-in/password",
            device_id=device_id,
        )
        sentinel2 = build_sentinel_token(session, device_id, flow="password_verify")
        if sentinel2:
            h2["openai-sentinel-token"] = sentinel2
        try:
            resp_c = session.post(
                f"{OPENAI_AUTH_BASE}/api/accounts/password/verify",
                json={"password": password},
                headers=h2, verify=False, timeout=30, allow_redirects=False,
            )
            if resp_c.status_code != 200:
                logger.warning(f"  [{tag}] 密码失败: HTTP %s | %s", resp_c.status_code, resp_c.text[:200])
                return "", ""
            data_c = resp_c.json()
            continue_url = str(data_c.get("continue_url") or "")
            page_type = str(((data_c.get("page") or {}).get("type")) or "")
            logger.info(f"  [{tag}] ✅ 密码验证成功")
        except Exception as e:
            logger.warning(f"  [{tag}] 密码异常: %s", e)
            return "", ""
    elif next_step == "otp" or (next_step == "password" and not password):
        # 无密码 OR 服务端要求OTP：触发邮箱 OTP
        if next_step == "otp" and password:
            logger.info(f"  [{tag}] 账号要求OTP登录（忽略密码）| email=%s", email)
        if next_step == "password" and not password:
            logger.warning(f"  [{tag}] 当前流程需要密码登录，但未配置母号密码 | email=%s", email)
            return "", ""
        logger.info(f"  [{tag}] OTP模式：依赖 email-verification 页面触发验证码邮件 | email=%s", email)
        page_type = "email_otp_verification"
        continue_url = f"{OPENAI_AUTH_BASE}/email-verification"

    # ── Step D（可选）：邮箱 OTP 验证 ──
    if page_type == "email_otp_verification" or "email-verification" in continue_url:
        if cf_token:
            logger.info(f"  [{tag}] OTP 已发送，自动轮询邮箱验证码 | email=%s", email)
        else:
            logger.info(f"  [{tag}] OTP 已发送，等待手动输入验证码 | email=%s", email)
        h_v = build_auth_json_headers(
            referer=f"{OPENAI_AUTH_BASE}/email-verification",
            device_id=device_id,
            include_device_id=False,
        )
        got_code = False
        if cf_token:
            verify_deadline = time.time() + 180
            tried_codes: set = set()
            baseline_mail_ids = snapshot_mail_identities(email, cf_token)
            mail_trigger_time = dt.datetime.now(MAIL_TIMEZONE)
            while time.time() < verify_deadline:
                all_emails = fetch_emails_list(email, cf_token)
                all_codes = []
                for item in sort_mail_items_newest_first(all_emails):
                    if not isinstance(item, dict):
                        continue
                    mail_time = parse_mail_item_time(item)
                    is_new_by_time = bool(mail_time and mail_time > mail_trigger_time)
                    identity = build_mail_item_identity(item)
                    if identity and identity in baseline_mail_ids and not is_new_by_time:
                        continue
                    if mail_time and mail_time <= mail_trigger_time:
                        continue
                    c = extract_otp_from_mail_item(item)
                    if c and c not in tried_codes:
                        all_codes.append(c)

                for otp_code in all_codes:
                    tried_codes.add(otp_code)
                    rv = session.post(
                        f"{OPENAI_AUTH_BASE}/api/accounts/email-otp/validate",
                        json={"code": otp_code},
                        headers=h_v,
                        verify=False,
                        timeout=30,
                    )
                    if rv.status_code == 200:
                        try:
                            d2 = rv.json()
                            continue_url = str(d2.get("continue_url") or continue_url)
                            page_type = str(((d2.get("page") or {}).get("type")) or "")
                        except Exception:
                            pass
                        got_code = True
                        logger.info(f"  [{tag}] OTP验证成功: %s", otp_code)
                        logger.info(f"  [{tag}] auth-session snapshots after otp: %s", summarize_auth_session_cookies(session))
                        break
                    logger.warning(f"  [{tag}] OTP验证失败: HTTP %s | %s", rv.status_code, rv.text[:200])
                if got_code:
                    break
                time.sleep(2)
        else:
            verify_deadline = time.time() + 300
            while time.time() < verify_deadline:
                otp_code = prompt_for_email_otp(
                    email=email,
                    tag=tag,
                    timeout=max(30, int(verify_deadline - time.time())),
                )
                if not otp_code:
                    return "", ""

                rv = session.post(
                    f"{OPENAI_AUTH_BASE}/api/accounts/email-otp/validate",
                    json={"code": otp_code}, headers=h_v, verify=False, timeout=30,
                )
                if rv.status_code == 200:
                    try:
                        d2 = rv.json()
                        continue_url = str(d2.get("continue_url") or continue_url)
                        page_type = str(((d2.get("page") or {}).get("type")) or "")
                    except Exception:
                        pass
                    got_code = True
                    logger.info(f"  [{tag}] OTP验证成功: %s", otp_code)
                    logger.info(f"  [{tag}] auth-session snapshots after otp: %s", summarize_auth_session_cookies(session))
                    break
                logger.warning(f"  [{tag}] OTP验证失败: HTTP %s | %s", rv.status_code, rv.text[:200])
        if not got_code:
            logger.warning(f"  [{tag}] OTP超时 | email=%s", email)
            return "", ""
    else:
        logger.warning(f"  [{tag}] 当前母号走第三方 SSO 流程，暂不支持自动登录 | continue_url=%s | email=%s", b_continue[:120], email)
        return "", ""

    auth_session_data = decode_auth_session_cookie(session)
    workspace_id = extract_workspace_id(auth_session_data)
    if is_workspace_stage(page_type, continue_url):
        continue_url = f"{OPENAI_AUTH_BASE}/workspace"
        page_type = "workspace"
        if workspace_id:
            logger.info(
                f"  [{tag}] 检测到 workspace 阶段，优先进入 /workspace | workspace_id=%s",
                workspace_id,
            )
        else:
            logger.info(f"  [{tag}] 检测到 workspace 阶段，优先进入 /workspace")

    # ── Step E: 跟随 consent 重定向 → chatgpt.com session ──
    if not continue_url:
        logger.warning(f"  [{tag}] 无 continue_url | email=%s", email)
        return "", ""

    if continue_url.startswith("/"):
        consent_url = f"{OPENAI_AUTH_BASE}{continue_url}"
    else:
        consent_url = continue_url

    logger.info(f"  [{tag}] 跟随 continue_url | url=%s | page_type=%s", consent_url[:80], page_type)
    final_url = ""
    try:
        # 跟随重定向一直到 chatgpt.com，让 NextAuth callback 建立 session
        resp_e = session.get(
            consent_url,
            headers=NAVIGATE_HEADERS,
            allow_redirects=True,
            verify=False,
            timeout=30,
        )
        final_url = str(resp_e.url)
        logger.info(f"  [{tag}] 最终落地: %s", final_url[:80])
    except Exception as e:
        logger.warning(f"  [{tag}] 重定向异常: %s", e)
        pass

    # 如果落地不在 chatgpt.com，需要做 workspace/select 来获取 chatgpt.com callback redirect
    if "chatgpt.com" not in final_url:
        logger.info(f"  [{tag}] 落地非 chatgpt.com，执行 workspace/select 流程...")
        try:
            # 解析 oai-client-auth-session cookie 获取 workspace 信息
            ws_id = None
            auth_session_data = decode_auth_session_cookie(session)
            if auth_session_data:
                logger.info(
                    f"  [{tag}] auth-session keys=%s | workspaces_type=%s | workspaces_preview=%s",
                    list(auth_session_data.keys())[:20],
                    type(auth_session_data.get('workspaces')).__name__,
                    str(auth_session_data.get('workspaces')),
                )
                ws_id = extract_workspace_id(auth_session_data)

            # POST /api/accounts/workspace/select
            if not ws_id:
                logger.warning(f"  [{tag}] 未找到 workspace_id，无法继续 workspace/select | email=%s", email)
            ws_body = {"workspace_id": ws_id} if ws_id else {}
            logger.info(f"  [{tag}] POST workspace/select | body=%s", ws_body)
            if ws_id:
                r_ws_sel = session.post(
                    f"{OPENAI_AUTH_BASE}/api/accounts/workspace/select",
                    json=ws_body,
                    headers=build_auth_json_headers(
                        referer=f"{OPENAI_AUTH_BASE}/workspace",
                        device_id=device_id,
                    ),
                    allow_redirects=False, verify=False, timeout=30)
                logger.info(f"  [{tag}] workspace/select: HTTP %s | Location=%s | body=%s",
                            r_ws_sel.status_code,
                            r_ws_sel.headers.get("Location", "")[:80],
                            r_ws_sel.text[:200])

                # 跟随 continue_url 或 Location redirect
                ws_next = ""
                try:
                    ws_data = r_ws_sel.json()
                    ws_next = str(ws_data.get("continue_url") or "")
                except Exception:
                    pass
                loc = r_ws_sel.headers.get("Location", "")
                ws_next = ws_next or loc

                if ws_next:
                    if not ws_next.startswith("http"):
                        ws_next = f"{OPENAI_AUTH_BASE}{ws_next}"
                    logger.info(f"  [{tag}] 跟随 ws_next: %s", ws_next[:80])
                    r_ws_redir = session.get(
                        ws_next, headers={"user-agent": USER_AGENT},
                        allow_redirects=True, verify=False, timeout=30)
                    logger.info(f"  [{tag}] ws_next 落地: %s", str(r_ws_redir.url)[:80])
        except Exception as e:
            logger.warning(f"  [{tag}] workspace/select 异常: %s", e)



    # ── Step F: 读取 chatgpt.com session ──
    logger.info(f"  [{tag}] 读取 /api/auth/session | email=%s", email)
    try:
        resp_s = session.get(
            f"{CHATGPT_BASE}/api/auth/session",
            headers={
                "accept": "application/json",
                "referer": f"{CHATGPT_BASE}/",
                "user-agent": USER_AGENT,
            },
            verify=False,
            timeout=20,
        )
        if resp_s.status_code == 200:
            sdata = resp_s.json()
            access_token = str(sdata.get("accessToken") or "")
            acct = sdata.get("account") or {}
            # account.id 是 UUID（邀请 API 路径使用），organizationId 是 org-xxx（Header 使用）
            acct_uuid = str(acct.get("id") or "")
            org_id = str(acct.get("organizationId") or "")
            # 优先用 UUID，其次用 org_id
            primary_id = acct_uuid or org_id
            if access_token and primary_id:
                logger.info(f"  [{tag}] ✅ 获取成功 | uuid=%s | org_id=%s", acct_uuid, org_id)
                # 返回 (access_token, account_uuid) 给 refresh_team_session_http 存储
                return access_token, acct_uuid or org_id
            elif access_token:
                # org_id 从 JWT 中解析
                payload = decode_jwt_payload(access_token)
                auth_info = payload.get("https://api.openai.com/auth", {})
                if isinstance(auth_info, dict):
                    org_id = str(auth_info.get("organization_id") or auth_info.get("chatgpt_account_id") or "")
                if org_id:
                    logger.info(f"  [{tag}] ✅ 从 JWT 获取 org_id=%s", org_id)
                    return access_token, org_id
            logger.warning(f"  [{tag}] session 不完整: %s", str(sdata)[:200])
        else:
            logger.warning(f"  [{tag}] session HTTP %s | %s", resp_s.status_code, resp_s.text[:150])
    except Exception as e:
        logger.warning(f"  [{tag}] session 异常: %s", e)

    return "", ""


def refresh_team_session_http(team):
    """
    通过纯 HTTP OAuth 登录母号（chatgpt.com OAuth），
    获取 account_id 和 auth_token 并写回 team 字典。
    - 有 password：走密码登录流程
    - 无 password：直接走邮箱 OTP 登录流程（发送后手动输入邮箱验证码）
    """
    m_email = team.get("email", "")
    m_password = team.get("password", "")  # 可为空，无密码时走 OTP
    if not m_email:
        logger.error("母号未配置 email，无法登录")
        return False

    mode_str = "密码登录" if m_password else "无密码OTP登录"
    logger.info("🔄 HTTP 刷新母号 session [%s]: %s", mode_str, m_email)


    # 使用 chatgpt.com 专用登录函数
    access_token, org_id = chatgpt_http_login(
        email=m_email,
        password=m_password,
        tag=team.get("name", m_email),
    )

    if access_token and org_id:
        team["auth_token"] = f"Bearer {access_token}"
        team["account_id"] = org_id
        persist_team_session_state(team)
        logger.info("✅ 母号 token 刷新成功 | account_id=%s | email=%s", org_id, m_email)
        return True

    logger.warning("母号 session 获取失败 | email=%s", m_email)
    return False


# ============================================================
# ⑮ 团队邀请管理
# ============================================================

_tracker_lock = threading.Lock()


def load_invite_tracker():
    if os.path.exists(INVITE_TRACKER_FILE):
        try:
            with open(INVITE_TRACKER_FILE, "r", encoding="utf-8") as f:
                tracker = json.load(f)
                if isinstance(tracker, dict):
                    teams = tracker.get("teams") or {}
                    normalized = {"teams": {}}
                    for team in TEAMS:
                        normalized["teams"][team["email"]] = []
                    for team_key, entries in teams.items():
                        normalized_entries = []
                        if isinstance(entries, list):
                            for item in entries:
                                if isinstance(item, str):
                                    normalized_entries.append({"email": item, "status": "sent"})
                                elif isinstance(item, dict):
                                    entry_email = str(item.get("email") or "").strip()
                                    if entry_email:
                                        normalized_entries.append({
                                            "email": entry_email,
                                            "status": str(item.get("status") or "sent"),
                                        })
                        normalized["teams"][team_key] = normalized_entries
                    return normalized
        except Exception as e:
            logger.warning("读取 invite tracker 失败: %s", e)
    return {"teams": {team["email"]: [] for team in TEAMS}}


def save_invite_tracker(tracker):
    try:
        with open(INVITE_TRACKER_FILE, "w", encoding="utf-8") as f:
            json.dump(tracker, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("保存 invite tracker 失败: %s", e)


def _find_tracker_entry(entries, email: str) -> Optional[Dict[str, Any]]:
    """按邮箱查找邀请跟踪项。AI by zb"""
    target = str(email or "").strip().lower()
    for item in entries or []:
        if isinstance(item, dict) and str(item.get("email") or "").strip().lower() == target:
            return item
    return None


def mark_invite_tracker_status(team_email: str, email: str, status: str) -> None:
    """更新邀请跟踪状态。AI by zb"""
    with _tracker_lock:
        tracker = load_invite_tracker()
        entries = tracker["teams"].setdefault(team_email, [])
        item = _find_tracker_entry(entries, email)
        if item:
            item["status"] = status
        else:
            entries.append({"email": email, "status": status})
        save_invite_tracker(tracker)


def find_invite_tracker_team_key(email: str) -> str:
    """根据子号邮箱查找对应的车头邮箱。AI by zb"""
    tracker = load_invite_tracker()
    for team_key, entries in (tracker.get("teams") or {}).items():
        if _find_tracker_entry(entries, email):
            return team_key
    return ""


def get_available_team(tracker):
    for team in TEAMS:
        invited = tracker["teams"].get(team["email"], [])
        if len(invited) < team.get("max_invites", 3):
            return team
    return None


def invite_to_team(email, team):
    """发送团队邀请，token 失效（401）时自动刷新后重试一次"""
    if not team.get("account_id") or not team.get("auth_token"):
        restore_team_session_state(team)
    if not team.get("account_id") or not team.get("auth_token"):
        if not refresh_team_session_http(team):
            logger.error("未能获取母号 session，跳过邀请: %s", email)
            return False

    for attempt in range(2):
        account_id = team["account_id"]  # 应为 UUID 格式
        invite_url = f"https://chatgpt.com/backend-api/accounts/{account_id}/invites"
        headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "authorization": team["auth_token"],
            "chatgpt-account-id": account_id,
            "content-type": "application/json",
            "origin": "https://chatgpt.com",
            "referer": "https://chatgpt.com/",
            "user-agent": USER_AGENT,
        }
        payload = {
            "email_addresses": [email],
            "role": "standard-user",
            "resend_emails": True,
        }
        try:
            resp = http_session.post(invite_url, headers=headers, json=payload, timeout=15)
            if resp.status_code == 200:
                result = resp.json()
                if result.get("account_invites"):
                    logger.info("✅ 邀请成功: %s → %s", email, team["name"])
                    return True
                elif result.get("errored_emails"):
                    logger.warning("邀请出错: %s | %s", email, result["errored_emails"])
                    return False
                logger.warning("邀请响应无明确结果，按软成功继续: %s", result)
                return True
            elif resp.status_code == 401 and attempt == 0:
                logger.info("Token 已过期，刷新后重试...")
                team.pop("auth_token", None)
                team.pop("account_id", None)
                if not refresh_team_session_http(team):
                    return False
                continue
            logger.warning("邀请失败: HTTP %s | %s", resp.status_code, resp.text[:200])
            return False
        except Exception as e:
            logger.warning("邀请请求异常: %s", e)
            return False
    return False


def auto_invite_to_team(email):
    """线程安全地选择可用车头并发送邀请"""
    with _tracker_lock:
        tracker = load_invite_tracker()
        logger.info("当前邀请跟踪状态: %s", tracker)
        for team_key, entries in tracker["teams"].items():
            item = _find_tracker_entry(entries, email)
            if item:
                logger.info("⚠️ %s 已记录邀请状态=%s，跳过重复发送", email, item.get("status", "sent"))
                return False
        team = get_available_team(tracker)
        if not team:
            logger.warning("所有车头已满，无可用名额")
            return False
        team_key = team["email"]
        if team_key not in tracker["teams"]:
            tracker["teams"][team_key] = []
        tracker["teams"][team_key].append({"email": email, "status": "pending"})
        save_invite_tracker(tracker)

    ok = invite_to_team(email, team)
    if not ok:
        with _tracker_lock:
            tracker = load_invite_tracker()
            lst = tracker["teams"].get(team_key, [])
            item = _find_tracker_entry(lst, email)
            if item in lst:
                lst.remove(item)
            save_invite_tracker(tracker)
    else:
        invited_count = len(tracker["teams"].get(team_key, []))
        mark_invite_tracker_status(team_key, email, "sent")
        logger.info("车头状态: %s %d/%d", team.get("name"), invited_count, team.get("max_invites", 3))
    return ok


# ============================================================
# ⑯ CSV 保存
# ============================================================

_csv_lock = threading.Lock()


def save_to_txt(email, password):
    """保存账号到 TXT（一行一个：email|password|时间）"""
    with _csv_lock:
        with open(ACCOUNTS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{email}|{password}|{time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    logger.info("📄 已保存: %s → %s", email, ACCOUNTS_FILE)


# ============================================================
# ⑰ 单账号注册主流程
# ============================================================

def register_one_account(proxy=""):
    """
    完整注册一个新子账号：
    1. 创建临时邮箱
    2. HTTP 五步注册（ProtocolRegistrar）
    3. 发送团队邀请（如有车头）
    4. HTTP OAuth 登录获取 Codex token
    5. 上传 token 到 Sub2Api + 保存本地
    """
    # 1. 创建临时邮箱
    email, jwt_token = create_temp_email()
    if not email:
        logger.error("创建临时邮箱失败，跳过")
        return None, None, False

    password = generate_random_password()
    logger.info("=" * 60)
    logger.info("📧 邮箱: %s", email)

    # 2. HTTP 五步注册
    registrar = ProtocolRegistrar(proxy=proxy)
    reg_ok = registrar.register(email=email, jwt_token=jwt_token, password=password)
    if not reg_ok:
        logger.error("❌ 注册失败 | email=%s", email)
        save_to_txt(email, password)
        return email, password, False

    logger.info("✅ 注册成功 | email=%s", email)
    save_to_txt(email, password)
    time.sleep(3)

    # 3. 团队邀请
    invited = False
    if TEAMS:
        logger.info("📨 发送团队邀请 | email=%s", email)
        invited = auto_invite_to_team(email)
        if not invited:
            logger.warning("⚠️ 邀请失败，继续尝试获取 Codex token | email=%s", email)

    if invited:
        logger.info("⏳ 等待邀请生效 (5s)...")
        time.sleep(5)

    codex_result = CodexLoginTool.run_gpt_team_post_invite_flow(
        mode=CODEX_LOGIN_MODE,
        gpt_team_callable=perform_http_oauth_login,
        email=email,
        password=password,
        cf_token=jwt_token,
        worker_domain=TEMP_MAIL_WORKER_DOMAIN,
        oauth_issuer=OPENAI_AUTH_BASE,
        oauth_client_id=OAUTH_CLIENT_ID,
        oauth_redirect_uri=OAUTH_REDIRECT_URI,
        proxy=proxy,
        logger=logger,
        attempts=3,
        retry_delay_seconds=5,
        build_token_dict_callable=build_token_dict,
        upload_callable=_push_account_to_sub2api if AUTO_UPLOAD_SUB2API and SUB2API_BASE_URL else None,
        output_dir=_resolve_local_path("output_tokens", "output_tokens"),
    )

    if not codex_result.success or not codex_result.tokens:
        if invited:
            team_key = find_invite_tracker_team_key(email)
            if team_key:
                mark_invite_tracker_status(team_key, email, "sent")
                logger.warning("⚠️ 邀请已发送，但尚未确认接受 | email=%s", email)
        return email, password, True

    if invited:
        team_key = find_invite_tracker_team_key(email)
        if team_key:
            mark_invite_tracker_status(team_key, email, "accepted")
            logger.info("✅ 邀请接受状态已确认 | email=%s | team=%s", email, team_key)
    return email, password, True


# ============================================================
# ⑱ 批量注册入口
# ============================================================

def run_batch():
    logger.info("=" * 60)
    logger.info("🚀 开始批量注册，目标账号数: %d", TOTAL_ACCOUNTS)
    logger.info("=" * 60)

    if TEAMS:
        logger.info("� 已配置 %d 个车头，session 按需获取", len(TEAMS))
    else:
        logger.warning("⚠️ 未配置任何车头，将跳过邀请步骤\n")

    success_count = 0
    fail_count = 0
    registered = []

    for i in range(TOTAL_ACCOUNTS):
        logger.info("#" * 60)
        logger.info("📝 注册账号 %d/%d", i + 1, TOTAL_ACCOUNTS)
        logger.info("#" * 60)

        email, password, success = register_one_account()

        if success:
            success_count += 1
            if email:
                registered.append(email)
        else:
            fail_count += 1

        logger.info("-" * 40)
        logger.info("📊 进度: %d/%d | ✅成功: %d | ❌失败: %d",
                    i + 1, TOTAL_ACCOUNTS, success_count, fail_count)
        logger.info("-" * 40)

        if i < TOTAL_ACCOUNTS - 1:
            wait_time = random.randint(5, 20)
            logger.info("⏳ 等待 %ds 后注册下一个...", wait_time)
            time.sleep(wait_time)

    logger.info("=" * 60)
    logger.info("🏁 批量注册完成")
    logger.info("   总计: %d | ✅成功: %d | ❌失败: %d", TOTAL_ACCOUNTS, success_count, fail_count)
    for e in registered:
        logger.info("     - %s", e)
    logger.info("=" * 60)


# ============================================================
# ⑲ 仅邀请测试入口
# ============================================================

def run_invite_only_test(target_email: str = INVITE_ONLY_TEST_EMAIL) -> bool:
    """直接邀请固定测试邮箱，不执行注册流程。AI by zb"""
    if not TEAMS:
        logger.error("未配置任何车头，无法执行邀请测试")
        return False

    team = TEAMS[0]
    logger.info("=" * 60)
    logger.info(
        "开始仅邀请测试 | team=%s | mother=%s | target=%s",
        team.get("name", "unknown"),
        team.get("email", ""),
        target_email,
    )
    logger.info("=" * 60)

    ok = invite_to_team(target_email, team)
    if ok:
        logger.info("✅ 仅邀请测试成功 | target=%s", target_email)
    else:
        logger.warning("❌ 仅邀请测试失败 | target=%s", target_email)
    return ok


# ============================================================
# ⑳ 程序入口
# ============================================================

if __name__ == "__main__":
    if "--invite-only" in sys.argv:
        sys.exit(0 if run_invite_only_test() else 1)
    run_batch()
