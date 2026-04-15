# services/native_installer

## 模块职责

`services/native_installer/` 实现 Claude Code 原生安装器，对应 TypeScript `ClaudeCode-main/src/utils/nativeInstaller/`。

## 子模块

- `installer.py` — 安装、清理和版本管理

## 关键类

### SetupMessage

```python
@dataclass
class SetupMessage:
    type: str    # "info", "success", "warning", "error"
    message: str
```

## 关键函数

- `check_install()` — 检查当前安装状态
- `install_latest()` — 安装最新版本
- `cleanup_old_versions()` — 清理旧版本
- `cleanup_npm_installations()` — 清理旧 npm 安装
- `cleanup_shell_aliases()` — 清理 shell 别名
- `lock_current_version()` — 锁定当前版本
- `remove_installed_symlink()` — 移除已安装的符号链接

## 安装目录

- **Windows**: `%LOCALAPPDATA%\claude-code\`
- **Unix**: `/usr/local/bin/`

## 测试

- `tests/test_services_native_installer.py` — 原生安装器测试

## 变更记录

- 2026-04-14：新增 `services/native_installer/` 模块，实现 U19 功能
