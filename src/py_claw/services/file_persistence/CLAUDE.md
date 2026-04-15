# services/file_persistence

## 模块职责

`services/file_persistence/` 实现 BYOC 模式的文件持久化，对应 TypeScript `ClaudeCode-main/src/utils/filePersistence/`。

## 子模块

- `file_persistence.py` — 文件持久化编排逻辑
- `types.py` — 类型定义

## 关键类

### PersistedFile

```python
@dataclass
class PersistedFile:
    filename: str  # 文件路径
    file_id: str   # Files API 返回的文件 ID
```

### FailedPersistence

```python
@dataclass
class FailedPersistence:
    filename: str  # 文件路径
    error: str    # 错误信息
```

### FilesPersistedEventData

```python
@dataclass
class FilesPersistedEventData:
    files: list[PersistedFile]
    failed: list[FailedPersistence]
```

## 关键函数

- `run_file_persistence()` — 执行文件持久化
- `execute_file_persistence()` — 带回调的文件持久化
- `is_file_persistence_enabled()` — 检查是否启用
- `_find_modified_files()` — 扫描修改过的文件

## 常量

- `DEFAULT_UPLOAD_CONCURRENCY = 4` — 默认上传并发数
- `FILE_COUNT_LIMIT = 1000` — 文件数量限制
- `OUTPUTS_SUBDIR = "outputs"` — 输出子目录名

## 环境要求

- `CLAUDE_CODE_ENVIRONMENT_KIND=byoc`
- `CLAUDE_CODE_SESSION_INGRESS_TOKEN`
- `CLAUDE_CODE_REMOTE_SESSION_ID`

## 测试

- `tests/test_services_file_persistence.py` — 文件持久化测试

## 变更记录

- 2026-04-14：新增 `services/file_persistence/` 模块，实现 U18 功能
