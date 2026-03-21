"""
ChatGPT 批量自动注册工具 (并发版) - 邮件 API 版
依赖: pip install curl_cffi
功能: 使用邮件 API 创建邮箱，并发自动注册 ChatGPT 账号，自动获取 OTP 验证码
"""

import os
import re
import uuid
import json
import random
import string
import time
import sys
import threading
import traceback
import secrets
import hashlib
import base64
from datetime import datetime, timezone
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, parse_qs, urlencode

from curl_cffi import requests as curl_requests

# ================= 加载配置 =================
def _load_config():
    """从 config.json 加载配置，环境变量优先级更高"""
    config = {
        "total_accounts": 3,
        "duckmail_api_base": "https://api.duckmail.sbs",
        "duckmail_bearer": "",
        "duckmail_use_proxy": True,
        "proxy_enabled": True,
        "proxy": "",
        "proxy_list_enabled": True,
        "proxy_list_url": "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/US/data.txt",
        "proxy_validate_enabled": True,
        "proxy_validate_timeout_seconds": 6,
        "proxy_validate_workers": 40,
        "proxy_validate_test_url": "https://auth.openai.com/",
        "proxy_max_retries_per_request": 30,
        "proxy_bad_ttl_seconds": 180,
        "proxy_retry_attempts_per_account": 20,
        "stable_proxy_file": "stable_proxy.txt",
        "stable_proxy": "",
        "prefer_stable_proxy": True,
        "output_file": "registered_accounts.txt",
        "enable_oauth": True,
        "oauth_required": True,
        "oauth_issuer": "https://auth.openai.com",
        "oauth_client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
        "oauth_redirect_uri": "http://localhost:1455/auth/callback",
        "ak_file": "ak.txt",
        "rk_file": "rk.txt",
        "token_json_dir": "codex_tokens",
        "sub2api_base_url": "",
        "sub2api_bearer": "",
        "sub2api_email": "",
        "sub2api_password": "",
        "auto_upload_sub2api": False,
        "sub2api_group_ids": [2],
    }

    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                file_config = json.load(f)
                config.update(file_config)
        except Exception as e:
            print(f"⚠️ 加载 config.json 失败: {e}")

    # 环境变量优先级更高
    config["duckmail_api_base"] = os.environ.get("DUCKMAIL_API_BASE", config["duckmail_api_base"])
    config["duckmail_bearer"] = os.environ.get("DUCKMAIL_BEARER", config["duckmail_bearer"])
    config["duckmail_use_proxy"] = os.environ.get("DUCKMAIL_USE_PROXY", config["duckmail_use_proxy"])
    config["proxy_enabled"] = os.environ.get("PROXY_ENABLED", config["proxy_enabled"])
    config["proxy"] = os.environ.get("PROXY", config["proxy"])
    config["proxy_list_enabled"] = os.environ.get("PROXY_LIST_ENABLED", config["proxy_list_enabled"])
    config["proxy_list_url"] = os.environ.get("PROXY_LIST_URL", config["proxy_list_url"])
    config["proxy_validate_enabled"] = os.environ.get("PROXY_VALIDATE_ENABLED", config["proxy_validate_enabled"])
    config["proxy_validate_timeout_seconds"] = float(os.environ.get(
        "PROXY_VALIDATE_TIMEOUT_SECONDS", config["proxy_validate_timeout_seconds"]
    ))
    config["proxy_validate_workers"] = int(os.environ.get("PROXY_VALIDATE_WORKERS", config["proxy_validate_workers"]))
    config["proxy_validate_test_url"] = os.environ.get("PROXY_VALIDATE_TEST_URL", config["proxy_validate_test_url"])
    config["total_accounts"] = int(os.environ.get("TOTAL_ACCOUNTS", config["total_accounts"]))
    config["proxy_max_retries_per_request"] = int(os.environ.get(
        "PROXY_MAX_RETRIES_PER_REQUEST", config["proxy_max_retries_per_request"]
    ))
    config["proxy_bad_ttl_seconds"] = int(os.environ.get("PROXY_BAD_TTL_SECONDS", config["proxy_bad_ttl_seconds"]))
    config["proxy_retry_attempts_per_account"] = int(os.environ.get(
        "PROXY_RETRY_ATTEMPTS_PER_ACCOUNT", config["proxy_retry_attempts_per_account"]
    ))
    config["stable_proxy_file"] = os.environ.get("STABLE_PROXY_FILE", config["stable_proxy_file"])
    config["stable_proxy"] = os.environ.get("STABLE_PROXY", config["stable_proxy"])
    config["prefer_stable_proxy"] = os.environ.get("PREFER_STABLE_PROXY", config["prefer_stable_proxy"])
    config["enable_oauth"] = os.environ.get("ENABLE_OAUTH", config["enable_oauth"])
    config["oauth_required"] = os.environ.get("OAUTH_REQUIRED", config["oauth_required"])
    config["oauth_issuer"] = os.environ.get("OAUTH_ISSUER", config["oauth_issuer"])
    config["oauth_client_id"] = os.environ.get("OAUTH_CLIENT_ID", config["oauth_client_id"])
    config["oauth_redirect_uri"] = os.environ.get("OAUTH_REDIRECT_URI", config["oauth_redirect_uri"])
    config["ak_file"] = os.environ.get("AK_FILE", config["ak_file"])
    config["rk_file"] = os.environ.get("RK_FILE", config["rk_file"])
    config["token_json_dir"] = os.environ.get("TOKEN_JSON_DIR", config["token_json_dir"])
    config["sub2api_base_url"] = os.environ.get("SUB2API_BASE_URL", config["sub2api_base_url"])
    config["sub2api_bearer"] = os.environ.get("SUB2API_BEARER", config["sub2api_bearer"])
    config["sub2api_email"] = os.environ.get("SUB2API_EMAIL", config["sub2api_email"])
    config["sub2api_password"] = os.environ.get("SUB2API_PASSWORD", config["sub2api_password"])
    config["auto_upload_sub2api"] = os.environ.get("AUTO_UPLOAD_SUB2API", config["auto_upload_sub2api"])
    _raw_group_ids = os.environ.get("SUB2API_GROUP_IDS")
    if _raw_group_ids:
        try:
            config["sub2api_group_ids"] = [int(x.strip()) for x in _raw_group_ids.split(",") if x.strip().isdigit()]
        except Exception:
            pass

    return config


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


_CONFIG = _load_config()
DUCKMAIL_API_BASE = _CONFIG["duckmail_api_base"]
DUCKMAIL_BEARER = _CONFIG["duckmail_bearer"]
DUCKMAIL_USE_PROXY = _as_bool(_CONFIG.get("duckmail_use_proxy", True))
DEFAULT_TOTAL_ACCOUNTS = _CONFIG["total_accounts"]
PROXY_ENABLED = _as_bool(_CONFIG.get("proxy_enabled", True))
DEFAULT_PROXY = _CONFIG["proxy"]
PROXY_LIST_ENABLED = _as_bool(_CONFIG.get("proxy_list_enabled", True))
PROXY_LIST_URL = _CONFIG["proxy_list_url"]
PROXY_VALIDATE_ENABLED = _as_bool(_CONFIG.get("proxy_validate_enabled", True))
PROXY_VALIDATE_TIMEOUT_SECONDS = max(1.0, float(_CONFIG.get("proxy_validate_timeout_seconds", 6)))
PROXY_VALIDATE_WORKERS = max(1, int(_CONFIG.get("proxy_validate_workers", 40)))
PROXY_VALIDATE_TEST_URL = str(_CONFIG.get("proxy_validate_test_url", "https://auth.openai.com/")).strip() or "https://auth.openai.com/"
PROXY_MAX_RETRIES_PER_REQUEST = max(1, int(_CONFIG.get("proxy_max_retries_per_request", 30)))
PROXY_BAD_TTL_SECONDS = max(10, int(_CONFIG.get("proxy_bad_ttl_seconds", 180)))
PROXY_RETRY_ATTEMPTS_PER_ACCOUNT = max(1, int(_CONFIG.get("proxy_retry_attempts_per_account", 20)))
STABLE_PROXY_FILE = _CONFIG.get("stable_proxy_file", "stable_proxy.txt")
STABLE_PROXY_RAW = _CONFIG.get("stable_proxy", "")
PREFER_STABLE_PROXY = _as_bool(_CONFIG.get("prefer_stable_proxy", True))
DEFAULT_OUTPUT_FILE = _CONFIG["output_file"]
ENABLE_OAUTH = _as_bool(_CONFIG.get("enable_oauth", True))
OAUTH_REQUIRED = _as_bool(_CONFIG.get("oauth_required", True))
OAUTH_ISSUER = _CONFIG["oauth_issuer"].rstrip("/")
OAUTH_CLIENT_ID = str(_CONFIG.get("oauth_client_id", "") or "").strip() or "app_EMoamEEZ73f0CkXaXp7hrann"
OAUTH_REDIRECT_URI = _CONFIG["oauth_redirect_uri"]
AK_FILE = _CONFIG["ak_file"]
RK_FILE = _CONFIG["rk_file"]
TOKEN_JSON_DIR = _CONFIG["token_json_dir"]
SUB2API_BASE_URL = str(_CONFIG.get("sub2api_base_url", "") or "").strip().rstrip("/")
SUB2API_BEARER = str(_CONFIG.get("sub2api_bearer", "") or "").strip()
SUB2API_EMAIL = str(_CONFIG.get("sub2api_email", "") or "").strip()
SUB2API_PASSWORD = str(_CONFIG.get("sub2api_password", "") or "").strip()
AUTO_UPLOAD_SUB2API = _as_bool(_CONFIG.get("auto_upload_sub2api", False))
_raw = _CONFIG.get("sub2api_group_ids", [2])
SUB2API_GROUP_IDS = [int(x) for x in (_raw if isinstance(_raw, list) else [_raw]) if str(x).strip().lstrip("-").isdigit()]

# Sub2Api bearer token 可能在运行时通过登录刷新，使用可变容器保存
_sub2api_bearer_holder = [SUB2API_BEARER]
_sub2api_auth_lock = threading.Lock()

if not DUCKMAIL_BEARER:
    print("⚠️ 警告: 未设置 duckmail_bearer(JWT_TOKEN)，请在 config.json 中设置或设置环境变量")
    print("   文件: config.json -> duckmail_bearer")
    print("   环境变量: export DUCKMAIL_BEARER='your_jwt_token'")

# 全局线程锁
_print_lock = threading.Lock()
_file_lock = threading.Lock()
# 停止信号：外部调用 _stop_event.set() 可中断注册循环
_stop_event = threading.Event()


def _normalize_proxy(proxy: str):
    if not proxy:
        return None
    value = str(proxy).strip()
    if not value:
        return None
    if "://" in value:
        return value
    return f"http://{value}"


STABLE_PROXY = _normalize_proxy(STABLE_PROXY_RAW)


def _normalize_proxy_list_url(url: str):
    value = (url or "").strip()
    if not value:
        return "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/US/data.txt"

    m = re.match(r"^https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)$", value)
    if m:
        owner, repo, branch, path = m.groups()
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
    return value


