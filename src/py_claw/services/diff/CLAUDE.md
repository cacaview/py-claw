[根目录(../../../../CLAUDE.md) > [src](../../../CLAUDE.md) > [py_claw](../../CLAUDE.md) > [services](../CLAUDE.md) > **diff**

# diff

## 模块职责

`diff/` 提供结构化 diff 生成服务，基于 LCS（最长公共子序列）算法计算文件差异并生成格式化 hunks。镜像 TypeScript 参考实现 `ClaudeCode-main/src/utils/diff.ts`。

## 入口与启动

- 主入口：`__init__.py`
- 主函数：`structured_patch()`、`get_patch_from_contents()`

## 对外接口

### 核心函数

- `structured_patch(old_fname, new_fname, old_text, new_text, ignore_whitespace, context, timeout)` — 计算两个文本之间的结构化补丁
- `get_patch_from_contents(file_path, old_content, new_content, ignore_whitespace, single_hunk)` — 从文件内容计算差异
- `count_lines_changed(patch, new_file_content)` — 统计补丁的添加/删除行数
- `adjust_hunk_line_numbers(hunks, offset)` — 调整 hunk 行号偏移

### 数据结构

- `StructuredPatch` — 完整补丁，包含 hunks 列表
- `StructuredPatchHunk` — 单个 hunk，含 oldStart/oldLines/newStart/newLines/lines

### 常量

- `CONTEXT_LINES = 3` — 默认上下文行数
- `DIFF_TIMEOUT_MS = 5000` — diff 超时毫秒数

## 关键依赖与配置

- 纯 Python 实现，无外部依赖
- 使用 `@dataclass(slots=True)` 优化内存

## 测试与质量

- 22 个测试覆盖核心场景（dataclass、结构、常量、get_patch_from_contents、count_lines_changed、adjust_hunk_line_numbers、structured_patch）
- 所有测试通过

## 相关文件清单

- `__init__.py` — 主实现（StructuredPatch、StructuredPatchHunk、structured_patch、get_patch_from_contents、count_lines_changed、adjust_hunk_line_numbers）

## 变更记录 (Changelog)

- 2026-04-13：实现 M9 功能，结构化 diff 服务完成
