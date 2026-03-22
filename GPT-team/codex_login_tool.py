#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
codex_login_tool.py
===================
共享 Codex 登录工具入口。AI by zb
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib.util
import json
import os
import sys
from typing import Any, Callable, Dict, Optional

import yaml


AUTO_OTP_EMAIL_DOMAIN = "@joini.cloud"


def is_joini_cloud_email(email: str) -> bool:
    """判断邮箱是否属于 joini.cloud 域名。AI by zb"""
    return str(email or "").strip().lower().endswith(AUTO_OTP_EMAIL_DOMAIN)


def resolve_effective_cf_token(email: str, cf_token: str) -> str:
    """按邮箱域名决定是否启用自动 OTP。AI by zb"""
    if not is_joini_cloud_email(email):
        return ""
    return str(cf_token or "").strip()


@dataclass(frozen=True)
class CodexLoginMode:
    """Codex 登录策略常量。AI by zb"""

    GPT_TEAM_WORKSPACE: str = "gpt_team_workspace"
    REGISTER_WORKSPACE: str = "register_workspace"


@dataclass
class CodexProcessResult:
    """Codex 登录后续流程结果。AI by zb"""

    success: bool
    tokens: Optional[Dict[str, Any]] = None
    token_dict: Optional[Dict[str, Any]] = None
    token_file: str = ""
    uploaded_to_sub2api: bool = False


