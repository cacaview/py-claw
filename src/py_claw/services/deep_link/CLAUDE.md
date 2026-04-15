# services/deep_link

## 模块职责

`services/deep_link/` 实现 deep link URI 解析和处理，对应 TypeScript `ClaudeCode-main/src/utils/deepLink/`。

## 子模块

- `parse_deep_link.py` — URI 解析
- `register_protocol.py` — 协议注册

## 关键类

### DeepLinkAction

```python
@dataclass
class DeepLinkAction:
    query: str | None  # 预填充提示
    cwd: str | None    # 工作目录
    repo: str | None   # GitHub owner/repo slug
```

## 关键函数

### parse_deep_link.py

- `parse_deep_link(uri)` — 解析 `claude-cli://open` URI
- `build_deep_link(action)` — 构建 deep link URL
- `_contains_control_chars()` — 检测控制字符
- `_partially_sanitize_unicode()` — 去除隐藏 Unicode 字符

### register_protocol.py

- `register_deep_link_protocol()` — 注册为协议处理器
- `unregister_deep_link_protocol()` — 取消注册

## 安全特性

- 参数长度限制（query 5000 字符，cwd 4096 字符）
- ASCII 控制字符检测
- Unicode 脱敏（去除零宽字符、BOM）
- 路径遍历防护

## 平台支持

- **macOS**: 使用 Launch Services
- **Windows**: 使用注册表
- **Linux**: 使用 .desktop 文件

## 测试

- `tests/test_services_deep_link.py` — Deep link 功能测试

## 变更记录

- 2026-04-14：新增 `services/deep_link/` 模块，实现 U17 功能