class ProxyPool:
    """线程安全代理池：使用 HTTP/SOCKS 代理并轮询"""

    def __init__(self, list_url: str, fallback_proxy: str = None,
                 max_retries_per_request: int = 30, bad_ttl_seconds: int = 180,
                 validate_enabled: bool = True, validate_timeout_seconds: float = 6,
                 validate_workers: int = 40, validate_test_url: str = "https://auth.openai.com/",
                 prefer_stable_proxy: bool = True, list_enabled: bool = True):
        self.list_url = _normalize_proxy_list_url(list_url)
        self.fallback_proxy = _normalize_proxy(fallback_proxy)
        self.list_enabled = bool(list_enabled)
        self.max_retries_per_request = max(1, int(max_retries_per_request))
        self.bad_ttl_seconds = max(10, int(bad_ttl_seconds))
        self.validate_enabled = bool(validate_enabled)
        self.validate_timeout_seconds = max(1.0, float(validate_timeout_seconds))
        self.validate_workers = max(1, int(validate_workers))
        self.validate_test_url = str(validate_test_url).strip() or "https://auth.openai.com/"
        self.prefer_stable_proxy = bool(prefer_stable_proxy)
        self._lock = threading.Lock()
        self._loaded = False
        self._proxies = []
        self._index = 0
        self._bad_until = {}
        self._last_fetched_count = 0
        self._last_valid_count = 0
        self._stable_proxy = None
        self._last_error = ""

    def set_fallback(self, proxy: str):
        normalized = _normalize_proxy(proxy)
        if normalized:
            with self._lock:
                self.fallback_proxy = normalized

    def set_stable_proxy(self, proxy: str):
        normalized = _normalize_proxy(proxy)
        if not normalized:
            return
        with self._lock:
            self._stable_proxy = normalized
            self._bad_until.pop(normalized, None)

    def set_prefer_stable_proxy(self, enabled: bool):
        with self._lock:
            self.prefer_stable_proxy = bool(enabled)

    def set_list_enabled(self, enabled: bool):
        """切换是否使用代理列表。AI by zb"""
        with self._lock:
            enabled = bool(enabled)
            if self.list_enabled == enabled:
                return
            self.list_enabled = enabled
            self._loaded = False

    def get_stable_proxy(self):
        with self._lock:
            return self._stable_proxy

    def _fetch_proxies(self):
        res = curl_requests.get(self.list_url, timeout=20)
        if res.status_code != 200:
            raise Exception(f"HTTP {res.status_code}")

        proxies = []
        seen = set()
        for raw_line in res.text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if not (
                line.startswith("http://")
                or line.startswith("socks4://")
                or line.startswith("socks5://")
            ):
                continue
            if line in seen:
                continue
            seen.add(line)
            proxies.append(line)
        return proxies

    def _validate_single_proxy(self, proxy: str):
        try:
            res = curl_requests.get(
                self.validate_test_url,
                timeout=self.validate_timeout_seconds,
                allow_redirects=False,
                proxies={"http": proxy, "https": proxy},
                impersonate="chrome131",
            )
            return 200 <= res.status_code < 500
        except Exception:
            return False

    def _filter_valid_proxies(self, proxies):
        if not self.validate_enabled or not proxies:
            return list(proxies)

        workers = min(self.validate_workers, len(proxies))
        valid = []
        total = len(proxies)
        done = 0
        started_at = time.time()
        last_log_at = started_at

        with _print_lock:
            print(
                f"[ProxyCheck] 开始校验代理: 总数 {total}, 并发 {workers}, "
                f"超时 {self.validate_timeout_seconds}s, 测试URL {self.validate_test_url}"
            )

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(self._validate_single_proxy, proxy): proxy for proxy in proxies}
            for future in as_completed(futures):
                proxy = futures[future]
                done += 1
                try:
                    if future.result():
                        valid.append(proxy)
                except Exception:
                    pass

                now = time.time()
                if done == total or (now - last_log_at) >= 1.5:
                    with _print_lock:
                        print(f"[ProxyCheck] 进度 {done}/{total}, 可用 {len(valid)}")
                    last_log_at = now

        elapsed = time.time() - started_at
        with _print_lock:
            print(f"[ProxyCheck] 校验完成: 可用 {len(valid)}/{total}, 耗时 {elapsed:.1f}s")
        return valid

    def refresh(self, force=False):
        with self._lock:
            if self._loaded and not force:
                return
            list_enabled = self.list_enabled
            stable_proxy = self._stable_proxy
            fallback_proxy = self.fallback_proxy

        proxies = []
        fetched_proxies = []
        last_error = ""
        if list_enabled:
            try:
                fetched_proxies = self._fetch_proxies()
                proxies = self._filter_valid_proxies(fetched_proxies)
                if self.validate_enabled and fetched_proxies and not proxies:
                    last_error = "代理校验后无可用代理"
            except Exception as e:
                last_error = str(e)
        else:
            seen = set()
            for proxy in (stable_proxy, fallback_proxy):
                normalized = _normalize_proxy(proxy)
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    proxies.append(normalized)

        with self._lock:
            self._last_fetched_count = len(fetched_proxies)
            self._last_valid_count = len(proxies) if self.validate_enabled else len(fetched_proxies)
            if proxies:
                random.shuffle(proxies)
                self._proxies = proxies
                self._index = 0
                self._bad_until = {}
                self._last_error = ""
            elif not self._proxies:
                self._proxies = [self.fallback_proxy] if self.fallback_proxy else []
                self._index = 0
                self._last_error = last_error
            else:
                self._last_error = last_error
            self._loaded = True

    def next_proxy(self):
        self.refresh()
        with self._lock:
            if not self._proxies:
                return None
            now = time.time()
            stable = self._stable_proxy if self.prefer_stable_proxy else None
            if stable:
                stable_bad_until = self._bad_until.get(stable, 0)
                if stable_bad_until and stable_bad_until <= now:
                    self._bad_until.pop(stable, None)
                    stable_bad_until = 0
                if stable_bad_until > now:
                    self._stable_proxy = None
                else:
                    return stable

            total = len(self._proxies)
            for _ in range(total):
                proxy = self._proxies[self._index]
                self._index = (self._index + 1) % total

                bad_until = self._bad_until.get(proxy, 0)
                if bad_until and bad_until <= now:
                    self._bad_until.pop(proxy, None)
                    bad_until = 0

                if bad_until > now:
                    continue
                return proxy

            fallback = self.fallback_proxy
            if fallback:
                bad_until = self._bad_until.get(fallback, 0)
                if bad_until and bad_until <= now:
                    self._bad_until.pop(fallback, None)
                    bad_until = 0
                if bad_until <= now:
                    return fallback
            # 所有代理都在冷却时，仍尝试一个代理，避免长时间完全不可用
            proxy = self._proxies[self._index]
            self._index = (self._index + 1) % total
            return proxy

    def report_bad(self, proxy: str, error=None):
        normalized = _normalize_proxy(proxy)
        if not normalized:
            return

        until = time.time() + self.bad_ttl_seconds
        with self._lock:
            self._bad_until[normalized] = until
            if self._stable_proxy == normalized:
                self._stable_proxy = None
            if error:
                self._last_error = f"{normalized} -> {str(error)[:160]}"

    def report_success(self, proxy: str):
        normalized = _normalize_proxy(proxy)
        if not normalized:
            return
        with self._lock:
            self._stable_proxy = normalized
            self._bad_until.pop(normalized, None)

    def request_retry_limit(self):
        self.refresh()
        with self._lock:
            pool_size = len(self._proxies)
            if self.fallback_proxy and self.fallback_proxy not in self._proxies:
                pool_size += 1
            max_retries = self.max_retries_per_request
        return max(1, min(max_retries, max(1, pool_size)))

    def info(self):
        with self._lock:
            now = time.time()
            bad_count = 0
            for until in self._bad_until.values():
                if until > now:
                    bad_count += 1
            return {
                "list_url": self.list_url,
                "list_enabled": self.list_enabled,
                "count": len(self._proxies),
                "fetched_count": self._last_fetched_count,
                "validated_count": self._last_valid_count,
                "validate_enabled": self.validate_enabled,
                "validate_test_url": self.validate_test_url,
                "validate_timeout_seconds": self.validate_timeout_seconds,
                "validate_workers": self.validate_workers,
                "bad_count": bad_count,
                "fallback_proxy": self.fallback_proxy,
                "stable_proxy": self._stable_proxy,
                "prefer_stable_proxy": self.prefer_stable_proxy,
                "max_retries_per_request": self.max_retries_per_request,
                "bad_ttl_seconds": self.bad_ttl_seconds,
                "last_error": self._last_error,
            }


_proxy_pool = ProxyPool(
    PROXY_LIST_URL,
    fallback_proxy=DEFAULT_PROXY,
    max_retries_per_request=PROXY_MAX_RETRIES_PER_REQUEST,
    bad_ttl_seconds=PROXY_BAD_TTL_SECONDS,
    validate_enabled=PROXY_VALIDATE_ENABLED,
    validate_timeout_seconds=PROXY_VALIDATE_TIMEOUT_SECONDS,
    validate_workers=PROXY_VALIDATE_WORKERS,
    validate_test_url=PROXY_VALIDATE_TEST_URL,
    prefer_stable_proxy=PREFER_STABLE_PROXY,
    list_enabled=PROXY_LIST_ENABLED,
)
_stable_proxy_loaded = False


def _get_proxy_pool(fallback_proxy=None):
    global _stable_proxy_loaded
    _proxy_pool.set_prefer_stable_proxy(PREFER_STABLE_PROXY)
    _proxy_pool.set_list_enabled(PROXY_LIST_ENABLED)
    if not _stable_proxy_loaded:
        stable = STABLE_PROXY or _load_stable_proxy_from_file()
        if stable:
            _proxy_pool.set_stable_proxy(stable)
        _stable_proxy_loaded = True
    if fallback_proxy:
        _proxy_pool.set_fallback(fallback_proxy)
    return _proxy_pool


def _is_proxy_related_error(exc: Exception):
    class_name = exc.__class__.__name__.lower()
    if "proxy" in class_name:
        return True

    curl_code = getattr(exc, "code", None)
    if curl_code in {5, 6, 7, 28, 35, 47, 52, 55, 56, 97}:
        return True

    msg = str(exc).lower()
    keywords = [
        "proxy",
        "connect tunnel failed",
        "could not connect",
        "connection refused",
        "timed out",
    ]
    for word in keywords:
        if word in msg:
            return True
    return False


def _enable_proxy_rotation(session, fallback_proxy=None, fixed_proxy=None):
    if not PROXY_ENABLED:
        session.trust_env = False
        return session
    pool = _get_proxy_pool(fallback_proxy)
    fixed_proxy = _normalize_proxy(fixed_proxy)
    original_request = session.request
    if getattr(original_request, "_proxy_rotation_wrapped", False):
        return session

    def _request_with_rotating_proxy(method, url, **kwargs):
        if kwargs.get("proxies"):
            return original_request(method, url, **kwargs)

        if fixed_proxy:
            req_kwargs = dict(kwargs)
            req_kwargs["proxies"] = {"http": fixed_proxy, "https": fixed_proxy}
            try:
                return original_request(method, url, **req_kwargs)
            except Exception as e:
                if _is_proxy_related_error(e):
                    pool.report_bad(fixed_proxy, error=e)
                raise

        retry_limit = pool.request_retry_limit()
        last_error = None

        for _ in range(retry_limit):
            proxy = pool.next_proxy()
            req_kwargs = kwargs
            if proxy:
                req_kwargs = dict(kwargs)
                req_kwargs["proxies"] = {"http": proxy, "https": proxy}

            try:
                return original_request(method, url, **req_kwargs)
            except Exception as e:
                last_error = e
                if not proxy:
                    raise
                if not _is_proxy_related_error(e):
                    raise
                pool.report_bad(proxy, error=e)

        if last_error:
            raise last_error
        return original_request(method, url, **kwargs)

    _request_with_rotating_proxy._proxy_rotation_wrapped = True
    session.request = _request_with_rotating_proxy
    return session


