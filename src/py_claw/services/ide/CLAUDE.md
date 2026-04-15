[根目录(../../../CLAUDE.md) > [src](../../CLAUDE.md) > [py_claw](../CLAUDE.md) > **services/ide**

# services/ide

## 模块职责

`services/ide/` 是 IDE 集成服务模块，为 Claude Code 提供 IDE 检测、连接管理和扩展安装功能。

基于 TypeScript 参考树 `ClaudeCode-main/src/utils/ide.ts` 实现。

## 入口与启动

- 模块导出：`services/ide/__init__.py`
- 主要服务函数：`detect_ides()`, `find_available_ide()`, `detect_running_ides()`

## 对外接口

### 类型 (types.py)

- `IdeType` — 支持的 IDE 类型枚举 (VS Code, Cursor, JetBrains 等)
- `IdeKind` — IDE 类别 (vscode, jetbrains)
- `IdeConfig` — IDE 配置信息
- `IdeLockfileInfo` — IDE lockfile 解析结果
- `DetectedIDEInfo` — 检测到的 IDE 信息
- `IDEExtensionInstallationStatus` — 扩展安装状态

### 服务函数 (service.py)

- `detect_ides()` — 检测有运行 Claude Code 扩展的 IDE
- `detect_running_ides()` — 检测系统中正在运行的 IDE
- `find_available_ide()` — 查找可用的 IDE（带超时轮询）
- `cleanup_stale_lockfiles()` — 清理过期的 IDE lockfile
- `is_supported_terminal()` — 检查是否在支持的 IDE 终端中运行
- `to_ide_display_name()` — 转换终端标识为显示名称

## 关键依赖与配置

- Lockfile 路径：`~/.claude/ide/*.lock`
- 环境变量：`CLAUDE_CODE_SSE_PORT`, `WSL_DISTRO_NAME`, `CLAUDE_CODE_IDE_HOST_OVERRIDE`
- 支持的 IDE：VS Code, Cursor, Windsurf, JetBrains 全家桶

## 数据模型

### DetectedIDEInfo

```python
@dataclass
class DetectedIDEInfo:
    name: str           # IDE 显示名称
    port: int           # SSE/WebSocket 端口
    workspace_folders: list[str]  # 工作区文件夹
    url: str           # 连接 URL
    is_valid: bool     # 是否与当前 cwd 匹配
    auth_token: str | None
    ide_running_in_windows: bool
```

## 测试与质量

- `tests/test_ide_*.py` — IDE 检测和 lockfile 管理测试

## 变更记录 (Changelog)

- 2026-04-13：新增 `services/ide/` 模块，实现 IDE 检测、lockfile 管理和连接功能
