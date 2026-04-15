# services/secure_storage

## 模块职责

`services/secure_storage/` 实现平台特定的安全存储，对应 TypeScript `ClaudeCode-main/src/utils/secureStorage/`。

## 子模块

- `secure_storage.py` — 抽象接口和明文存储实现
- `keychain_helpers.py` — macOS Keychain 辅助函数

## 关键类

### SecureStorage

抽象接口，包含方法：
- `get(key)` — 获取值
- `set(key, value)` — 设置值
- `delete(key)` — 删除值
- `exists(key)` — 检查键是否存在

### PlainTextStorage

不安全存储实现（作为 fallback），**仅用于没有安全存储的平台**。

### MacOsKeychainStorage

macOS Keychain 存储实现。

## 关键函数

- `get_secure_storage()` — 获取当前平台的最佳存储实现
- `create_fallback_storage()` — 创建带有 fallback 的存储

## 平台支持

- **macOS**: 使用 Keychain（通过 `security` 命令）
- **Linux**: 回退到明文存储（TODO: 添加 libsecret 支持）
- **Windows**: 回退到明文存储

## 测试

- `tests/test_services_secure_storage.py` — 安全存储测试

## 变更记录

- 2026-04-14：新增 `services/secure_storage/` 模块，实现 U16 功能