# Chrome 指纹配置: impersonate 与 sec-ch-ua 必须匹配真实浏览器
_CHROME_PROFILES = [
    {
        "major": 131, "impersonate": "chrome131",
        "build": 6778, "patch_range": (69, 205),
        "sec_ch_ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    },
    {
        "major": 133, "impersonate": "chrome133a",
        "build": 6943, "patch_range": (33, 153),
        "sec_ch_ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
    },
    {
        "major": 136, "impersonate": "chrome136",
        "build": 7103, "patch_range": (48, 175),
        "sec_ch_ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
    },
    {
        "major": 142, "impersonate": "chrome142",
        "build": 7540, "patch_range": (30, 150),
        "sec_ch_ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
    },
]


def _random_chrome_version():
    profile = random.choice(_CHROME_PROFILES)
    major = profile["major"]
    build = profile["build"]
    patch = random.randint(*profile["patch_range"])
    full_ver = f"{major}.0.{build}.{patch}"
    ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{full_ver} Safari/537.36"
    return profile["impersonate"], major, full_ver, ua, profile["sec_ch_ua"]


def _random_delay(low=0.3, high=1.0):
    time.sleep(random.uniform(low, high))


def _make_trace_headers():
    trace_id = random.randint(10**17, 10**18 - 1)
    parent_id = random.randint(10**17, 10**18 - 1)
    tp = f"00-{uuid.uuid4().hex}-{format(parent_id, '016x')}-01"
    return {
        "traceparent": tp, "tracestate": "dd=s:1;o:rum",
        "x-datadog-origin": "rum", "x-datadog-sampling-priority": "1",
        "x-datadog-trace-id": str(trace_id), "x-datadog-parent-id": str(parent_id),
    }


def _generate_pkce():
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


class SentinelTokenGenerator:
    """纯 Python 版本 sentinel token 生成器（PoW）"""

    MAX_ATTEMPTS = 500000
    ERROR_PREFIX = "wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D"

    def __init__(self, device_id=None, user_agent=None):
        self.device_id = device_id or str(uuid.uuid4())
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/145.0.0.0 Safari/537.36"
        )
        self.requirements_seed = str(random.random())
        self.sid = str(uuid.uuid4())

    @staticmethod
    def _fnv1a_32(text: str):
        h = 2166136261
        for ch in text:
            h ^= ord(ch)
            h = (h * 16777619) & 0xFFFFFFFF
        h ^= (h >> 16)
        h = (h * 2246822507) & 0xFFFFFFFF
        h ^= (h >> 13)
        h = (h * 3266489909) & 0xFFFFFFFF
        h ^= (h >> 16)
        h &= 0xFFFFFFFF
        return format(h, "08x")

    def _get_config(self):
        now_str = time.strftime(
            "%a %b %d %Y %H:%M:%S GMT+0000 (Coordinated Universal Time)",
            time.gmtime(),
        )
        perf_now = random.uniform(1000, 50000)
        time_origin = time.time() * 1000 - perf_now
        nav_prop = random.choice([
            "vendorSub", "productSub", "vendor", "maxTouchPoints",
            "scheduling", "userActivation", "doNotTrack", "geolocation",
            "connection", "plugins", "mimeTypes", "pdfViewerEnabled",
            "webkitTemporaryStorage", "webkitPersistentStorage",
            "hardwareConcurrency", "cookieEnabled", "credentials",
            "mediaDevices", "permissions", "locks", "ink",
        ])
        nav_val = f"{nav_prop}-undefined"

        return [
            "1920x1080",
            now_str,
            4294705152,
            random.random(),
            self.user_agent,
            "https://sentinel.openai.com/sentinel/20260124ceb8/sdk.js",
            None,
            None,
            "en-US",
            "en-US,en",
            random.random(),
            nav_val,
            random.choice(["location", "implementation", "URL", "documentURI", "compatMode"]),
            random.choice(["Object", "Function", "Array", "Number", "parseFloat", "undefined"]),
            perf_now,
            self.sid,
            "",
            random.choice([4, 8, 12, 16]),
            time_origin,
        ]

    @staticmethod
    def _base64_encode(data):
        raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return base64.b64encode(raw).decode("ascii")

    def _run_check(self, start_time, seed, difficulty, config, nonce):
        config[3] = nonce
        config[9] = round((time.time() - start_time) * 1000)
        data = self._base64_encode(config)
        hash_hex = self._fnv1a_32(seed + data)
        diff_len = len(difficulty)
        if hash_hex[:diff_len] <= difficulty:
            return data + "~S"
        return None

    def generate_token(self, seed=None, difficulty=None):
        seed = seed if seed is not None else self.requirements_seed
        difficulty = str(difficulty or "0")
        start_time = time.time()
        config = self._get_config()

        for i in range(self.MAX_ATTEMPTS):
            result = self._run_check(start_time, seed, difficulty, config, i)
            if result:
                return "gAAAAAB" + result
        return "gAAAAAB" + self.ERROR_PREFIX + self._base64_encode(str(None))

    def generate_requirements_token(self):
        config = self._get_config()
        config[3] = 1
        config[9] = round(random.uniform(5, 50))
        data = self._base64_encode(config)
        return "gAAAAAC" + data


