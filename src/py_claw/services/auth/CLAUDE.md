# services/auth

## 模块职责

`services/auth/` 实现认证相关的工具函数，对应 TypeScript `ClaudeCode-main/src/utils/auth.ts`。主要职责包括：

- OAuth token 管理、缓存与刷新
- API key 获取与缓存（SWR 语义）
- 认证状态查询（订阅者类型、API key 来源）
- 云提供商认证辅助（AWS、GCP）
- 组织验证

## 核心功能

### Token 管理

- `get_claude_ai_oauth_tokens()` - 从安全存储获取 OAuth tokens
- `save_oauth_tokens_if_needed()` - 保存 tokens 到安全存储
- `clear_oauth_token_cache()` - 清除所有 token 缓存
- `handle_oauth_401_error()` - 处理 401 错误并刷新 token
- `check_and_refresh_oauth_token_if_needed()` - 检查过期并按需刷新

### API Key 管理

- `get_anthropic_api_key()` - 获取 Anthropic API key
- `get_anthropic_api_key_with_source()` - 获取 API key 及其来源
- `get_configured_api_key_helper()` - 获取配置的 apiKeyHelper
- `get_api_key_from_api_key_helper_cached()` - 同步缓存读取
- `clear_api_key_helper_cache()` - 清除 API key helper 缓存
- `save_api_key()` / `remove_api_key()` - 保存/删除 API key

### 认证状态

- `is_anthropic_auth_enabled()` - 是否启用 1P Anthropic 认证
- `get_auth_token_source()` - 获取 token 来源
- `has_anthropic_api_key_auth()` - 是否有 API key 认证
- `is_claude_ai_subscriber()` - 是否为 Claude.ai 订阅者
- `has_profile_scope()` - OAuth token 是否有 user:profile scope
- `is_1p_api_customer()` - 是否为 1P API 客户

### 订阅者类型

- `get_subscription_type()` - 获取订阅类型 (max/pro/enterprise/team)
- `is_max_subscriber()` / `is_pro_subscriber()` / `is_enterprise_subscriber()` / `is_team_subscriber()`
- `is_team_premium_subscriber()` - Team + premium tier
- `is_consumer_subscriber()` - Max 或 Pro 订阅者
- `get_subscription_name()` - 人类可读的订阅名称
- `has_opus_access()` - 是否有 Opus 模型访问权限

### 云提供商认证

- `refresh_and_get_aws_credentials()` - 刷新并获取 AWS 凭证
- `clear_aws_credentials_cache()` - 清除 AWS 凭证缓存
- `prefetch_aws_credentials_if_safe()` - 安全地预取 AWS 凭证
- `refresh_gcp_credentials_if_needed()` - 按需刷新 GCP 凭证
- `clear_gcp_credentials_cache()` - 清除 GCP 凭证缓存
- `prefetch_gcp_credentials_if_safe()` - 安全地预取 GCP 凭证

### OTel Headers

- `get_otel_headers_from_helper()` - 从配置的 helper 获取 OTel headers

### 组织验证

- `validate_force_login_org()` - 验证 OAuth token 属于所需组织

### 账户信息

- `get_account_information()` - 获取账户信息（订阅、token 来源、API key 来源、组织、邮箱）
- `get_oauth_account_info()` - 获取 OAuth 账户信息
- `is_overage_provisioning_allowed()` - 是否允许额外用量购买

## 类型

- `ApiKeySource` - API key 来源枚举
- `AuthTokenSource` - Auth token 来源枚举
- `UserAccountInfo` - 用户账户信息 dataclass
- `OrgValidationResult` - 组织验证结果 dataclass
- `AwsCredentials` - AWS 凭证 dataclass

## 关键设计

### SWR 语义

API key helper 使用 Stale-While-Revalidate 语义：
- 返回缓存值如果新鲜
- 返回过期值同时在后台刷新
- 去重并发请求

### 安全检查

来自项目或本地设置的 helper 命令（apiKeyHelper、awsAuthRefresh、gcpAuthRefresh）在执行前需要检查工作区信任。

### 跨进程失效

OAuth token 缓存在另一个进程写入新 token 时会失效，通过检查 `.credentials.json` 的 mtime 实现。

### 401 处理去重

多个并发请求使用同一个过期 token 触发 401 时，只有一个会真正刷新 token，其他等待结果。

## 平台考虑

- macOS: 支持 Keychain 存储
- Linux/Windows: 回退到明文存储或配置文件
- Bare mode: API-key-only，不使用 OAuth

## 相关文件

- `auth.py` - 主实现
- `__init__.py` - 导出
- `tests/test_services_auth.py` - 测试
