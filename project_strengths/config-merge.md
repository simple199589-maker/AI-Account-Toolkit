# 配置合并

## 目标

把 `GPT-team/config.yaml` 和 `GPT_register+duckmail+CPA+autouploadsub2api/config.json` 里真正用到的配置收敛成一份更短的模板。

## 精简原则

- 只保留当前代码实际会读、并且日常确实需要改的项。
- OAuth 固定参数、代理高级调优参数、部分输出细节一律回退到代码默认值，不再放进精简模板。
- 同类能力统一命名，避免同一件事在两个项目里两套字段名。

## 合并后的结构

- `mail`：合并 `temp_mail.*` 和 `duckmail_*`
- `proxy`：保留开关、兜底代理、代理池地址、基础校验开关
- `oauth`：只保留功能开关
- `upload.cpa`：保留 CPA 上报核心配置
- `upload.sub2api`：保留 Sub2Api 上报和池管理核心配置
- `team`：保留母号列表和邀请跟踪文件
- `output`：保留几个真实会落盘的输出文件

## 字段映射

| 原字段 | 合并后字段 |
| --- | --- |
| `temp_mail.worker_domain` | `mail.base_url` |
| `temp_mail.email_domains` | `mail.domains` |
| `temp_mail.admin_password` | `mail.admin_password` |
| `duckmail_api_base` | `mail.base_url` |
| `duckmail_bearer` | `mail.bearer` |
| `proxy.http` / `proxy` | `proxy.url` |
| `proxy_list_url` | `proxy.pool_url` |
| `proxy_enabled` | `proxy.enabled` |
| `proxy_validate_enabled` | `proxy.validate` |
| `prefer_stable_proxy` | `proxy.prefer_stable` |
| `enable_oauth` | `oauth.enabled` |
| `oauth_required` | `oauth.required` |
| `cli_proxy.api_base` | `upload.cpa.api_base` |
| `cli_proxy.password` | `upload.cpa.password` |
| `cli_proxy.upload_enabled` | `upload.cpa.enabled` |
| `sub2api.base_url` / `sub2api_base_url` | `upload.sub2api.base_url` |
| `sub2api.bearer` / `sub2api_bearer` | `upload.sub2api.bearer` |
| `sub2api.email` / `sub2api_email` | `upload.sub2api.email` |
| `sub2api.password` / `sub2api_password` | `upload.sub2api.password` |
| `sub2api.group_ids` / `sub2api_group_ids` | `upload.sub2api.group_ids` |
| `auto_upload_sub2api` / `sub2api.auto_upload_sub2api` | `upload.sub2api.enabled` |
| `teams` | `team.mothers` |
| `output.accounts_file` | `output.accounts_file` |
| `output.results_file` | `output.results_file` |
| `output_file` | `output.registered_file` |
| `token_json_dir` | `output.token_dir` |
| `output.invite_tracker_file` | `team.invite_tracker_file` |

## 被省略的配置

这些不是没用，而是已经压回“高级配置”，日常先不放进精简模板：

- `cli_proxy.management_url`
- `oauth_issuer`
- `oauth_client_id`
- `oauth_redirect_uri`
- `ak_file`
- `rk_file`
- `duckmail_use_proxy`
- `proxy_list_enabled`
- `proxy_validate_timeout_seconds`
- `proxy_validate_workers`
- `proxy_validate_test_url`
- `proxy_max_retries_per_request`
- `proxy_bad_ttl_seconds`
- `proxy_retry_attempts_per_account`
- `stable_proxy_file`
- `stable_proxy`
- `sub2api_min_candidates`

## 建议

- 后面如果你真要统一代码配置，建议以这份 YAML 为主，不再同时维护 YAML 和 JSON 两套命名。
- 第一阶段先统一字段名和目录结构，不急着把高级代理参数并进来。
- 第二阶段如果需要，再加一个 `advanced` 区块承接代理调优项。
