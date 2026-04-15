[根目录(../../../CLAUDE.md) > [src](../../CLAUDE.md) > [py_claw](../CLAUDE.md) > **services/doctor**

# services/doctor

## 模块职责

`services/doctor/` 是 Doctor 诊断服务模块，为 Claude Code 提供系统诊断功能。

基于 TypeScript 参考树 `ClaudeCode-main/src/utils/doctorDiagnostic.ts` 和 `doctorContextWarnings.ts` 实现。

## 入口与启动

- 模块导出：`services/doctor/__init__.py`
- 主服务函数：`run_diagnostics()`, `get_diagnostic_summary()`

## 对外接口

### 类型 (types.py)

- `InstallationType` — 安装类型枚举 (npm-global, npm-local, native, package-manager, development, unknown)
- `DiagnosticInfo` — 系统诊断信息
- `RipgrepStatus` — Ripgrep 状态
- `ContextWarning` — 上下文警告
- `ContextWarnings` — 上下文警告集合
- `DoctorCheckResult` — 单个检查结果

### 服务函数 (service.py)

- `run_diagnostics()` — 运行所有诊断检查
- `get_diagnostic_summary()` — 获取诊断摘要字符串
- `get_installation_info()` — 获取安装信息
- `check_context_warnings()` — 检查上下文相关警告
- `check_mcp_servers()` — 检查 MCP 服务器状态

## 诊断检查项目

1. **Python 版本** — 检查 Python 版本是否支持
2. **平台** — 检查操作系统兼容性
3. **API 密钥** — 检查 ANTHROPIC_API_KEY 是否设置
4. **Git** — 检查 git 是否安装
5. **Shell** — 检查可用 shell
6. **配置目录** — 检查 ~/.claude 目录
7. **设置文件** — 检查 settings.json 文件
8. **Ripgrep** — 检查 ripgrep 是否可用
9. **包管理器** — 检查 brew/pip/npm/yarn

## 数据模型

### DoctorCheckResult

```python
@dataclass
class DoctorCheckResult:
    name: str           # 检查名称
    status: str         # 'ok' | 'warning' | 'error' | 'pending'
    message: str        # 状态消息
    details: list[str]  # 详细信息
```

### ContextWarning

```python
@dataclass
class ContextWarning:
    type: str           # 'claudemd_files' | 'agent_descriptions' | 'mcp_tools' | 'unreachable_rules'
    severity: str      # 'warning' | 'error'
    message: str        # 警告消息
    details: list[str] # 详细信息
    current_value: int
    threshold: int
```

## 测试与质量

- `tests/test_doctor_service.py` — Doctor 服务测试

## 变更记录 (Changelog)

- 2026-04-13：新增 `services/doctor/` 模块，实现 M8 功能（Doctor 诊断服务）
