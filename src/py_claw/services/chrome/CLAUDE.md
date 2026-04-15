[根目录(../../../../CLAUDE.md) > [src](../../../CLAUDE.md) > [py_claw](../../CLAUDE.md) > [services](../CLAUDE.md) > **chrome**

# services/chrome

## 模块职责

`services/chrome/` 实现 Claude in Chrome 扩展集成，对应 TypeScript 参考树 `ClaudeCode-main/src/utils/claudeInChrome/`。

主要功能：
- Chrome 扩展安装检测
- 浏览器自动检测（Chrome、Brave、Arc、Edge、Chromium、Vivaldi、Opera）
- 跨平台 URL 打开（macOS、Windows、Linux、WSL）
- Claude in Chrome MCP server 配置管理

## 子模块

- `common.py` — 浏览器检测、URL 打开、Native Messaging 配置
- `setup.py` — Chrome 扩展检测、shouldEnableClaudeInChrome 逻辑

## 关键常量

```python
CLAUDE_IN_CHROME_MCP_SERVER_NAME = "claude-in-chrome"
CHROME_EXTENSION_URL = "https://claude.ai/chrome"
CHROME_PERMISSIONS_URL = "https://clau.de/chrome/permissions"
CHROME_RECONNECT_URL = "https://clau.de/chrome/reconnect"
```

## 关键函数

### common.py

- `detect_available_browser() -> ChromiumBrowser | None` — 检测可用的 Chromium 浏览器
- `get_all_browser_data_paths() -> list[tuple[ChromiumBrowser, Path]]` — 获取所有浏览器数据路径
- `open_in_chrome(url: str) -> bool` — 在检测到的浏览器中打开 URL
- `get_platform() -> Literal["macos", "linux", "windows", "wsl"]` — 获取当前平台

### setup.py

- `is_chrome_extension_installed() -> bool` — 检测 Chrome 扩展是否安装
- `should_enable_claude_in_chrome(chrome_flag: bool | None) -> bool` — 判断是否应启用 Chrome 扩展
- `get_chrome_extension_urls() -> dict[str, str]` — 获取扩展管理 URL

## 浏览器支持

| 浏览器 | macOS | Linux | Windows |
|--------|-------|-------|---------|
| Chrome | ✅ | ✅ | ✅ |
| Brave | ✅ | ✅ | ✅ |
| Arc | ✅ | ❌ | ✅ |
| Edge | ✅ | ✅ | ✅ |
| Chromium | ✅ | ✅ | ✅ |
| Vivaldi | ✅ | ✅ | ✅ |
| Opera | ✅ | ✅ | ✅ |

## 相关文件

- 参考：`ClaudeCode-main/src/utils/claudeInChrome/common.ts`
- 参考：`ClaudeCode-main/src/utils/claudeInChrome/setup.ts`
- 命令集成：`commands.py` — `/chrome` 命令 handler

## 变更记录 (Changelog)

- 2026-04-13：新增 `chrome/` 模块，实现 Chrome 扩展集成服务
