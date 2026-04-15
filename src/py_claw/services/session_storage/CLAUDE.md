[根目录(../../../../CLAUDE.md) > [src](../../../CLAUDE.md) > [py_claw](../../CLAUDE.md) > [services](../CLAUDE.md) > **session_storage**

# services/session_storage

## 模块职责

`services/session_storage/` 实现会话持久化和检索功能，对应 TypeScript 参考树 `ClaudeCode-main/src/utils/sessionStorage.ts` 和 `sessionStoragePortable.ts`。

主要功能：
- 会话文件路径管理（projects 目录、会话 transcripts）
- 快速元数据提取（head/tail 读取，无需完整解析）
- JSON 字段提取（正则匹配，无完整 JSON 解析）
- 会话搜索（按标题、标签、首 prompt 搜索）
- 会话文件 I/O（JSONL 读写）

## 子模块

- `common.py` — 可移植工具函数（路径管理、清理、快速字段提取）
- `storage.py` — 会话存储引擎（文件 I/O、元数据缓存）
- `search.py` — 会话搜索功能

## 关键常量

```python
LITE_READ_BUF_SIZE = 65536  # Head/tail 读取缓冲区大小
MAX_SANITIZED_LENGTH = 200   # 路径组件最大长度
SKIP_PRECOMPACT_THRESHOLD = 5 * 1024 * 1024  # 预压缩过滤阈值
```

## 关键函数

### common.py

- `validate_uuid(maybe_uuid) -> str | None` — UUID 验证
- `unescape_json_string(raw) -> str` — JSON 字符串反转义
- `extract_json_string_field(text, key) -> str | None` — 从文本提取 JSON 字段
- `extract_last_json_string_field(text, key) -> str | None` — 提取最后一个匹配的字段
- `extract_first_prompt_from_head(head) -> str` — 从 head 提取首个用户 prompt
- `read_head_and_tail(file_path, file_size, buf) -> tuple[str, str]` — 读取文件首尾
- `read_session_lite(file_path) -> LiteSessionFile | None` — 快速读取会话文件元数据
- `sanitize_path(name) -> str` — 路径名安全化
- `get_projects_dir() -> str` — 获取 projects 目录
- `get_project_dir(project_dir) -> str` — 获取项目目录
- `find_project_dir(project_path) -> str | None` — 查找项目目录
- `resolve_session_file_path(session_id, dir_path) -> CanonicalizedSessionFile | None` — 解析会话文件路径

### storage.py

- `SessionStorageEngine.set_session(session_id, project_dir)` — 设置当前会话
- `SessionStorageEngine.get_session_file() -> str | None` — 获取会话文件路径
- `SessionStorageEngine.append_entry(entry)` — 追加条目到会话文件
- `SessionStorageEngine.load_session_lite() -> LiteSessionFile | None` — 加载轻量级会话元数据
- `SessionStorageEngine.extract_metadata() -> SessionMetadata | None` — 提取会话元数据
- `get_session_storage_engine() -> SessionStorageEngine` — 获取全局引擎实例

### search.py

- `search_sessions(project_path, query, limit, offset) -> list[SessionSearchResult]` — 搜索会话
- `get_session_info(session_id, project_path) -> SessionSearchResult | None` — 获取特定会话信息
- `list_session_files(project_path, limit) -> list[str]` — 列出会话文件

## 数据类型

### LiteSessionFile
```python
@dataclass(frozen=True, slots=True)
class LiteSessionFile:
    mtime: float      # 修改时间
    size: int       # 文件大小
    head: str       # 文件头部内容
    tail: str       # 文件尾部内容
```

### SessionMetadata
```python
@dataclass(frozen=True, slots=True)
class SessionMetadata:
    session_id: str
    custom_title: str | None = None
    tag: str | None = None
    agent_name: str | None = None
    agent_color: str | None = None
    first_prompt: str | None = None
    created_at: float | None = None
    modified_at: float | None = None
```

### SessionSearchResult
```python
@dataclass(frozen=True, slots=True)
class SessionSearchResult:
    session_id: str
    file_path: str
    project_path: str | None
    custom_title: str | None = None
    tag: str | None = None
    agent_name: str | None = None
    first_prompt: str | None = None
    size: int = 0
    mtime: float = 0.0
```

## 路径结构

```
~/.claude/
└── projects/
    └── <sanitized-project-path>/
        └── <session-id>.jsonl        # 会话 transcript 文件
        └── <session-id>-subagents/
            └── agent-<agent-id>.jsonl  # 子 agent transcript
```

## 会话文件格式

会话文件使用 JSONL 格式，每行一个 JSON 对象：

```jsonl
{"type":"user","uuid":"...","message":{"content":"..."}}
{"type":"assistant","uuid":"...","message":{"content":"..."}}
{"type":"system","subtype":"compact_boundary",...}
{"customTitle":"My Session","tag":"important"}
```

## 与 session_memory 的区别

- `session_storage/` — 低层级会话文件 I/O 和路径管理
- `session_memory/` — 上层会话记忆提取和状态管理

## 相关文件

- 参考：`ClaudeCode-main/src/utils/sessionStorage.ts`
- 参考：`ClaudeCode-main/src/utils/sessionStoragePortable.ts`

## 变更记录 (Changelog)

- 2026-04-13：新增 `session_storage/` 模块，实现会话持久化和检索功能