class CodexLoginTool:
    """统一封装两条可复用的 Codex 登录策略。AI by zb"""

    @staticmethod
    def login_with_gpt_team_workspace(
        login_callable: Callable[..., Optional[Dict[str, Any]]],
        *,
        email: str,
        password: str,
        cf_token: str,
        worker_domain: str,
        oauth_issuer: str,
        oauth_client_id: str,
        oauth_redirect_uri: str,
        proxy: str = "",
        logger: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """复用 gpt-team-xianyu 当前的 workspace 模式 Codex 登录。AI by zb"""
        if logger:
            if is_joini_cloud_email(email) and str(cf_token or "").strip():
                logger.info("[CodexTool] joini.cloud 邮箱启用自动 OTP | email=%s", email)
            elif is_joini_cloud_email(email):
                logger.info("[CodexTool] joini.cloud 邮箱缺少自动收码 token，改为手动 OTP | email=%s", email)
            else:
                logger.info("[CodexTool] 非 joini.cloud 邮箱，改为手动 OTP | email=%s", email)
            logger.info("[CodexTool] 使用 gpt_team_workspace 策略 | email=%s", email)
        return login_callable(
            email=email,
            password=password,
            cf_token=resolve_effective_cf_token(email, cf_token),
            worker_domain=worker_domain,
            oauth_issuer=oauth_issuer,
            oauth_client_id=oauth_client_id,
            oauth_redirect_uri=oauth_redirect_uri,
            proxy=proxy,
        )

    @staticmethod
    def login_with_register_workspace(
        login_callable: Callable[..., Optional[Dict[str, Any]]],
        *,
        email: str,
        password: str,
        mailbox_ref: str,
        logger: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """保留 register_workspace 策略入口，后续需要时再接。AI by zb"""
        if logger and hasattr(logger, "info"):
            logger.info("[CodexTool] 使用 register_workspace 策略 | email=%s", email)
        return login_callable(
            email=email,
            password=password,
            mailbox_ref=mailbox_ref,
        )

    @staticmethod
    def dispatch(
        mode: str,
        *,
        gpt_team_callable: Optional[Callable[..., Optional[Dict[str, Any]]]] = None,
        register_callable: Optional[Callable[..., Optional[Dict[str, Any]]]] = None,
        logger: Any = None,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """按策略分发 Codex 登录调用。AI by zb"""
        normalized_mode = str(mode or "").strip().lower()
        if normalized_mode == CodexLoginMode.GPT_TEAM_WORKSPACE:
            if not gpt_team_callable:
                raise ValueError("缺少 gpt_team_workspace 登录函数")
            return CodexLoginTool.login_with_gpt_team_workspace(
                gpt_team_callable,
                logger=logger,
                **kwargs,
            )
        if normalized_mode == CodexLoginMode.REGISTER_WORKSPACE:
            if not register_callable:
                raise ValueError("缺少 register_workspace 登录函数")
            return CodexLoginTool.login_with_register_workspace(
                register_callable,
                logger=logger,
                **kwargs,
            )
        raise ValueError(f"未知 Codex 登录策略: {mode}")

    @staticmethod
    def run_gpt_team_post_invite_flow(
        *,
        mode: str,
        gpt_team_callable: Callable[..., Optional[Dict[str, Any]]],
        email: str,
        password: str,
        cf_token: str,
        worker_domain: str,
        oauth_issuer: str,
        oauth_client_id: str,
        oauth_redirect_uri: str,
        proxy: str = "",
        logger: Any = None,
        attempts: int = 3,
        retry_delay_seconds: int = 5,
        build_token_dict_callable: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
        upload_callable: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
        output_dir: str = "",
    ) -> CodexProcessResult:
        """执行邀请后的 Codex 登录、保存与上报流程。AI by zb"""
        if logger:
            logger.info("🔑 HTTP 登录获取 Codex token | email=%s", email)

        tokens: Optional[Dict[str, Any]] = None
        total_attempts = max(1, int(attempts))
        delay_seconds = max(0, int(retry_delay_seconds))

        for attempt in range(1, total_attempts + 1):
            tokens = CodexLoginTool.dispatch(
                mode,
                gpt_team_callable=gpt_team_callable,
                email=email,
                password=password,
                cf_token=cf_token,
                worker_domain=worker_domain,
                oauth_issuer=oauth_issuer,
                oauth_client_id=oauth_client_id,
                oauth_redirect_uri=oauth_redirect_uri,
                proxy=proxy,
                logger=logger,
            )
            if tokens:
                break
            if logger and attempt < total_attempts:
                logger.warning("⚠️ Codex 登录第 %d 次失败，%ds 后重试... | email=%s", attempt, delay_seconds, email)
            if attempt < total_attempts and delay_seconds > 0:
                import time
                time.sleep(delay_seconds)

        if not tokens:
            if logger:
                logger.warning("❌ Codex 登录失败（注册已成功）| email=%s", email)
            return CodexProcessResult(success=False)

        token_dict = None
        token_file = ""
        if build_token_dict_callable:
            token_dict = build_token_dict_callable(email, tokens)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                token_file = os.path.join(output_dir, f"{email}.json")
                try:
                    with open(token_file, "w", encoding="utf-8") as f:
                        json.dump(token_dict, f, ensure_ascii=False, indent=2)
                    if logger:
                        logger.info("📁 token 已保存本地: %s", token_file)
                except Exception as exc:
                    if logger:
                        logger.warning("本地保存 token 失败: %s", exc)

        uploaded = False
        if upload_callable and str((tokens or {}).get("refresh_token") or "").strip():
            uploaded = bool(upload_callable(email, tokens))
        elif logger:
            logger.info("⏭️ 跳过 Sub2Api 上传（auto_upload_sub2api=false 或配置缺失）| email=%s", email)

        if logger:
            logger.info("🎉 完整流程成功: %s", email)

        return CodexProcessResult(
            success=True,
            tokens=tokens,
            token_dict=token_dict,
            token_file=token_file,
            uploaded_to_sub2api=uploaded,
        )


_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_FILE = os.path.join(_BASE_DIR, "config.yaml")
_XIANYU_FILE = os.path.join(_BASE_DIR, "gpt-team-xianyu.py")


def _load_yaml_config() -> Dict[str, Any]:
    """读取 GPT-team 当前目录配置。AI by zb"""
    if not os.path.exists(_CONFIG_FILE):
        return {}
    with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _resolve_proxy(cli_proxy: str, config: Dict[str, Any]) -> str:
    """解析测试时使用的代理。AI by zb"""
    raw_proxy = str(cli_proxy or "").strip()
    if raw_proxy:
        return raw_proxy
    proxy_cfg = config.get("proxy") or {}
    if isinstance(proxy_cfg, dict):
        return str(proxy_cfg.get("http") or "").strip()
    return ""


def _load_module_from_path(module_path: str, module_name: str):
    """按路径加载 Python 模块。AI by zb"""
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_gpt_team_workspace_test(
    *,
    email: str,
    password: str,
    cf_token: str,
    proxy: str,
) -> int:
    """执行 gpt-team workspace 模式的 Codex 登录测试。AI by zb"""
    config = _load_yaml_config()
    module = _load_module_from_path(_XIANYU_FILE, "gpt_team_xianyu_runtime")

    configured_cf_token = str(cf_token or (config.get("temp_mail") or {}).get("admin_password") or "").strip()
    effective_cf_token = resolve_effective_cf_token(email, configured_cf_token)
    worker_domain = str((config.get("temp_mail") or {}).get("worker_domain") or "").strip()
    effective_proxy = _resolve_proxy(proxy, config)
    otp_mode = "auto" if effective_cf_token else "manual"

    print(f"[CodexTool] 开始测试 | mode={CodexLoginMode.GPT_TEAM_WORKSPACE} | email={email}")
    print(f"[CodexTool] worker_domain={worker_domain or '-'} | proxy={effective_proxy or '-'} | otp_mode={otp_mode}")

    tokens = CodexLoginTool.dispatch(
        CodexLoginMode.GPT_TEAM_WORKSPACE,
        gpt_team_callable=module.perform_http_oauth_login,
        email=email,
        password=password,
        cf_token=configured_cf_token,
        worker_domain=worker_domain,
        oauth_issuer=module.OPENAI_AUTH_BASE,
        oauth_client_id=module.OAUTH_CLIENT_ID,
        oauth_redirect_uri=module.OAUTH_REDIRECT_URI,
        proxy=effective_proxy,
        logger=module.logger,
    )

    if not tokens:
        print("[CodexTool] 测试失败：未获取到 token")
        return 1

    print("[CodexTool] 测试成功，返回字段如下：")
    print(json.dumps(tokens, ensure_ascii=False, indent=2))
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。AI by zb"""
    parser = argparse.ArgumentParser(description="GPT-team Codex 登录测试工具")
    parser.add_argument("--email", required=True, help="已加入工作空间的账号邮箱")
    parser.add_argument("--password", required=True, help="账号密码")
    parser.add_argument("--cf-token", default="", help="邮箱验证码读取 token，不传则默认读取 GPT-team/config.yaml")
    parser.add_argument("--proxy", default="", help="代理地址，不传则默认读取 GPT-team/config.yaml")
    parser.add_argument(
        "--mode",
        default=CodexLoginMode.GPT_TEAM_WORKSPACE,
        choices=[CodexLoginMode.GPT_TEAM_WORKSPACE],
        help="登录策略，当前默认且仅支持 gpt_team_workspace",
    )
    return parser


def main() -> int:
    """命令行入口。AI by zb"""
    parser = _build_arg_parser()
    args = parser.parse_args()
    return _run_gpt_team_workspace_test(
        email=str(args.email).strip(),
        password=str(args.password).strip(),
        cf_token=str(args.cf_token).strip(),
        proxy=str(args.proxy).strip(),
    )


if __name__ == "__main__":
    sys.modules.setdefault("codex_login_tool", sys.modules[__name__])
    raise SystemExit(main())
