#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
codex_login_manual_test.py
==========================
固定参数的 Codex 登录手动验证码测试文件。AI by zb
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from typing import Any, Dict, Optional

import requests
import yaml

from sub2api_service import Sub2ApiConfig, Sub2ApiUploader, normalize_group_ids


TEST_EMAIL = "ivy.gonzalez@joini.cloud"
TEST_PASSWORD = "$%4Y8DUmDYsQ5Rpq"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")
XIANYU_FILE = os.path.join(BASE_DIR, "gpt-team-xianyu.py")


def load_config() -> Dict[str, Any]:
    """读取 GPT-team 当前目录配置。AI by zb"""
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def load_xianyu_module():
    """按路径加载 gpt-team-xianyu.py。AI by zb"""
    spec = importlib.util.spec_from_file_location("gpt_team_xianyu_manual_runtime", XIANYU_FILE)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块: {XIANYU_FILE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_token_payload(module, email: str, tokens: Dict[str, Any]) -> Dict[str, Any]:
    """复用 xianyu 的 token 结构生成。AI by zb"""
    return module.build_token_dict(email, tokens)


def upload_to_sub2api(module, email: str, tokens: Dict[str, Any], config: Dict[str, Any]) -> bool:
    """按 GPT-team/config.yaml 配置上传到 Sub2Api。AI by zb"""
    sub2api_cfg = config.get("sub2api") or {}
    base_url = str(sub2api_cfg.get("base_url") or "").strip().rstrip("/")
    if not base_url:
        print("[ManualCodex] 未配置 sub2api.base_url，跳过上传")
        return False

    session = requests.Session()
    uploader = Sub2ApiUploader(
        session,
        Sub2ApiConfig(
            base_url=base_url,
            bearer=str(sub2api_cfg.get("bearer") or "").strip(),
            email=str(sub2api_cfg.get("email") or "").strip(),
            password=str(sub2api_cfg.get("password") or "").strip(),
            group_ids=normalize_group_ids(sub2api_cfg.get("group_ids", [2]), default=[2]),
            client_id=module.OAUTH_CLIENT_ID,
        ),
        module.logger,
    )
    ok = uploader.push_account(email, tokens)
    print(f"[ManualCodex] Sub2Api 上传结果: {'成功' if ok else '失败'}")
    return ok


def perform_http_oauth_login_manual(module, email: str, password: str, proxy: str = "") -> Optional[Dict[str, Any]]:
    """复用 xianyu 的底层能力，OTP 改为手动输入。AI by zb"""
    session = module.create_session(proxy=proxy)
    device_id = str(module.uuid.uuid4())

    session.cookies.set("oai-did", device_id, domain=".auth.openai.com")
    session.cookies.set("oai-did", device_id, domain="auth.openai.com")

    code_verifier, code_challenge = module.generate_pkce()
    state = module.secrets.token_urlsafe(32)

    module.logger.info("[ManualCodex] Step A: authorize | email=%s", email)
    authorize_params = {
        "response_type": "code",
        "client_id": module.OAUTH_CLIENT_ID,
        "redirect_uri": module.OAUTH_REDIRECT_URI,
        "scope": "openid profile email offline_access",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    authorize_url = f"{module.OPENAI_AUTH_BASE}/oauth/authorize?{module.urlencode(authorize_params)}"
    try:
        session.get(
            authorize_url,
            headers=module.NAVIGATE_HEADERS,
            allow_redirects=True,
            verify=False,
            timeout=30,
        )
    except Exception as e:
        module.logger.warning("[ManualCodex] Step A 失败: %s | email=%s", e, email)
        return None

    module.logger.info("[ManualCodex] Step B: 提交邮箱 | email=%s", email)
    headers = dict(module.COMMON_HEADERS)
    headers["referer"] = f"{module.OPENAI_AUTH_BASE}/log-in"
    headers["oai-device-id"] = device_id
    headers.update(module.generate_datadog_trace())

    sentinel_email = module.build_sentinel_token(session, device_id, flow="authorize_continue")
    if not sentinel_email:
        module.logger.warning("[ManualCodex] Step B sentinel 失败 | email=%s", email)
        return None
    headers["openai-sentinel-token"] = sentinel_email

    try:
        resp = session.post(
            f"{module.OPENAI_AUTH_BASE}/api/accounts/authorize/continue",
            json={"username": {"kind": "email", "value": email}},
            headers=headers,
            verify=False,
            timeout=30,
        )
    except Exception as e:
        module.logger.warning("[ManualCodex] Step B 异常: %s | email=%s", e, email)
        return None
    if resp.status_code != 200:
        module.logger.warning("[ManualCodex] Step B 失败: HTTP %s | email=%s", resp.status_code, email)
        return None

    module.logger.info("[ManualCodex] Step C: 提交密码 | email=%s", email)
    headers["referer"] = f"{module.OPENAI_AUTH_BASE}/log-in/password"
    headers.update(module.generate_datadog_trace())

    sentinel_pwd = module.build_sentinel_token(session, device_id, flow="password_verify")
    if not sentinel_pwd:
        module.logger.warning("[ManualCodex] Step C sentinel 失败 | email=%s", email)
        return None
    headers["openai-sentinel-token"] = sentinel_pwd

    try:
        resp = session.post(
            f"{module.OPENAI_AUTH_BASE}/api/accounts/password/verify",
            json={"password": password},
            headers=headers,
            verify=False,
            timeout=30,
            allow_redirects=False,
        )
    except Exception as e:
        module.logger.warning("[ManualCodex] Step C 异常: %s | email=%s", e, email)
        return None
    if resp.status_code != 200:
        module.logger.warning("[ManualCodex] Step C 失败: HTTP %s | email=%s", resp.status_code, email)
        return None

    continue_url = ""
    page_type = ""
    try:
        data = resp.json()
        continue_url = str(data.get("continue_url") or "")
        page_type = str(((data.get("page") or {}).get("type")) or "")
    except Exception:
        pass
    module.logger.info(
        "[ManualCodex] Step C 结果 | continue_url=%s | page_type=%s | email=%s",
        continue_url[:120],
        page_type,
        email,
    )
    if not continue_url:
        module.logger.warning("[ManualCodex] Step C 无 continue_url | email=%s", email)
        return None

    if page_type == "email_otp_verification" or "email-verification" in continue_url:
        module.logger.info("[ManualCodex] Step D: 需要手动输入 OTP | email=%s", email)
        verification_url = continue_url if continue_url.startswith("http") else f"{module.OPENAI_AUTH_BASE}{continue_url}"
        try:
            session.get(
                verification_url,
                headers=module.NAVIGATE_HEADERS,
                verify=False,
                timeout=20,
                allow_redirects=True,
            )
            module.logger.info("[ManualCodex] 打开 email-verification 页面: %s | email=%s", verification_url[:80], email)
        except Exception as e:
            module.logger.warning("[ManualCodex] 打开 email-verification 异常: %s | email=%s", e, email)

        h_val = module.build_auth_json_headers(
            referer=f"{module.OPENAI_AUTH_BASE}/email-verification",
            device_id=device_id,
            include_device_id=False,
        )

        verify_deadline = module.time.time() + 300
        otp_ok = False
        while module.time.time() < verify_deadline:
            otp_code = module.prompt_for_email_otp(
                email=email,
                tag=f"{email}-manual",
                timeout=max(30, int(verify_deadline - module.time.time())),
            )
            if not otp_code:
                return None

            resp_val = session.post(
                f"{module.OPENAI_AUTH_BASE}/api/accounts/email-otp/validate",
                json={"code": otp_code},
                headers=h_val,
                verify=False,
                timeout=30,
            )
            if resp_val.status_code == 200:
                try:
                    d2 = resp_val.json()
                    continue_url = str(d2.get("continue_url") or continue_url)
                    page_type = str(((d2.get("page") or {}).get("type")) or "")
                except Exception:
                    pass
                module.logger.info(
                    "[ManualCodex] OTP验证成功 | continue_url=%s | page_type=%s | email=%s",
                    continue_url[:120],
                    page_type,
                    email,
                )
                otp_ok = True
                break

            module.logger.warning(
                "[ManualCodex] OTP验证失败: HTTP %s | %s",
                resp_val.status_code,
                resp_val.text[:200],
            )

        if not otp_ok:
            module.logger.warning("[ManualCodex] OTP 超时 | email=%s", email)
            return None

    auth_session_data = module.decode_auth_session_cookie(session)
    workspace_id = module.extract_workspace_id(auth_session_data)
    normalized_page_type = str(page_type or "").strip().lower()
    normalized_continue_url = str(continue_url or "").strip().lower()
    explicit_workspace = normalized_page_type == "workspace" or "/workspace" in normalized_continue_url
    about_you_stage = normalized_page_type in {"about_you", "about-you"} or "/about-you" in normalized_continue_url

    if (explicit_workspace or about_you_stage) and not workspace_id:
        auth_session_data, workspace_id = module.ensure_workspace_context(
            session=session,
            oauth_issuer=module.OPENAI_AUTH_BASE,
            email=email,
            log_prefix="[ManualCodex]",
        )

    if explicit_workspace or (workspace_id and about_you_stage):
        continue_url = f"{module.OPENAI_AUTH_BASE}/workspace"
        page_type = "workspace"
        module.logger.info("[ManualCodex] 进入 workspace 阶段 | workspace_id=%s | email=%s", workspace_id or "", email)
        module.time.sleep(2)
    elif about_you_stage:
        module.logger.info("[ManualCodex] 当前仍处于 about-you/onboarding | email=%s", email)

    if "about-you" in continue_url and not workspace_id:
        h_about = dict(module.NAVIGATE_HEADERS)
        h_about["referer"] = f"{module.OPENAI_AUTH_BASE}/email-verification"
        try:
            resp_about = session.get(
                f"{module.OPENAI_AUTH_BASE}/about-you",
                headers=h_about,
                verify=False,
                timeout=30,
                allow_redirects=True,
            )
            module.logger.info(
                "[ManualCodex] about-you 页面加载: HTTP %s | url=%s | email=%s",
                resp_about.status_code,
                str(resp_about.url)[:120],
                email,
            )
        except Exception:
            return None

        if "consent" in str(resp_about.url) or "organization" in str(resp_about.url):
            continue_url = str(resp_about.url)
        else:
            first_name, last_name = module.generate_random_name()
            birthdate = module.generate_random_birthday()
            h_create = dict(module.COMMON_HEADERS)
            h_create["referer"] = f"{module.OPENAI_AUTH_BASE}/about-you"
            h_create["oai-device-id"] = device_id
            h_create.update(module.generate_datadog_trace())
            resp_create = session.post(
                f"{module.OPENAI_AUTH_BASE}/api/accounts/create_account",
                json={"name": f"{first_name} {last_name}", "birthdate": birthdate},
                headers=h_create,
                verify=False,
                timeout=30,
            )
            module.logger.info(
                "[ManualCodex] about-you create_account: HTTP %s | body=%s | email=%s",
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
                continue_url = f"{module.OPENAI_AUTH_BASE}/sign-in-with-chatgpt/codex/consent"

            auth_session_data, workspace_id = module.ensure_workspace_context(
                session=session,
                oauth_issuer=module.OPENAI_AUTH_BASE,
                email=email,
                log_prefix="[ManualCodex]",
                max_attempts=5,
            )
            if workspace_id:
                continue_url = f"{module.OPENAI_AUTH_BASE}/workspace"
                page_type = "workspace"
                module.logger.info("[ManualCodex] about-you 后补拿到 workspace_id=%s | email=%s", workspace_id, email)

    if "consent" in page_type:
        continue_url = f"{module.OPENAI_AUTH_BASE}/sign-in-with-chatgpt/codex/consent"

    if not continue_url or "email-verification" in continue_url:
        module.logger.warning("[ManualCodex] 未能推进到 consent/workspace 阶段 | email=%s", email)
        return None

    if continue_url.startswith("/"):
        consent_url = f"{module.OPENAI_AUTH_BASE}{continue_url}"
    else:
        consent_url = continue_url

    auth_code = None
    try:
        resp_consent = session.get(
            consent_url,
            headers=module.NAVIGATE_HEADERS,
            verify=False,
            timeout=30,
            allow_redirects=False,
        )
        if resp_consent.status_code in (301, 302, 303, 307, 308):
            loc = resp_consent.headers.get("Location", "")
            auth_code = module._extract_code_from_url(loc)
            if not auth_code:
                auth_code = module._follow_and_extract_code(session, loc, module.OPENAI_AUTH_BASE)
        elif resp_consent.status_code == 200:
            html = resp_consent.text
            state_m = module.re.search(r'["\']state["\']:\s*["\']([^"\'\ ]+)["\']', html)
            nonce_m = module.re.search(r'["\']nonce["\']:\s*["\']([^"\'\ ]+)["\']', html)
            consent_payload = {"action": "allow"}
            if state_m:
                consent_payload["state"] = state_m.group(1)
            if nonce_m:
                consent_payload["nonce"] = nonce_m.group(1)
            consent_h = {
                "accept": "application/json, text/plain, */*",
                "content-type": "application/json",
                "origin": module.OPENAI_AUTH_BASE,
                "referer": consent_url,
                "user-agent": module.USER_AGENT,
                "oai-device-id": device_id,
            }
            r_consent_post = session.post(
                consent_url,
                json=consent_payload,
                headers=consent_h,
                verify=False,
                timeout=30,
                allow_redirects=False,
            )
            if r_consent_post.status_code in (301, 302, 303, 307, 308):
                loc2 = r_consent_post.headers.get("Location", "")
                auth_code = module._extract_code_from_url(loc2)
                if not auth_code:
                    consent_url = loc2 if loc2.startswith("http") else f"{module.OPENAI_AUTH_BASE}{loc2}"
            elif r_consent_post.status_code == 200:
                try:
                    cdata = r_consent_post.json()
                    redirect_to = str(cdata.get("redirectTo") or cdata.get("redirect_url") or "")
                    if redirect_to:
                        auth_code = module._extract_code_from_url(redirect_to)
                        if not auth_code:
                            consent_url = redirect_to
                except Exception:
                    pass
        else:
            auth_code = module._extract_code_from_url(str(resp_consent.url))
            if not auth_code:
                auth_code = module._follow_and_extract_code(session, str(resp_consent.url), module.OPENAI_AUTH_BASE)
    except Exception:
        pass

    if not auth_code:
        session_data = module.decode_auth_session_cookie(session)
        workspace_id = module.extract_workspace_id(session_data)
        if session_data:
            module.logger.info("[ManualCodex] auth-session snapshots: %s | email=%s", module.summarize_auth_session_cookies(session), email)

        if workspace_id:
            h_ws = module.build_auth_json_headers(
                referer=consent_url,
                device_id=device_id,
            )
            try:
                resp_ws = session.post(
                    f"{module.OPENAI_AUTH_BASE}/api/accounts/workspace/select",
                    json={"workspace_id": workspace_id},
                    headers=h_ws,
                    verify=False,
                    timeout=30,
                    allow_redirects=False,
                )
                if resp_ws.status_code in (301, 302, 303, 307, 308):
                    loc = resp_ws.headers.get("Location", "")
                    auth_code = module._extract_code_from_url(loc)
                    if not auth_code:
                        auth_code = module._follow_and_extract_code(session, loc, module.OPENAI_AUTH_BASE)
                elif resp_ws.status_code == 200:
                    ws_data = resp_ws.json()
                    ws_next = str(ws_data.get("continue_url") or "")
                    ws_page = str(((ws_data.get("page") or {}).get("type")) or "")
                    if "organization" in ws_next or "organization" in ws_page:
                        org_url = ws_next if ws_next.startswith("http") else f"{module.OPENAI_AUTH_BASE}{ws_next}"
                        org_id = None
                        project_id = None
                        ws_orgs = (ws_data.get("data") or {}).get("orgs", []) if isinstance(ws_data, dict) else []
                        if ws_orgs:
                            org_id = (ws_orgs[0] or {}).get("id")
                            projects = (ws_orgs[0] or {}).get("projects", [])
                            if projects:
                                project_id = (projects[0] or {}).get("id")
                        if org_id:
                            body = {"org_id": org_id}
                            if project_id:
                                body["project_id"] = project_id
                            h_org = module.build_auth_json_headers(
                                referer=org_url,
                                device_id=device_id,
                            )
                            resp_org = session.post(
                                f"{module.OPENAI_AUTH_BASE}/api/accounts/organization/select",
                                json=body,
                                headers=h_org,
                                verify=False,
                                timeout=30,
                                allow_redirects=False,
                            )
                            if resp_org.status_code in (301, 302, 303, 307, 308):
                                loc = resp_org.headers.get("Location", "")
                                auth_code = module._extract_code_from_url(loc)
                                if not auth_code:
                                    auth_code = module._follow_and_extract_code(session, loc, module.OPENAI_AUTH_BASE)
                            elif resp_org.status_code == 200:
                                org_data = resp_org.json()
                                org_next = str(org_data.get("continue_url") or "")
                                if org_next:
                                    full_next = org_next if org_next.startswith("http") else f"{module.OPENAI_AUTH_BASE}{org_next}"
                                    auth_code = module._follow_and_extract_code(session, full_next, module.OPENAI_AUTH_BASE)
                        else:
                            auth_code = module._follow_and_extract_code(session, org_url, module.OPENAI_AUTH_BASE)
                    else:
                        if ws_next:
                            full_next = ws_next if ws_next.startswith("http") else f"{module.OPENAI_AUTH_BASE}{ws_next}"
                            auth_code = module._follow_and_extract_code(session, full_next, module.OPENAI_AUTH_BASE)
            except Exception:
                pass

    if not auth_code:
        try:
            resp_fallback = session.get(
                consent_url,
                headers=module.NAVIGATE_HEADERS,
                verify=False,
                timeout=30,
                allow_redirects=True,
            )
            auth_code = module._extract_code_from_url(str(resp_fallback.url))
            if not auth_code and resp_fallback.history:
                for hist in resp_fallback.history:
                    loc = hist.headers.get("Location", "")
                    auth_code = module._extract_code_from_url(loc)
                    if auth_code:
                        break
        except Exception:
            pass

    if not auth_code:
        module.logger.warning("[ManualCodex] 未能获取 auth_code | email=%s", email)
        return None

    return module._exchange_code_for_token(
        auth_code,
        code_verifier,
        oauth_issuer=module.OPENAI_AUTH_BASE,
        oauth_client_id=module.OAUTH_CLIENT_ID,
        oauth_redirect_uri=module.OAUTH_REDIRECT_URI,
        proxy=proxy,
    )


def main() -> int:
    """命令行入口。AI by zb"""
    config = load_config()
    module = load_xianyu_module()
    proxy_cfg = config.get("proxy") or {}
    proxy = str(proxy_cfg.get("http") or "").strip() if isinstance(proxy_cfg, dict) else ""

    print(f"[ManualCodex] 开始测试 | email={TEST_EMAIL}")
    print(f"[ManualCodex] proxy={proxy or '-'}")

    tokens = perform_http_oauth_login_manual(
        module=module,
        email=TEST_EMAIL,
        password=TEST_PASSWORD,
        proxy=proxy,
    )
    if not tokens:
        print("[ManualCodex] 测试失败：未获取到 token")
        return 1

    print("[ManualCodex] 测试成功，返回字段如下：")
    print(json.dumps(tokens, ensure_ascii=False, indent=2))
    token_payload = build_token_payload(module, TEST_EMAIL, tokens)
    output_dir = os.path.join(BASE_DIR, "output_tokens")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{TEST_EMAIL}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(token_payload, f, ensure_ascii=False, indent=2)
    print(f"[ManualCodex] 本地已保存: {output_file}")
    upload_to_sub2api(module, TEST_EMAIL, tokens, config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
