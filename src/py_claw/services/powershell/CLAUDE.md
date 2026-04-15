# services/powershell

## 模块职责

`services/powershell/` 实现 PowerShell 命令解析和安全分析，对应 TypeScript `ClaudeCode-main/src/utils/powershell/`。

## 子模块

- `parser.py` — PowerShell AST 解析器
- `dangerous_cmdlets.py` — 危险 cmdlet 列表

## 关键类

### ParsedCommandElement

```python
@dataclass
class ParsedCommandElement:
    name: str           # 命令名
    name_type: str      # 'cmdlet', 'application', 'unknown'
    element_type: str
    args: list[str]
    text: str
    element_types: list[str]
    redirections: list[ParsedRedirection]
```

### ParsedStatement

```python
@dataclass
class ParsedStatement:
    statement_type: str  # 'PipelineAst', 'IfStatementAst', etc.
    commands: list[ParsedCommandElement]
    redirections: list[ParsedRedirection]
    text: str
    nested_commands: list[ParsedCommandElement] | None
    security_patterns: dict[str, bool] | None
```

### ParsedPowerShellCommand

```python
@dataclass
class ParsedPowerShellCommand:
    valid: bool
    statements: list[ParsedStatement]
    variables: list[dict]
    has_stop_parsing: bool
    errors: list[dict]
    original_command: str
```

## 关键函数

### parser.py

- `parse_powershell_command()` — 解析 PowerShell 命令（含缓存）
- `get_all_command_names()` — 提取所有命令名
- `get_file_redirections()` — 提取文件重定向
- `has_directory_change()` — 检测目录变更命令
- `derive_security_flags()` — 推导安全相关标志

### dangerous_cmdlets.py

- `is_dangerous_cmdlet()` — 检查是否为危险 cmdlet
- `is_never_suggest_cmdlet()` — 检查是否应禁用自动补全
- `is_safe_output_cmdlet()` — 检查是否为安全输出 cmdlet
- `is_accept_edits_allowed_cmdlet()` — 检查是否允许接受编辑

## 常量

- `MAX_COMMAND_LENGTH` — Windows 32767 / Unix 4500 字节限制
- `COMMON_ALIASES` — 常见 PowerShell 别名映射

## 危险 cmdlet

- 代码执行：`Invoke-Expression`, `Invoke-Command`, `iex`, `icm`
- 远程会话：`New-PSSession`, `Enter-PSSession`, `Remove-PSSession`
- 进程控制：`Start-Process`, `Stop-Process`, `Start-Job`
- 网络：`Invoke-WebRequest`, `Invoke-RestMethod`

## 测试

- `tests/test_services_powershell.py` — PowerShell 解析测试

## 变更记录

- 2026-04-14：新增 `services/powershell/` 模块，实现 U20 功能