def fetch_sentinel_challenge(session, device_id, flow="authorize_continue", user_agent=None,
                             sec_ch_ua=None, impersonate=None):
    generator = SentinelTokenGenerator(device_id=device_id, user_agent=user_agent)
    req_body = {
        "p": generator.generate_requirements_token(),
        "id": device_id,
        "flow": flow,
    }
    headers = {
        "Content-Type": "text/plain;charset=UTF-8",
        "Referer": "https://sentinel.openai.com/backend-api/sentinel/frame.html",
        "Origin": "https://sentinel.openai.com",
        "User-Agent": user_agent or "Mozilla/5.0",
        "sec-ch-ua": sec_ch_ua or '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }

    kwargs = {
        "data": json.dumps(req_body),
        "headers": headers,
        "timeout": 20,
    }
    if impersonate:
        kwargs["impersonate"] = impersonate

    try:
        resp = session.post("https://sentinel.openai.com/backend-api/sentinel/req", **kwargs)
    except Exception:
        return None

    if resp.status_code != 200:
        return None

    try:
        return resp.json()
    except Exception:
        return None


def build_sentinel_token(session, device_id, flow="authorize_continue", user_agent=None,
                         sec_ch_ua=None, impersonate=None):
    challenge = fetch_sentinel_challenge(
        session,
        device_id,
        flow=flow,
        user_agent=user_agent,
        sec_ch_ua=sec_ch_ua,
        impersonate=impersonate,
    )
    if not challenge:
        return None

    c_value = challenge.get("token", "")
    if not c_value:
        return None

    pow_data = challenge.get("proofofwork") or {}
    generator = SentinelTokenGenerator(device_id=device_id, user_agent=user_agent)

    if pow_data.get("required") and pow_data.get("seed"):
        p_value = generator.generate_token(
            seed=pow_data.get("seed"),
            difficulty=pow_data.get("difficulty", "0"),
        )
    else:
        p_value = generator.generate_requirements_token()

    return json.dumps({
        "p": p_value,
        "t": "",
        "c": c_value,
        "id": device_id,
        "flow": flow,
    }, separators=(",", ":"))


def _extract_code_from_url(url: str):
    if not url or "code=" not in url:
        return None
    try:
        return parse_qs(urlparse(url).query).get("code", [None])[0]
    except Exception:
        return None


def _decode_jwt_payload(token: str):
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception:
        return {}


def _save_codex_tokens(email: str, tokens: dict):
    access_token = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")
    id_token = tokens.get("id_token", "")

    if access_token:
        with _file_lock:
            with open(AK_FILE, "a", encoding="utf-8") as f:
                f.write(f"{access_token}\n")

    if refresh_token:
        with _file_lock:
            with open(RK_FILE, "a", encoding="utf-8") as f:
                f.write(f"{refresh_token}\n")

    if not access_token:
        return

    payload = _decode_jwt_payload(access_token)
    auth_info = payload.get("https://api.openai.com/auth", {})
    account_id = auth_info.get("chatgpt_account_id", "")

    exp_timestamp = payload.get("exp")
    expired_str = ""
    if isinstance(exp_timestamp, int) and exp_timestamp > 0:
        from datetime import datetime, timezone, timedelta

        exp_dt = datetime.fromtimestamp(exp_timestamp, tz=timezone(timedelta(hours=8)))
        expired_str = exp_dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")

    from datetime import datetime, timezone, timedelta

    now = datetime.now(tz=timezone(timedelta(hours=8)))
    token_data = {
        "type": "codex",
        "email": email,
        "expired": expired_str,
        "id_token": id_token,
        "account_id": account_id,
        "access_token": access_token,
        "last_refresh": now.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "refresh_token": refresh_token,
    }

    base_dir = os.path.dirname(os.path.abspath(__file__))
    token_dir = TOKEN_JSON_DIR if os.path.isabs(TOKEN_JSON_DIR) else os.path.join(base_dir, TOKEN_JSON_DIR)
    os.makedirs(token_dir, exist_ok=True)

    token_path = os.path.join(token_dir, f"{email}.json")
    with _file_lock:
        with open(token_path, "w", encoding="utf-8") as f:
            json.dump(token_data, f, ensure_ascii=False)


def _stable_proxy_path():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return STABLE_PROXY_FILE if os.path.isabs(STABLE_PROXY_FILE) else os.path.join(base_dir, STABLE_PROXY_FILE)


def _load_stable_proxy_from_file():
    path = _stable_proxy_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            line = f.readline().strip()
        return _normalize_proxy(line)
    except Exception:
        return None


def _save_stable_proxy_to_config(proxy: str):
    normalized = _normalize_proxy(proxy)
    if not normalized:
        return

    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if not os.path.exists(config_path):
        return

    try:
        with _file_lock:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            config["stable_proxy"] = normalized
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
                f.write("\n")
    except Exception:
        return


def _save_stable_proxy_to_file(proxy: str):
    normalized = _normalize_proxy(proxy)
    if not normalized:
        return
    path = _stable_proxy_path()
    with _file_lock:
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{normalized}\n")


def _sub2api_login() -> str:
    """登录 Sub2Api，刷新 bearer token，返回新 token 或空字符串"""
    if not SUB2API_BASE_URL or not SUB2API_EMAIL or not SUB2API_PASSWORD:
        return ""
    url = f"{SUB2API_BASE_URL}/api/v1/auth/login"
    try:
        resp = curl_requests.post(
            url,
            json={"email": SUB2API_EMAIL, "password": SUB2API_PASSWORD},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            impersonate="chrome131",
            timeout=15,
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
    except Exception as e:
        with _print_lock:
            print(f"[Sub2Api] 登录失败: {e}")
        return ""


def _build_sub2api_account_payload(email: str, tokens: dict) -> dict:
    """构建 POST /api/v1/admin/accounts 所需的完整 payload"""
    access_token = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")
    id_token = tokens.get("id_token", "")

    at_payload = _decode_jwt_payload(access_token) if access_token else {}
    at_auth = at_payload.get("https://api.openai.com/auth") or {}
    chatgpt_account_id = at_auth.get("chatgpt_account_id", "") or tokens.get("account_id", "")
    chatgpt_user_id = at_auth.get("chatgpt_user_id", "")
    exp_timestamp = at_payload.get("exp", 0)
    expires_at = exp_timestamp if isinstance(exp_timestamp, int) and exp_timestamp > 0 else int(time.time()) + 863999

    it_payload = _decode_jwt_payload(id_token) if id_token else {}
    it_auth = it_payload.get("https://api.openai.com/auth") or {}
    organization_id = it_auth.get("organization_id", "")
    if not organization_id:
        orgs = it_auth.get("organizations") or []
        if orgs:
            organization_id = (orgs[0] or {}).get("id", "")

    return {
        "auto_pause_on_expired": True,
        "concurrency": 10,
        "credentials": {
            "access_token": access_token,
            "chatgpt_account_id": chatgpt_account_id,
            "chatgpt_user_id": chatgpt_user_id,
            "client_id": OAUTH_CLIENT_ID,
            "expires_in": 863999,
            "expires_at": expires_at,
            "model_mapping": {"gpt-3.5-turbo":"gpt-3.5-turbo","gpt-3.5-turbo-0125":"gpt-3.5-turbo-0125","gpt-3.5-turbo-1106":"gpt-3.5-turbo-1106","gpt-3.5-turbo-16k":"gpt-3.5-turbo-16k","gpt-4":"gpt-4","gpt-4-turbo":"gpt-4-turbo","gpt-4-turbo-preview":"gpt-4-turbo-preview","gpt-4o":"gpt-4o","gpt-4o-2024-08-06":"gpt-4o-2024-08-06","gpt-4o-2024-11-20":"gpt-4o-2024-11-20","gpt-4o-mini":"gpt-4o-mini","gpt-4o-mini-2024-07-18":"gpt-4o-mini-2024-07-18","gpt-4.5-preview":"gpt-4.5-preview","gpt-4.1":"gpt-4.1","gpt-4.1-mini":"gpt-4.1-mini","gpt-4.1-nano":"gpt-4.1-nano","o1":"o1","o1-preview":"o1-preview","o1-mini":"o1-mini","o1-pro":"o1-pro","o3":"o3","o3-mini":"o3-mini","o3-pro":"o3-pro","o4-mini":"o4-mini","gpt-5":"gpt-5","gpt-5-2025-08-07":"gpt-5-2025-08-07","gpt-5-chat":"gpt-5-chat","gpt-5-chat-latest":"gpt-5-chat-latest","gpt-5-codex":"gpt-5-codex","gpt-5.3-codex-spark":"gpt-5.3-codex-spark","gpt-5-pro":"gpt-5-pro","gpt-5-pro-2025-10-06":"gpt-5-pro-2025-10-06","gpt-5-mini":"gpt-5-mini","gpt-5-mini-2025-08-07":"gpt-5-mini-2025-08-07","gpt-5-nano":"gpt-5-nano","gpt-5-nano-2025-08-07":"gpt-5-nano-2025-08-07","gpt-5.1":"gpt-5.1","gpt-5.1-2025-11-13":"gpt-5.1-2025-11-13","gpt-5.1-chat-latest":"gpt-5.1-chat-latest","gpt-5.1-codex":"gpt-5.1-codex","gpt-5.1-codex-max":"gpt-5.1-codex-max","gpt-5.1-codex-mini":"gpt-5.1-codex-mini","gpt-5.2":"gpt-5.2","gpt-5.2-2025-12-11":"gpt-5.2-2025-12-11","gpt-5.2-chat-latest":"gpt-5.2-chat-latest","gpt-5.2-codex":"gpt-5.2-codex","gpt-5.2-pro":"gpt-5.2-pro","gpt-5.2-pro-2025-12-11":"gpt-5.2-pro-2025-12-11","gpt-5.4":"gpt-5.4","gpt-5.4-2026-03-05":"gpt-5.4-2026-03-05","gpt-5.3-codex":"gpt-5.3-codex","chatgpt-4o-latest":"chatgpt-4o-latest","gpt-4o-audio-preview":"gpt-4o-audio-preview","gpt-4o-realtime-preview":"gpt-4o-realtime-preview"},
            "organization_id": organization_id,
            "refresh_token": refresh_token,
        },
        "extra": {
            "email": email,
            "openai_oauth_responses_websockets_v2_enabled": True,
            "openai_oauth_responses_websockets_v2_mode": "off"
        },
        "group_ids": SUB2API_GROUP_IDS,
        "name": email,
        "notes": "",
        "platform": "openai",
        "priority": 1,
        "type": "oauth",
        "rate_multiplier": 1,
    }


def _push_account_to_sub2api(email: str, tokens: dict) -> bool:
    """
    上传完整账号信息到 Sub2Api。
    POST {SUB2API_BASE_URL}/api/v1/admin/accounts
    若返回 401 且配置了邮箱/密码，则自动重新登录后重试一次。
    返回 True 表示成功。
    """
    if not SUB2API_BASE_URL or not tokens.get("refresh_token"):
        return False

    url = f"{SUB2API_BASE_URL}/api/v1/admin/accounts"
    payload = _build_sub2api_account_payload(email, tokens)

    def _do_request(bearer: str):
        try:
            resp = curl_requests.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {bearer}",
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/plain, */*",
                    "Referer": f"{SUB2API_BASE_URL}/admin/accounts",
                },
                impersonate="chrome131",
                timeout=20,
            )
            return resp.status_code, resp.text
        except Exception as e:
            return 0, str(e)

    bearer = _sub2api_bearer_holder[0]
    status, body = _do_request(bearer)

    if status == 401 and SUB2API_EMAIL and SUB2API_PASSWORD:
        with _sub2api_auth_lock:
            if _sub2api_bearer_holder[0] == bearer:
                new_token = _sub2api_login()
                if new_token:
                    _sub2api_bearer_holder[0] = new_token
        bearer = _sub2api_bearer_holder[0]
        status, body = _do_request(bearer)

    ok = status in (200, 201)
    with _print_lock:
        if ok:
            print(f"[Sub2Api] 上传成功 (HTTP {status})")
        else:
            print(f"[Sub2Api] 上传失败 (HTTP {status}): {body[:500]}")
    return ok


def _generate_password(length=14):
    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    special = "!@#$%&*"
    pwd = [random.choice(lower), random.choice(upper),
           random.choice(digits), random.choice(special)]
    all_chars = lower + upper + digits + special
    pwd += [random.choice(all_chars) for _ in range(length - 4)]
    random.shuffle(pwd)
    return "".join(pwd)


# ================= 邮件 API 函数 =================

def _create_mail_api_session():
    """创建带重试的邮件 API 请求会话"""
    session = curl_requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
    })
    if DUCKMAIL_USE_PROXY:
        return _enable_proxy_rotation(session)
    session.trust_env = False
    return session


def _mail_api_url(path: str):
    """构造邮件 API 完整地址。AI by zb"""
    api_base = DUCKMAIL_API_BASE.rstrip("/")
    suffix = path if path.startswith("/") else f"/{path}"
    if api_base.endswith("/api"):
        return f"{api_base}{suffix}"
    return f"{api_base}/api{suffix}"


def _mail_api_headers():
    """构造邮件 API 认证头。AI by zb"""
    return {
        "Authorization": f"Bearer {DUCKMAIL_BEARER}",
        "X-Admin-Token": DUCKMAIL_BEARER,
    }


def _mail_message_sort_key(message):
    """按接收时间和 ID 生成排序键，优先最新邮件。AI by zb"""
    raw = str(
        message.get("received_at")
        or message.get("created_at")
        or message.get("date")
        or ""
    ).strip()
    ts = 0.0
    if raw:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                dt = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
                ts = dt.timestamp()
                break
            except Exception:
                continue
        if not ts:
            for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
                try:
                    ts = datetime.strptime(raw, fmt).timestamp()
                    break
                except Exception:
                    continue
        if not ts:
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                ts = dt.timestamp()
            except Exception:
                ts = 0.0

    raw_id = message.get("id") or message.get("@id") or 0
    try:
        msg_id = int(str(raw_id).rsplit("/", 1)[-1])
    except Exception:
        msg_id = 0
    return (ts, msg_id)


def _mail_message_identity(message):
    """提取邮件唯一标识，优先使用邮件 ID。AI by zb"""
    raw_id = message.get("id") or message.get("@id")
    return str(raw_id).strip() if raw_id is not None else ""


def _mail_message_id_set(messages):
    """提取邮件列表中的 ID 集合。AI by zb"""
    result = set()
    if not isinstance(messages, list):
        return result
    for msg in messages:
        identity = _mail_message_identity(msg)
        if identity:
            result.add(identity)
    return result


def _sort_mail_messages(messages):
    """按最新优先排序邮件列表。AI by zb"""
    if not isinstance(messages, list):
        return []
    return sorted(messages, key=_mail_message_sort_key, reverse=True)


def _recent_mail_messages(messages, not_before_ts=None, slack_seconds=8, exclude_message_ids=None):
    """筛选指定时间后的邮件，优先避免误用旧验证码。AI by zb"""
    ordered = _sort_mail_messages(messages)
    exclude_message_ids = set(exclude_message_ids or [])
    if not not_before_ts and not exclude_message_ids:
        return ordered

    threshold = float(not_before_ts) - max(0, int(slack_seconds))
    recent = []
    for msg in ordered:
        identity = _mail_message_identity(msg)
        if identity and identity in exclude_message_ids:
            continue
        if not not_before_ts:
            recent.append(msg)
            continue
        msg_ts, _ = _mail_message_sort_key(msg)
        if msg_ts <= 0:
            continue
        if msg_ts >= threshold:
            recent.append(msg)
    return recent


def create_temp_email():
    """创建邮件地址，返回 (email, password, mailbox_ref)"""
    if not DUCKMAIL_BEARER:
        raise Exception("duckmail_bearer(JWT_TOKEN) 未设置，无法创建临时邮箱")

    # 生成随机邮箱前缀 8-13 位
    length = random.randint(8, 13)
    session = _create_mail_api_session()

    try:
        # 1. 创建账号
        res = session.get(
            _mail_api_url("/generate"),
            params={"length": length},
            headers=_mail_api_headers(),
            timeout=15,
            impersonate="chrome131"
        )

        if res.status_code != 200:
            raise Exception(f"创建邮箱失败: {res.status_code} - {res.text[:200]}")

        data = res.json()
        email = data.get("email") or (data.get("data") or {}).get("email") or ""
        if email:
            return email, "N/A", email

        raise Exception(f"创建邮箱响应缺少 email: {str(data)[:200]}")

    except Exception as e:
        raise Exception(f"邮件 API 创建邮箱失败: {e}")


def _fetch_emails_mail_api(mailbox_ref: str):
    """按邮箱地址获取邮件列表"""
    try:
        session = _create_mail_api_session()

        res = session.get(
            _mail_api_url("/emails"),
            params={"mailbox": mailbox_ref, "limit": 20},
            headers=_mail_api_headers(),
            timeout=15,
            impersonate="chrome131"
        )

        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list):
                return data
            messages = data.get("data") or data.get("items") or []
            return messages if isinstance(messages, list) else []
        return []
    except Exception:
        return []


def _fetch_email_detail_mail_api(mailbox_ref: str, msg_id: str):
    """获取单封邮件详情"""
    try:
        session = _create_mail_api_session()

        if isinstance(msg_id, str):
            msg_id = msg_id.rsplit("/", 1)[-1]

        res = session.get(
            _mail_api_url(f"/email/{msg_id}"),
            headers=_mail_api_headers(),
            timeout=15,
            impersonate="chrome131"
        )

        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return None


def _extract_verification_code(email_content: str):
    """从邮件内容提取 6 位验证码"""
    if not email_content:
        return None

    patterns = [
        r"Verification code:?\s*(\d{6})",
        r"code is\s*(\d{6})",
        r"代码为[:：]?\s*(\d{6})",
        r"验证码[:：]?\s*(\d{6})",
        r">\s*(\d{6})\s*<",
        r"(?<![#&])\b(\d{6})\b",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, email_content, re.IGNORECASE)
        for code in matches:
            if code == "177010":  # 已知误判
                continue
            return code
    return None


def wait_for_verification_email(mailbox_ref: str, timeout: int = 120,
                                not_before_ts: float = None, exclude_message_ids=None):
    """等待并提取 OpenAI 验证码"""
    start_time = time.time()

    while time.time() - start_time < timeout:
        messages = _recent_mail_messages(
            _fetch_emails_mail_api(mailbox_ref),
            not_before_ts=not_before_ts,
            exclude_message_ids=exclude_message_ids,
        )
        if messages and len(messages) > 0:
            for msg in messages[:12]:
                code = str(msg.get("verification_code") or "").strip()
                if re.fullmatch(r"\d{6}", code) and code != "177010":
                    return code

                msg_id = msg.get("id") or msg.get("@id")
                if not msg_id:
                    continue

                detail = _fetch_email_detail_mail_api(mailbox_ref, msg_id)
                if not detail:
                    continue

                code = str(detail.get("verification_code") or "").strip()
                if re.fullmatch(r"\d{6}", code) and code != "177010":
                    return code

                content = (
                    detail.get("content")
                    or detail.get("html_content")
                    or detail.get("text")
                    or detail.get("html")
                    or detail.get("preview")
                    or msg.get("preview")
                    or ""
                )
                code = _extract_verification_code(content)
                if code:
                    return code

        time.sleep(3)

    return None


def _random_name():
    first = random.choice([
        "James", "Emma", "Liam", "Olivia", "Noah", "Ava", "Ethan", "Sophia",
        "Lucas", "Mia", "Mason", "Isabella", "Logan", "Charlotte", "Alexander",
        "Amelia", "Benjamin", "Harper", "William", "Evelyn", "Henry", "Abigail",
        "Sebastian", "Emily", "Jack", "Elizabeth",
    ])
    last = random.choice([
        "Smith", "Johnson", "Brown", "Davis", "Wilson", "Moore", "Taylor",
        "Clark", "Hall", "Young", "Anderson", "Thomas", "Jackson", "White",
        "Harris", "Martin", "Thompson", "Garcia", "Robinson", "Lewis",
        "Walker", "Allen", "King", "Wright", "Scott", "Green",
    ])
    return f"{first} {last}"


def _random_birthdate():
    y = random.randint(1985, 2002)
    m = random.randint(1, 12)
    d = random.randint(1, 28)
    return f"{y}-{m:02d}-{d:02d}"


class ChatGPTRegister:
    BASE = "https://chatgpt.com"
    AUTH = "https://auth.openai.com"

    def __init__(self, proxy: str = None, tag: str = "", fixed_proxy: str = None):
        self.tag = tag  # 线程标识，用于日志
        self.device_id = str(uuid.uuid4())
        self.auth_session_logging_id = str(uuid.uuid4())
        self.impersonate, self.chrome_major, self.chrome_full, self.ua, self.sec_ch_ua = _random_chrome_version()

        self.session = curl_requests.Session(impersonate=self.impersonate)

        self.proxy = _normalize_proxy(proxy)
        self.fixed_proxy = _normalize_proxy(fixed_proxy)
        _enable_proxy_rotation(self.session, fallback_proxy=self.proxy, fixed_proxy=self.fixed_proxy)

        self.session.headers.update({
            "User-Agent": self.ua,
            "Accept-Language": random.choice([
                "en-US,en;q=0.9", "en-US,en;q=0.9,zh-CN;q=0.8",
                "en,en-US;q=0.9", "en-US,en;q=0.8",
            ]),
            "sec-ch-ua": self.sec_ch_ua, "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"', "sec-ch-ua-arch": '"x86"',
            "sec-ch-ua-bitness": '"64"',
            "sec-ch-ua-full-version": f'"{self.chrome_full}"',
            "sec-ch-ua-platform-version": f'"{random.randint(10, 15)}.0.0"',
        })

        self.session.cookies.set("oai-did", self.device_id, domain="chatgpt.com")
        self._callback_url = None

    def _log(self, step, method, url, status, body=None):
        prefix = f"[{self.tag}] " if self.tag else ""
        lines = [
            f"\n{'='*60}",
            f"{prefix}[Step] {step}",
            f"{prefix}[{method}] {url}",
            f"{prefix}[Status] {status}",
        ]
        if body:
            try:
                lines.append(f"{prefix}[Response] {json.dumps(body, indent=2, ensure_ascii=False)[:1000]}")
            except Exception:
                lines.append(f"{prefix}[Response] {str(body)[:1000]}")
        lines.append(f"{'='*60}")
        with _print_lock:
            print("\n".join(lines))

    def _print(self, msg):
        prefix = f"[{self.tag}] " if self.tag else ""
        with _print_lock:
            print(f"{prefix}{msg}")

    def _parse_json_or_raise(self, response, step_name: str):
        if response.status_code >= 400:
            raise Exception(f"{step_name} 被拦截 ({response.status_code})")

        try:
            data = response.json()
        except Exception:
            body = (response.text or "")[:200].replace("\n", " ")
            raise Exception(
                f"{step_name} 返回非 JSON (status={response.status_code}, body={body})"
            )
        return data

    # ==================== 邮件 API ====================

    def _create_mail_api_session(self):
        """创建带重试的邮件 API 请求会话"""
        session = curl_requests.Session()
        session.headers.update({
            "User-Agent": self.ua,
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        if DUCKMAIL_USE_PROXY:
            return _enable_proxy_rotation(session, fallback_proxy=self.proxy, fixed_proxy=self.fixed_proxy)
        session.trust_env = False
        return session

    def create_temp_email(self):
        """创建邮件地址，返回 (email, password, mailbox_ref)"""
        if not DUCKMAIL_BEARER:
            raise Exception("duckmail_bearer(JWT_TOKEN) 未设置，无法创建临时邮箱")

        length = random.randint(8, 13)
        session = self._create_mail_api_session()

        try:
            res = session.get(
                _mail_api_url("/generate"),
                params={"length": length},
                headers=_mail_api_headers(),
                timeout=15,
                impersonate=self.impersonate
            )

            if res.status_code != 200:
                raise Exception(f"创建邮箱失败: {res.status_code} - {res.text[:200]}")

            data = res.json()
            email = data.get("email") or (data.get("data") or {}).get("email") or ""
            if email:
                return email, "N/A", email

            raise Exception(f"创建邮箱响应缺少 email: {str(data)[:200]}")

        except Exception as e:
            raise Exception(f"邮件 API 创建邮箱失败: {e}")

    def _fetch_emails_mail_api(self, mailbox_ref: str):
        """按邮箱地址获取邮件列表"""
        try:
            session = self._create_mail_api_session()

            res = session.get(
                _mail_api_url("/emails"),
                params={"mailbox": mailbox_ref, "limit": 20},
                headers=_mail_api_headers(),
                timeout=15,
                impersonate=self.impersonate
            )

            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list):
                    return data
                messages = data.get("data") or data.get("items") or []
                return messages if isinstance(messages, list) else []
            return []
        except Exception:
            return []

    def _fetch_email_detail_mail_api(self, mailbox_ref: str, msg_id: str):
        """获取单封邮件详情"""
        try:
            session = self._create_mail_api_session()

            if isinstance(msg_id, str):
                msg_id = msg_id.rsplit("/", 1)[-1]

            res = session.get(
                _mail_api_url(f"/email/{msg_id}"),
                headers=_mail_api_headers(),
                timeout=15,
                impersonate=self.impersonate
            )

            if res.status_code == 200:
                return res.json()
        except Exception:
            pass
        return None

    def _extract_verification_code(self, email_content: str):
        """从邮件内容提取 6 位验证码"""
        if not email_content:
            return None

        patterns = [
            r"Verification code:?\s*(\d{6})",
            r"code is\s*(\d{6})",
            r"代码为[:：]?\s*(\d{6})",
            r"验证码[:：]?\s*(\d{6})",
            r">\s*(\d{6})\s*<",
            r"(?<![#&])\b(\d{6})\b",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, email_content, re.IGNORECASE)
            for code in matches:
                if code == "177010":  # 已知误判
                    continue
                return code
        return None

    def wait_for_verification_email(self, mailbox_ref: str, timeout: int = 120,
                                    not_before_ts: float = None, exclude_message_ids=None):
        """等待并提取 OpenAI 验证码"""
        self._print(f"[OTP] 等待验证码邮件 (最多 {timeout}s)...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            messages = _recent_mail_messages(
                self._fetch_emails_mail_api(mailbox_ref),
                not_before_ts=not_before_ts,
                exclude_message_ids=exclude_message_ids,
            )
            if messages and len(messages) > 0:
                for msg in messages[:12]:
                    code = str(msg.get("verification_code") or "").strip()
                    if re.fullmatch(r"\d{6}", code) and code != "177010":
                        self._print(f"[OTP] 验证码: {code}")
                        return code

                    msg_id = msg.get("id") or msg.get("@id")
                    if not msg_id:
                        continue

                    detail = self._fetch_email_detail_mail_api(mailbox_ref, msg_id)
                    if not detail:
                        continue

                    code = str(detail.get("verification_code") or "").strip()
                    if re.fullmatch(r"\d{6}", code) and code != "177010":
                        self._print(f"[OTP] 验证码: {code}")
                        return code

                    content = (
                        detail.get("content")
                        or detail.get("html_content")
                        or detail.get("text")
                        or detail.get("html")
                        or detail.get("preview")
                        or msg.get("preview")
                        or ""
                    )
                    code = self._extract_verification_code(content)
                    if code:
                        self._print(f"[OTP] 验证码: {code}")
                        return code

            elapsed = int(time.time() - start_time)
            self._print(f"[OTP] 等待中... ({elapsed}s/{timeout}s)")
            time.sleep(3)

        self._print(f"[OTP] 超时 ({timeout}s)")
        return None

    # ==================== 注册流程 ====================

    def visit_homepage(self):
        url = f"{self.BASE}/"
        r = self.session.get(url, headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Upgrade-Insecure-Requests": "1",
        }, allow_redirects=True)
        self._log("0. Visit homepage", "GET", url, r.status_code,
                   {"cookies_count": len(self.session.cookies)})
        if r.status_code != 200:
            raise Exception(f"Visit homepage 被拦截 ({r.status_code})")

    def get_csrf(self) -> str:
        url = f"{self.BASE}/api/auth/csrf"
        r = self.session.get(url, headers={"Accept": "application/json", "Referer": f"{self.BASE}/"})
        data = self._parse_json_or_raise(r, "Get CSRF")
        token = data.get("csrfToken", "")
        self._log("1. Get CSRF", "GET", url, r.status_code, data)
        if not token:
            raise Exception("Failed to get CSRF token")
        return token

    def signin(self, email: str, csrf: str) -> str:
        url = f"{self.BASE}/api/auth/signin/openai"
        params = {
            "prompt": "login", "ext-oai-did": self.device_id,
            "auth_session_logging_id": self.auth_session_logging_id,
            "screen_hint": "login_or_signup", "login_hint": email,
        }
        form_data = {"callbackUrl": f"{self.BASE}/", "csrfToken": csrf, "json": "true"}
        r = self.session.post(url, params=params, data=form_data, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json", "Referer": f"{self.BASE}/", "Origin": self.BASE,
        })
        data = self._parse_json_or_raise(r, "Signin")
        authorize_url = data.get("url", "")
        self._log("2. Signin", "POST", url, r.status_code, data)
        if not authorize_url:
            raise Exception("Failed to get authorize URL")
        return authorize_url

    def authorize(self, url: str) -> str:
        r = self.session.get(url, headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": f"{self.BASE}/", "Upgrade-Insecure-Requests": "1",
        }, allow_redirects=True)
        final_url = str(r.url)
        self._log("3. Authorize", "GET", url, r.status_code, {"final_url": final_url})
        if r.status_code >= 400:
            raise Exception(f"Authorize 被拦截 ({r.status_code})")
        return final_url

    def register(self, email: str, password: str):
        url = f"{self.AUTH}/api/accounts/user/register"
        headers = {"Content-Type": "application/json", "Accept": "application/json",
                    "Referer": f"{self.AUTH}/create-account/password", "Origin": self.AUTH}
        headers.update(_make_trace_headers())
        r = self.session.post(url, json={"username": email, "password": password}, headers=headers)
        try: data = r.json()
        except Exception: data = {"text": r.text[:500]}
        self._log("4. Register", "POST", url, r.status_code, data)
        return r.status_code, data

    def send_otp(self):
        url = f"{self.AUTH}/api/accounts/email-otp/send"
        r = self.session.get(url, headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": f"{self.AUTH}/create-account/password", "Upgrade-Insecure-Requests": "1",
        }, allow_redirects=True)
        try: data = r.json()
        except Exception: data = {"final_url": str(r.url), "status": r.status_code}
        self._log("5. Send OTP", "GET", url, r.status_code, data)
        return r.status_code, data

    def validate_otp(self, code: str):
        url = f"{self.AUTH}/api/accounts/email-otp/validate"
        headers = {"Content-Type": "application/json", "Accept": "application/json",
                    "Referer": f"{self.AUTH}/email-verification", "Origin": self.AUTH}
        headers.update(_make_trace_headers())
        r = self.session.post(url, json={"code": code}, headers=headers)
        try: data = r.json()
        except Exception: data = {"text": r.text[:500]}
        self._log("6. Validate OTP", "POST", url, r.status_code, data)
        return r.status_code, data

    def create_account(self, name: str, birthdate: str):
        url = f"{self.AUTH}/api/accounts/create_account"
        headers = {"Content-Type": "application/json", "Accept": "application/json",
                    "Referer": f"{self.AUTH}/about-you", "Origin": self.AUTH}
        headers.update(_make_trace_headers())
        r = self.session.post(url, json={"name": name, "birthdate": birthdate}, headers=headers)
        try: data = r.json()
        except Exception: data = {"text": r.text[:500]}
        self._log("7. Create Account", "POST", url, r.status_code, data)
        if isinstance(data, dict):
            cb = data.get("continue_url") or data.get("url") or data.get("redirect_url")
            if cb:
                self._callback_url = cb
        return r.status_code, data

    def callback(self, url: str = None):
        if not url:
            url = self._callback_url
        if not url:
            self._print("[!] No callback URL, skipping.")
            return None, None
        r = self.session.get(url, headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Upgrade-Insecure-Requests": "1",
        }, allow_redirects=True)
        self._log("8. Callback", "GET", url, r.status_code, {"final_url": str(r.url)})
        return r.status_code, {"final_url": str(r.url)}

    # ==================== 自动注册主流程 ====================

    def run_register(self, email, password, name, birthdate, mailbox_ref):
        """使用邮件 API 的注册流程"""
        self.visit_homepage()
        _random_delay(0.3, 0.8)
        csrf = self.get_csrf()
        _random_delay(0.2, 0.5)
        auth_url = self.signin(email, csrf)
        _random_delay(0.3, 0.8)
        pre_authorize_message_ids = _mail_message_id_set(self._fetch_emails_mail_api(mailbox_ref))

        final_url = self.authorize(auth_url)
        final_path = urlparse(final_url).path
        _random_delay(0.3, 0.8)

        self._print(f"Authorize → {final_path}")

        need_otp = False
        otp_started_at = None
        otp_seen_message_ids = set()

        if "create-account/password" in final_path:
            self._print("全新注册流程")
            _random_delay(0.5, 1.0)
            status, data = self.register(email, password)
            if status != 200:
                raise Exception(f"Register 失败 ({status}): {data}")
            # register 之后可能还需要 send_otp（全新注册流程中 OTP 不一定在 authorize 时发送）
            _random_delay(0.3, 0.8)
            otp_seen_message_ids = _mail_message_id_set(self._fetch_emails_mail_api(mailbox_ref))
            self.send_otp()
            need_otp = True
            otp_started_at = time.time()
        elif "email-verification" in final_path or "email-otp" in final_path:
            self._print("跳到 OTP 验证阶段 (authorize 已触发 OTP，不再重复发送)")
            # 不调用 send_otp()，因为 authorize 重定向到 email-verification 时服务器已发送 OTP
            need_otp = True
            otp_started_at = time.time()
            otp_seen_message_ids = pre_authorize_message_ids
        elif "about-you" in final_path:
            self._print("跳到填写信息阶段")
            _random_delay(0.5, 1.0)
            self.create_account(name, birthdate)
            _random_delay(0.3, 0.5)
            self.callback()
            return True
        elif "callback" in final_path or "chatgpt.com" in final_url:
            self._print("账号已完成注册")
            return True
        else:
            self._print(f"未知跳转: {final_url}")
            self.register(email, password)
            otp_seen_message_ids = _mail_message_id_set(self._fetch_emails_mail_api(mailbox_ref))
            self.send_otp()
            need_otp = True
            otp_started_at = time.time()

        if need_otp:
            # 使用邮件 API 等待验证码
            otp_code = self.wait_for_verification_email(
                mailbox_ref,
                not_before_ts=otp_started_at,
                exclude_message_ids=otp_seen_message_ids,
            )
            if not otp_code:
                raise Exception("未能获取验证码")

            _random_delay(0.3, 0.8)
            status, data = self.validate_otp(otp_code)
            if status != 200:
                self._print("验证码失败，重试...")
                otp_seen_message_ids = _mail_message_id_set(self._fetch_emails_mail_api(mailbox_ref))
                self.send_otp()
                otp_started_at = time.time()
                _random_delay(1.0, 2.0)
                otp_code = self.wait_for_verification_email(
                    mailbox_ref,
                    timeout=60,
                    not_before_ts=otp_started_at,
                    exclude_message_ids=otp_seen_message_ids,
                )
                if not otp_code:
                    raise Exception("重试后仍未获取验证码")
                _random_delay(0.3, 0.8)
                status, data = self.validate_otp(otp_code)
                if status != 200:
                    raise Exception(f"验证码失败 ({status}): {data}")

        _random_delay(0.5, 1.5)
        status, data = self.create_account(name, birthdate)
        if status != 200:
            raise Exception(f"Create account 失败 ({status}): {data}")
        _random_delay(0.2, 0.5)
        self.callback()
        return True

    def _decode_oauth_session_cookie(self):
        jar = getattr(self.session.cookies, "jar", None)
        if jar is not None:
            cookie_items = list(jar)
        else:
            cookie_items = []

        for c in cookie_items:
            name = getattr(c, "name", "") or ""
            if "oai-client-auth-session" not in name:
                continue

            raw_val = (getattr(c, "value", "") or "").strip()
            if not raw_val:
                continue

            candidates = [raw_val]
            try:
                from urllib.parse import unquote

                decoded = unquote(raw_val)
                if decoded != raw_val:
                    candidates.append(decoded)
            except Exception:
                pass

            for val in candidates:
                try:
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]

                    part = val.split(".")[0] if "." in val else val
                    pad = 4 - len(part) % 4
                    if pad != 4:
                        part += "=" * pad
                    raw = base64.urlsafe_b64decode(part)
                    data = json.loads(raw.decode("utf-8"))
                    if isinstance(data, dict):
                        return data
                except Exception:
                    continue
        return None

    def _oauth_allow_redirect_extract_code(self, url: str, referer: str = None):
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": self.ua,
        }
        if referer:
            headers["Referer"] = referer

        try:
            resp = self.session.get(
                url,
                headers=headers,
                allow_redirects=True,
                timeout=30,
                impersonate=self.impersonate,
            )
            final_url = str(resp.url)
            code = _extract_code_from_url(final_url)
            if code:
                self._print("[OAuth] allow_redirect 命中最终 URL code")
                return code

            for r in getattr(resp, "history", []) or []:
                loc = r.headers.get("Location", "")
                code = _extract_code_from_url(loc)
                if code:
                    self._print("[OAuth] allow_redirect 命中 history Location code")
                    return code
                code = _extract_code_from_url(str(r.url))
                if code:
                    self._print("[OAuth] allow_redirect 命中 history URL code")
                    return code
        except Exception as e:
            maybe_localhost = re.search(r'(https?://localhost[^\s\'\"]+)', str(e))
            if maybe_localhost:
                code = _extract_code_from_url(maybe_localhost.group(1))
                if code:
                    self._print("[OAuth] allow_redirect 从 localhost 异常提取 code")
                    return code
            self._print(f"[OAuth] allow_redirect 异常: {e}")

        return None

    def _oauth_follow_for_code(self, start_url: str, referer: str = None, max_hops: int = 16):
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": self.ua,
        }
        if referer:
            headers["Referer"] = referer

        current_url = start_url
        last_url = start_url

        for hop in range(max_hops):
            try:
                resp = self.session.get(
                    current_url,
                    headers=headers,
                    allow_redirects=False,
                    timeout=30,
                    impersonate=self.impersonate,
                )
            except Exception as e:
                maybe_localhost = re.search(r'(https?://localhost[^\s\'\"]+)', str(e))
                if maybe_localhost:
                    code = _extract_code_from_url(maybe_localhost.group(1))
                    if code:
                        self._print(f"[OAuth] follow[{hop + 1}] 命中 localhost 回调")
                        return code, maybe_localhost.group(1)
                self._print(f"[OAuth] follow[{hop + 1}] 请求异常: {e}")
                return None, last_url

            last_url = str(resp.url)
            self._print(f"[OAuth] follow[{hop + 1}] {resp.status_code} {last_url[:140]}")
            code = _extract_code_from_url(last_url)
            if code:
                return code, last_url

            if resp.status_code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("Location", "")
                if not loc:
                    return None, last_url
                if loc.startswith("/"):
                    loc = f"{OAUTH_ISSUER}{loc}"
                code = _extract_code_from_url(loc)
                if code:
                    return code, loc
                current_url = loc
                headers["Referer"] = last_url
                continue

            return None, last_url

        return None, last_url

    def _oauth_submit_workspace_and_org(self, consent_url: str):
        session_data = self._decode_oauth_session_cookie()
        if not session_data:
            jar = getattr(self.session.cookies, "jar", None)
            if jar is not None:
                cookie_names = [getattr(c, "name", "") for c in list(jar)]
            else:
                cookie_names = list(self.session.cookies.keys())
            self._print(f"[OAuth] 无法解码 oai-client-auth-session, cookies={cookie_names[:12]}")
            return None

        workspaces = session_data.get("workspaces", [])
        if not workspaces:
            self._print("[OAuth] session 中没有 workspace 信息")
            return None

        workspace_id = (workspaces[0] or {}).get("id")
        if not workspace_id:
            self._print("[OAuth] workspace_id 为空")
            return None

        h = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": OAUTH_ISSUER,
            "Referer": consent_url,
            "User-Agent": self.ua,
            "oai-device-id": self.device_id,
        }
        h.update(_make_trace_headers())

        resp = self.session.post(
            f"{OAUTH_ISSUER}/api/accounts/workspace/select",
            json={"workspace_id": workspace_id},
            headers=h,
            allow_redirects=False,
            timeout=30,
            impersonate=self.impersonate,
        )
        self._print(f"[OAuth] workspace/select -> {resp.status_code}")

        if resp.status_code in (301, 302, 303, 307, 308):
            loc = resp.headers.get("Location", "")
            if loc.startswith("/"):
                loc = f"{OAUTH_ISSUER}{loc}"
            code = _extract_code_from_url(loc)
            if code:
                return code
            code, _ = self._oauth_follow_for_code(loc, referer=consent_url)
            if not code:
                code = self._oauth_allow_redirect_extract_code(loc, referer=consent_url)
            return code

        if resp.status_code != 200:
            self._print(f"[OAuth] workspace/select 失败: {resp.status_code}")
            return None

        try:
            ws_data = resp.json()
        except Exception:
            self._print("[OAuth] workspace/select 响应不是 JSON")
            return None

        ws_next = ws_data.get("continue_url", "")
        orgs = ws_data.get("data", {}).get("orgs", [])
        ws_page = (ws_data.get("page") or {}).get("type", "")
        self._print(f"[OAuth] workspace/select page={ws_page or '-'} next={(ws_next or '-')[:140]}")

        org_id = None
        project_id = None
        if orgs:
            org_id = (orgs[0] or {}).get("id")
            projects = (orgs[0] or {}).get("projects", [])
            if projects:
                project_id = (projects[0] or {}).get("id")

        if org_id:
            org_body = {"org_id": org_id}
            if project_id:
                org_body["project_id"] = project_id

            h_org = dict(h)
            if ws_next:
                h_org["Referer"] = ws_next if ws_next.startswith("http") else f"{OAUTH_ISSUER}{ws_next}"

            resp_org = self.session.post(
                f"{OAUTH_ISSUER}/api/accounts/organization/select",
                json=org_body,
                headers=h_org,
                allow_redirects=False,
                timeout=30,
                impersonate=self.impersonate,
            )
            self._print(f"[OAuth] organization/select -> {resp_org.status_code}")
            if resp_org.status_code in (301, 302, 303, 307, 308):
                loc = resp_org.headers.get("Location", "")
                if loc.startswith("/"):
                    loc = f"{OAUTH_ISSUER}{loc}"
                code = _extract_code_from_url(loc)
                if code:
                    return code
                code, _ = self._oauth_follow_for_code(loc, referer=h_org.get("Referer"))
                if not code:
                    code = self._oauth_allow_redirect_extract_code(loc, referer=h_org.get("Referer"))
                return code

            if resp_org.status_code == 200:
                try:
                    org_data = resp_org.json()
                except Exception:
                    self._print("[OAuth] organization/select 响应不是 JSON")
                    return None

                org_next = org_data.get("continue_url", "")
                org_page = (org_data.get("page") or {}).get("type", "")
                self._print(f"[OAuth] organization/select page={org_page or '-'} next={(org_next or '-')[:140]}")
                if org_next:
                    if org_next.startswith("/"):
                        org_next = f"{OAUTH_ISSUER}{org_next}"
                    code, _ = self._oauth_follow_for_code(org_next, referer=h_org.get("Referer"))
                    if not code:
                        code = self._oauth_allow_redirect_extract_code(org_next, referer=h_org.get("Referer"))
                    return code

        if ws_next:
            if ws_next.startswith("/"):
                ws_next = f"{OAUTH_ISSUER}{ws_next}"
            code, _ = self._oauth_follow_for_code(ws_next, referer=consent_url)
            if not code:
                code = self._oauth_allow_redirect_extract_code(ws_next, referer=consent_url)
            return code

        return None

    def perform_codex_oauth_login_http(self, email: str, password: str, mailbox_ref: str = None):
        self._print("[OAuth] 开始执行 Codex OAuth 纯协议流程...")

        # 兼容两种 domain 形式，确保 auth 域也带 oai-did
        self.session.cookies.set("oai-did", self.device_id, domain=".auth.openai.com")
        self.session.cookies.set("oai-did", self.device_id, domain="auth.openai.com")

        code_verifier, code_challenge = _generate_pkce()
        state = secrets.token_urlsafe(24)

        authorize_params = {
            "response_type": "code",
            "client_id": OAUTH_CLIENT_ID,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "scope": "openid profile email offline_access",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
        authorize_url = f"{OAUTH_ISSUER}/oauth/authorize?{urlencode(authorize_params)}"

        def _oauth_json_headers(referer: str):
            h = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": OAUTH_ISSUER,
                "Referer": referer,
                "User-Agent": self.ua,
                "oai-device-id": self.device_id,
            }
            h.update(_make_trace_headers())
            return h

        def _bootstrap_oauth_session():
            self._print("[OAuth] 1/7 GET /oauth/authorize")
            try:
                r = self.session.get(
                    authorize_url,
                    headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Referer": f"{self.BASE}/",
                        "Upgrade-Insecure-Requests": "1",
                        "User-Agent": self.ua,
                    },
                    allow_redirects=True,
                    timeout=30,
                    impersonate=self.impersonate,
                )
            except Exception as e:
                self._print(f"[OAuth] /oauth/authorize 异常: {e}")
                return False, ""

            final_url = str(r.url)
            redirects = len(getattr(r, "history", []) or [])
            self._print(f"[OAuth] /oauth/authorize -> {r.status_code}, final={(final_url or '-')[:140]}, redirects={redirects}")

            has_login = any(getattr(c, "name", "") == "login_session" for c in self.session.cookies)
            self._print(f"[OAuth] login_session: {'已获取' if has_login else '未获取'}")

            if not has_login:
                self._print("[OAuth] 未拿到 login_session，尝试访问 oauth2 auth 入口")
                oauth2_url = f"{OAUTH_ISSUER}/api/oauth/oauth2/auth"
                try:
                    r2 = self.session.get(
                        oauth2_url,
                        headers={
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Referer": authorize_url,
                            "Upgrade-Insecure-Requests": "1",
                            "User-Agent": self.ua,
                        },
                        params=authorize_params,
                        allow_redirects=True,
                        timeout=30,
                        impersonate=self.impersonate,
                    )
                    final_url = str(r2.url)
                    redirects2 = len(getattr(r2, "history", []) or [])
                    self._print(f"[OAuth] /api/oauth/oauth2/auth -> {r2.status_code}, final={(final_url or '-')[:140]}, redirects={redirects2}")
                except Exception as e:
                    self._print(f"[OAuth] /api/oauth/oauth2/auth 异常: {e}")

                has_login = any(getattr(c, "name", "") == "login_session" for c in self.session.cookies)
                self._print(f"[OAuth] login_session(重试): {'已获取' if has_login else '未获取'}")

            return has_login, final_url

        def _post_authorize_continue(referer_url: str):
            sentinel_authorize = build_sentinel_token(
                self.session,
                self.device_id,
                flow="authorize_continue",
                user_agent=self.ua,
                sec_ch_ua=self.sec_ch_ua,
                impersonate=self.impersonate,
            )
            if not sentinel_authorize:
                self._print("[OAuth] authorize_continue 的 sentinel token 获取失败")
                return None

            headers_continue = _oauth_json_headers(referer_url)
            headers_continue["openai-sentinel-token"] = sentinel_authorize

            try:
                return self.session.post(
                    f"{OAUTH_ISSUER}/api/accounts/authorize/continue",
                    json={"username": {"kind": "email", "value": email}},
                    headers=headers_continue,
                    timeout=30,
                    allow_redirects=False,
                    impersonate=self.impersonate,
                )
            except Exception as e:
                self._print(f"[OAuth] authorize/continue 异常: {e}")
                return None

        has_login_session, authorize_final_url = _bootstrap_oauth_session()
        if not authorize_final_url:
            return None

        continue_referer = authorize_final_url if authorize_final_url.startswith(OAUTH_ISSUER) else f"{OAUTH_ISSUER}/log-in"

        self._print("[OAuth] 2/7 POST /api/accounts/authorize/continue")
        resp_continue = _post_authorize_continue(continue_referer)
        if resp_continue is None:
            return None

        self._print(f"[OAuth] /authorize/continue -> {resp_continue.status_code}")
        if resp_continue.status_code == 400 and "invalid_auth_step" in (resp_continue.text or ""):
            self._print("[OAuth] invalid_auth_step，重新 bootstrap 后重试一次")
            has_login_session, authorize_final_url = _bootstrap_oauth_session()
            if not authorize_final_url:
                return None
            continue_referer = authorize_final_url if authorize_final_url.startswith(OAUTH_ISSUER) else f"{OAUTH_ISSUER}/log-in"
            resp_continue = _post_authorize_continue(continue_referer)
            if resp_continue is None:
                return None
            self._print(f"[OAuth] /authorize/continue(重试) -> {resp_continue.status_code}")

        if resp_continue.status_code != 200:
            self._print(f"[OAuth] 邮箱提交失败: {resp_continue.text[:180]}")
            return None

        try:
            continue_data = resp_continue.json()
        except Exception:
            self._print("[OAuth] authorize/continue 响应解析失败")
            return None

        continue_url = continue_data.get("continue_url", "")
        page_type = (continue_data.get("page") or {}).get("type", "")
        self._print(f"[OAuth] continue page={page_type or '-'} next={(continue_url or '-')[:140]}")

        self._print("[OAuth] 3/7 POST /api/accounts/password/verify")
        sentinel_pwd = build_sentinel_token(
            self.session,
            self.device_id,
            flow="password_verify",
            user_agent=self.ua,
            sec_ch_ua=self.sec_ch_ua,
            impersonate=self.impersonate,
        )
        if not sentinel_pwd:
            self._print("[OAuth] password_verify 的 sentinel token 获取失败")
            return None

        headers_verify = _oauth_json_headers(f"{OAUTH_ISSUER}/log-in/password")
        headers_verify["openai-sentinel-token"] = sentinel_pwd

        try:
            resp_verify = self.session.post(
                f"{OAUTH_ISSUER}/api/accounts/password/verify",
                json={"password": password},
                headers=headers_verify,
                timeout=30,
                allow_redirects=False,
                impersonate=self.impersonate,
            )
        except Exception as e:
            self._print(f"[OAuth] password/verify 异常: {e}")
            return None

        self._print(f"[OAuth] /password/verify -> {resp_verify.status_code}")
        if resp_verify.status_code != 200:
            self._print(f"[OAuth] 密码校验失败: {resp_verify.text[:180]}")
            return None

        try:
            verify_data = resp_verify.json()
        except Exception:
            self._print("[OAuth] password/verify 响应解析失败")
            return None

        continue_url = verify_data.get("continue_url", "") or continue_url
        page_type = (verify_data.get("page") or {}).get("type", "") or page_type
        self._print(f"[OAuth] verify page={page_type or '-'} next={(continue_url or '-')[:140]}")

        need_oauth_otp = (
            page_type == "email_otp_verification"
            or "email-verification" in (continue_url or "")
            or "email-otp" in (continue_url or "")
        )

        if need_oauth_otp:
            self._print("[OAuth] 4/7 检测到邮箱 OTP 验证")
            if not mailbox_ref:
                self._print("[OAuth] OAuth 阶段需要邮箱 OTP，但未提供 mailbox_ref")
                return None

            headers_otp = _oauth_json_headers(f"{OAUTH_ISSUER}/email-verification")
            tried_codes = set()
            otp_success = False
            otp_deadline = time.time() + 120
            otp_not_before_ts = time.time()

            while time.time() < otp_deadline and not otp_success:
                messages = _recent_mail_messages(
                    self._fetch_emails_mail_api(mailbox_ref) or [],
                    not_before_ts=otp_not_before_ts,
                )
                candidate_codes = []
                round_seen = set()

                for msg in messages[:12]:
                    code = str(msg.get("verification_code") or "").strip()
                    if (
                        re.fullmatch(r"\d{6}", code)
                        and code != "177010"
                        and code not in tried_codes
                        and code not in round_seen
                    ):
                        candidate_codes.append(code)
                        round_seen.add(code)

                    msg_id = msg.get("id") or msg.get("@id")
                    if not msg_id:
                        continue
                    detail = self._fetch_email_detail_mail_api(mailbox_ref, msg_id)
                    if not detail:
                        continue
                    code = str(detail.get("verification_code") or "").strip()
                    if (
                        re.fullmatch(r"\d{6}", code)
                        and code != "177010"
                        and code not in tried_codes
                        and code not in round_seen
                    ):
                        candidate_codes.append(code)
                        round_seen.add(code)
                        continue

                    content = (
                        detail.get("content")
                        or detail.get("html_content")
                        or detail.get("text")
                        or detail.get("html")
                        or detail.get("preview")
                        or msg.get("preview")
                        or ""
                    )
                    code = self._extract_verification_code(content)
                    if code and code not in tried_codes and code not in round_seen:
                        candidate_codes.append(code)
                        round_seen.add(code)

                if not candidate_codes:
                    elapsed = int(120 - max(0, otp_deadline - time.time()))
                    self._print(f"[OAuth] OTP 等待中... ({elapsed}s/120s)")
                    time.sleep(2)
                    continue

                for otp_code in candidate_codes:
                    tried_codes.add(otp_code)
                    self._print(f"[OAuth] 尝试 OTP: {otp_code}")
                    try:
                        resp_otp = self.session.post(
                            f"{OAUTH_ISSUER}/api/accounts/email-otp/validate",
                            json={"code": otp_code},
                            headers=headers_otp,
                            timeout=30,
                            allow_redirects=False,
                            impersonate=self.impersonate,
                        )
                    except Exception as e:
                        self._print(f"[OAuth] email-otp/validate 异常: {e}")
                        continue

                    self._print(f"[OAuth] /email-otp/validate -> {resp_otp.status_code}")
                    if resp_otp.status_code != 200:
                        self._print(f"[OAuth] OTP 无效，继续尝试下一条: {resp_otp.text[:160]}")
                        continue

                    try:
                        otp_data = resp_otp.json()
                    except Exception:
                        self._print("[OAuth] email-otp/validate 响应解析失败")
                        continue

                    continue_url = otp_data.get("continue_url", "") or continue_url
                    page_type = (otp_data.get("page") or {}).get("type", "") or page_type
                    self._print(f"[OAuth] OTP 验证通过 page={page_type or '-'} next={(continue_url or '-')[:140]}")
                    otp_success = True
                    break

                if not otp_success:
                    time.sleep(2)

            if not otp_success:
                self._print(f"[OAuth] OAuth 阶段 OTP 验证失败，已尝试 {len(tried_codes)} 个验证码")
                return None

        code = None
        consent_url = continue_url
        if consent_url and consent_url.startswith("/"):
            consent_url = f"{OAUTH_ISSUER}{consent_url}"

        if not consent_url and "consent" in page_type:
            consent_url = f"{OAUTH_ISSUER}/sign-in-with-chatgpt/codex/consent"

        if consent_url:
            code = _extract_code_from_url(consent_url)

        if not code and consent_url:
            self._print("[OAuth] 5/7 跟随 continue_url 提取 code")
            code, _ = self._oauth_follow_for_code(consent_url, referer=f"{OAUTH_ISSUER}/log-in/password")

        consent_hint = (
            ("consent" in (consent_url or ""))
            or ("sign-in-with-chatgpt" in (consent_url or ""))
            or ("workspace" in (consent_url or ""))
            or ("organization" in (consent_url or ""))
            or ("consent" in page_type)
            or ("organization" in page_type)
        )

        if not code and consent_hint:
            if not consent_url:
                consent_url = f"{OAUTH_ISSUER}/sign-in-with-chatgpt/codex/consent"
            self._print("[OAuth] 6/7 执行 workspace/org 选择")
            code = self._oauth_submit_workspace_and_org(consent_url)

        if not code:
            fallback_consent = f"{OAUTH_ISSUER}/sign-in-with-chatgpt/codex/consent"
            self._print("[OAuth] 6/7 回退 consent 路径重试")
            code = self._oauth_submit_workspace_and_org(fallback_consent)
            if not code:
                code, _ = self._oauth_follow_for_code(fallback_consent, referer=f"{OAUTH_ISSUER}/log-in/password")

        if not code:
            self._print("[OAuth] 未获取到 authorization code")
            return None

        self._print("[OAuth] 7/7 POST /oauth/token")
        token_resp = self.session.post(
            f"{OAUTH_ISSUER}/oauth/token",
            headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": self.ua},
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": OAUTH_REDIRECT_URI,
                "client_id": OAUTH_CLIENT_ID,
                "code_verifier": code_verifier,
            },
            timeout=60,
            impersonate=self.impersonate,
        )
        self._print(f"[OAuth] /oauth/token -> {token_resp.status_code}")

        if token_resp.status_code != 200:
            self._print(f"[OAuth] token 交换失败: {token_resp.status_code} {token_resp.text[:200]}")
            return None

        try:
            data = token_resp.json()
        except Exception:
            self._print("[OAuth] token 响应解析失败")
            return None

        if not data.get("access_token"):
            self._print("[OAuth] token 响应缺少 access_token")
            return None

        self._print("[OAuth] Codex Token 获取成功")
        return data


# ==================== 并发批量注册 ====================

def _register_one(idx, total, proxy, output_file):
    """单个注册任务 (在线程中运行) - 使用邮件 API 创建邮箱"""
    pool = _get_proxy_pool(fallback_proxy=proxy) if PROXY_ENABLED else None
    last_error = "unknown error"

    for attempt in range(1, PROXY_RETRY_ATTEMPTS_PER_ACCOUNT + 1):
        if _stop_event.is_set():
            return False, None, "已手动停止"
        reg = None
        current_proxy = pool.next_proxy() if pool else None
        proxy_label = current_proxy or "direct"

        try:
            reg = ChatGPTRegister(
                proxy=current_proxy,
                fixed_proxy=current_proxy,
                tag=f"{idx}-try{attempt}",
            )
            reg._print(
                f"[Proxy] 尝试 {attempt}/{PROXY_RETRY_ATTEMPTS_PER_ACCOUNT}: {proxy_label}"
            )

            # 1. 创建邮件地址
            reg._print("[MailAPI] 创建临时邮箱...")
            email, email_pwd, mailbox_ref = reg.create_temp_email()
            tag = email.split("@")[0]
            reg.tag = tag  # 更新 tag

            chatgpt_password = _generate_password()
            name = _random_name()
            birthdate = _random_birthdate()

            with _print_lock:
                print(f"\n{'='*60}")
                print(f"  [{idx}/{total}] 注册: {email}")
                print(f"  ChatGPT密码: {chatgpt_password}")
                print(f"  邮箱凭据: {email_pwd}")
                print(f"  姓名: {name} | 生日: {birthdate}")
                print(f"  代理: {proxy_label}")
                print(f"{'='*60}")

            # 2. 执行注册流程
            reg.run_register(email, chatgpt_password, name, birthdate, mailbox_ref)

            # 3. OAuth（可选）
            oauth_ok = True
            if ENABLE_OAUTH:
                reg._print("[OAuth] 开始获取 Codex Token...")
                tokens = reg.perform_codex_oauth_login_http(email, chatgpt_password, mailbox_ref=mailbox_ref)
                oauth_ok = bool(tokens and tokens.get("access_token"))
                if oauth_ok:
                    _save_codex_tokens(email, tokens)
                    reg._print("[OAuth] Token 已保存")
                    if AUTO_UPLOAD_SUB2API and SUB2API_BASE_URL and tokens.get("refresh_token"):
                        reg._print("[Sub2Api] 正在上传账号...")
                        _push_account_to_sub2api(email, tokens)
                else:
                    msg = "OAuth 获取失败"
                    if OAUTH_REQUIRED:
                        raise Exception(f"{msg}（oauth_required=true）")
                    reg._print(f"[OAuth] {msg}（按配置继续）")

            # 4. 成功后固定此代理（后续优先使用）
            if current_proxy and pool:
                pool.report_success(current_proxy)
                _save_stable_proxy_to_file(current_proxy)
                _save_stable_proxy_to_config(current_proxy)

            # 5. 线程安全写入结果
            with _file_lock:
                with open(output_file, "a", encoding="utf-8") as out:
                    out.write(
                        f"{email}----{chatgpt_password}----{email_pwd}"
                        f"----oauth={'ok' if oauth_ok else 'fail'}----proxy={proxy_label}\n"
                    )

            with _print_lock:
                print(f"\n[OK] [{tag}] {email} 注册成功! 代理: {proxy_label}")
            return True, email, None

        except Exception as e:
            last_error = str(e)
            if current_proxy and pool:
                pool.report_bad(current_proxy, error=e)

            with _print_lock:
                print(
                    f"\n[FAIL] [{idx}] 尝试 {attempt}/{PROXY_RETRY_ATTEMPTS_PER_ACCOUNT} "
                    f"失败: {last_error} | 代理: {proxy_label}"
                )

            if attempt >= PROXY_RETRY_ATTEMPTS_PER_ACCOUNT:
                with _print_lock:
                    traceback.print_exc()
                break

    return False, None, f"代理重试耗尽: {last_error}"


def run_batch(total_accounts: int = 3, output_file="registered_accounts.txt",
              max_workers=3, proxy=None):
    """并发批量注册 - 邮件 API 版"""

    _stop_event.clear()

    if not DUCKMAIL_BEARER:
        print("❌ 错误: 未设置 duckmail_bearer(JWT_TOKEN) 环境变量")
        print("   请设置: export DUCKMAIL_BEARER='your_jwt_token'")
        print("   或: set DUCKMAIL_BEARER=your_jwt_token (Windows)")
        return

    actual_workers = min(max_workers, total_accounts)
    print(f"\n{'#'*60}")
    print(f"  ChatGPT 批量自动注册 (邮件 API 版)")
    print(f"  注册数量: {total_accounts} | 并发数: {actual_workers}")
    print(f"  邮件 API: {DUCKMAIL_API_BASE}")
    if PROXY_ENABLED:
        pool = _get_proxy_pool(fallback_proxy=proxy)
        pool.refresh(force=True)
        proxy_info = pool.info()
        print(f"  代理源: {proxy_info['list_url']}")
        print(f"  优先稳定代理: {'是' if proxy_info['prefer_stable_proxy'] else '否'}")
        print(f"  账号级代理重试: {PROXY_RETRY_ATTEMPTS_PER_ACCOUNT} 次/账号")
        print(f"  代理校验: {'开启' if proxy_info['validate_enabled'] else '关闭'}")
        if proxy_info["validate_enabled"]:
            print(f"  校验目标: {proxy_info['validate_test_url']}")
            print(f"  校验超时: {proxy_info['validate_timeout_seconds']} 秒 | 校验并发: {proxy_info['validate_workers']}")
            print(f"  校验通过: {proxy_info['validated_count']}/{proxy_info['fetched_count']}")
        print(f"  代理池(HTTP/SOCKS): {proxy_info['count']} 个")
        print(f"  代理重试: 单请求最多 {proxy_info['max_retries_per_request']} 次")
        print(f"  失效冷却: {proxy_info['bad_ttl_seconds']} 秒")
        if proxy_info["bad_count"] > 0:
            print(f"  当前冷却代理: {proxy_info['bad_count']} 个")
        if proxy_info["fallback_proxy"]:
            print(f"  兜底代理: {proxy_info['fallback_proxy']}")
        if proxy_info["stable_proxy"]:
            print(f"  稳定代理: {proxy_info['stable_proxy']}")
        print(f"  稳定代理文件: {_stable_proxy_path()}")
        if proxy_info["last_error"]:
            print(f"  代理拉取告警: {proxy_info['last_error'][:200]}")
    else:
        print("  代理: 已关闭，当前以直连模式运行")
    print(f"  OAuth: {'开启' if ENABLE_OAUTH else '关闭'} | required: {'是' if OAUTH_REQUIRED else '否'}")
    if ENABLE_OAUTH:
        print(f"  OAuth Issuer: {OAUTH_ISSUER}")
        print(f"  OAuth Client: {OAUTH_CLIENT_ID}")
        print(f"  Token输出: {TOKEN_JSON_DIR}/, {AK_FILE}, {RK_FILE}")
    print(f"  输出文件: {output_file}")
    print(f"{'#'*60}\n")

    success_count = 0
    fail_count = 0
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=actual_workers) as executor:
        futures = {}
        for idx in range(1, total_accounts + 1):
            future = executor.submit(
                _register_one, idx, total_accounts, proxy, output_file
            )
            futures[future] = idx

        for future in as_completed(futures):
            idx = futures[future]
            try:
                ok, email, err = future.result()
                if ok:
                    success_count += 1
                else:
                    fail_count += 1
                    print(f"  [账号 {idx}] 失败: {err}")
            except Exception as e:
                fail_count += 1
                with _print_lock:
                    print(f"[FAIL] 账号 {idx} 线程异常: {e}")

    elapsed = time.time() - start_time
    avg = elapsed / total_accounts if total_accounts else 0
    print(f"\n{'#'*60}")
    print(f"  注册完成! 耗时 {elapsed:.1f} 秒")
    print(f"  总数: {total_accounts} | 成功: {success_count} | 失败: {fail_count}")
    print(f"  平均速度: {avg:.1f} 秒/个")
    if success_count > 0:
        print(f"  结果文件: {output_file}")
    print(f"{'#'*60}")


def main():
    print("=" * 60)
    print("  ChatGPT 批量自动注册工具 (邮件 API 版)")
    print("=" * 60)

    # 检查邮件 API 配置
    if not DUCKMAIL_BEARER:
        print("\n⚠️  警告: 未设置 duckmail_bearer(JWT_TOKEN)")
        print("   请编辑 config.json 设置 duckmail_bearer，或设置环境变量:")
        print("   Windows: set DUCKMAIL_BEARER=your_jwt_token")
        print("   Linux/Mac: export DUCKMAIL_BEARER='your_jwt_token'")
        print("\n   按 Enter 继续尝试运行 (可能会失败)...")
        input()

    if PROXY_ENABLED:
        env_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") \
                 or os.environ.get("ALL_PROXY") or os.environ.get("all_proxy")
        default_fallback_proxy = _normalize_proxy(DEFAULT_PROXY)
        env_fallback_proxy = _normalize_proxy(env_proxy)
        proxy = default_fallback_proxy or env_fallback_proxy
        proxy_source = "config.json(proxy)" if default_fallback_proxy else (
            "环境变量(HTTPS_PROXY/ALL_PROXY)" if env_fallback_proxy else "未配置"
        )

        print(f"[Info] 代理池地址: {_normalize_proxy_list_url(PROXY_LIST_URL)}")
        print("[Info] 代理模式: 自动拉取 US 列表，使用 http/socks 代理并轮询")
        print(f"[Info] 代理校验: {'开启' if PROXY_VALIDATE_ENABLED else '关闭'} | 目标: {PROXY_VALIDATE_TEST_URL}")
        print(f"[Info] 优先稳定代理开关: {'开启' if PREFER_STABLE_PROXY else '关闭'}")
        print(f"[Info] 账号失败自动换代理重试: {PROXY_RETRY_ATTEMPTS_PER_ACCOUNT} 次")
        if proxy:
            print(f"[Info] 兜底代理来源: {proxy_source} -> {proxy}")
        else:
            print("[Info] 未配置兜底代理，远端列表为空时将直连")
    else:
        proxy = None
        print("[Info] 代理模式: 已关闭，忽略 config 与环境变量代理")

    # 输入注册数量
    count_input = input(f"\n注册账号数量 (默认 {DEFAULT_TOTAL_ACCOUNTS}): ").strip()
    total_accounts = int(count_input) if count_input.isdigit() and int(count_input) > 0 else DEFAULT_TOTAL_ACCOUNTS

    workers_input = input("并发数 (默认 3): ").strip()
    max_workers = int(workers_input) if workers_input.isdigit() and int(workers_input) > 0 else 3

    run_batch(total_accounts=total_accounts, output_file=DEFAULT_OUTPUT_FILE,
              max_workers=max_workers, proxy=proxy)


if __name__ == "__main__":
    main()
