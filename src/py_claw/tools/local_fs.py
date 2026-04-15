from __future__ import annotations

import fnmatch
import glob as glob_module
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pypdf import PdfReader

from py_claw.tools.base import ToolDefinition, ToolError, ToolPermissionTarget

# ripgrep-compatible type-to-glob mapping
_TYPE_TO_GLOBS: dict[str, list[str]] = {
    "py": ["*.py", "*.pyw", "*.pyx", "*.pyi"],
    "js": ["*.js", "*.jsx", "*.mjs", "*.cjs"],
    "ts": ["*.ts", "*.tsx", "*.mts", "*.cts"],
    "rs": ["*.rs"],
    "go": ["*.go"],
    "java": ["*.java"],
    "c": ["*.h", "*.c"],
    "cpp": ["*.cpp", "*.cc", "*.cxx", "*.hpp", "*.hh", "*.hxx", "*.c++"],
    "rb": ["*.rb", "*.rake", "*.gemspec"],
    "php": ["*.php", "*.phtml", "*.php3", "*.php4", "*.php5"],
    "sh": ["*.sh", "*.bash", "*.dash", "*.ksh", "*.ash"],
    "bash": ["*.bash"],
    "zsh": ["*.zsh"],
    "fish": ["*.fish"],
    "pwsh": ["*.ps1", "*.psm1", "*.psd1"],
    "json": ["*.json", "*.jsonc", "*.jsonl", "*.webmanifest"],
    "yaml": ["*.yaml", "*.yml", "*.yaml.dist", "*.yml.dist"],
    "toml": ["*.toml"],
    "xml": ["*.xml", "*.xsd", "*.xsl", "*.xslt", "*.svg"],
    "html": ["*.html", "*.htm", "*.xhtml"],
    "css": ["*.css", "*.scss", "*.sass", "*.less", "*.styl"],
    "md": ["*.md", "*.markdown", "*.mdown", "*.mkd", "*.mkdn"],
    "txt": ["*.txt"],
    "rst": ["*.rst"],
    "adoc": ["*.adoc", "*.asciidoc"],
    "tex": ["*.tex", "*.sty", "*.cls"],
    "make": ["Makefile", "makefile", "*.mk"],
    "cmake": ["CMakeLists.txt", "*.cmake", "*.cmake.in"],
    "dockerfile": ["Dockerfile", "*.dockerfile", "Containerfile"],
    "vue": ["*.vue"],
    "svelte": ["*.svelte"],
    "elm": ["*.elm"],
    "ex": ["*.ex", "*.exs"],
    "erl": ["*.erl", "*.hrl"],
    "hs": ["*.hs"],
    "scala": ["*.scala", "*.sc"],
    "kt": ["*.kt", "*.kts"],
    "swift": ["*.swift"],
    "objc": ["*.m", "*.mm"],
    "lua": ["*.lua"],
    "r": ["*.r", "*.R", "*.Rmd"],
    "jl": ["*.jl"],
    "clj": ["*.clj", "*.cljs", "*.cljc", "*.edn"],
    "nim": ["*.nim", "*.nims", "*.nimble"],
    "zig": ["*.zig"],
    "v": ["*.v", "*.vh", "*.vo"],
    "sql": ["*.sql"],
    "graphql": ["*.graphql", "*.gql", "*.graphqls"],
    "proto": ["*.proto"],
    "rkt": ["*.rkt"],
    "fs": ["*.fs", "*.fsx", "*.fsscript"],
    "ml": ["*.ml", "*.mli"],
    "vim": ["*.vim", "*.vimrc", "*.gvimrc"],
    "ini": ["*.ini", "*.cfg", "*.conf", "*.config"],
    "properties": ["*.properties"],
    "env": [".env", ".env.*", "*.env"],
    "git": [".gitignore", ".gitattributes", ".gitconfig"],
}


def _type_to_glob_patterns(type_name: str) -> list[str]:
    return _TYPE_TO_GLOBS.get(type_name, [])


class ReadToolInput(BaseModel):
    file_path: str
    offset: int | None = Field(default=None, ge=0)
    limit: int | None = Field(default=None, gt=0)
    pages: str | None = None


class EditToolInput(BaseModel):
    file_path: str
    old_string: str
    new_string: str
    replace_all: bool = False


class WriteToolInput(BaseModel):
    file_path: str
    content: str


class GlobToolInput(BaseModel):
    pattern: str
    path: str | None = None


class GrepToolInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pattern: str
    path: str | None = None
    glob: str | None = None
    output_mode: Literal["content", "files_with_matches", "count"] = "files_with_matches"
    before_context: int | None = Field(default=None, alias="-B")
    after_context: int | None = Field(default=None, alias="-A")
    context_alias: int | None = Field(default=None, alias="-C")
    context: int | None = None
    line_numbers: bool = Field(default=True, alias="-n")
    ignore_case: bool = Field(default=False, alias="-i")
    type: str | None = None
    head_limit: int | None = Field(default=250, ge=0)
    offset: int = Field(default=0, ge=0)
    multiline: bool = False


class NotebookEditToolInput(BaseModel):
    notebook_path: str
    cell_id: str | None = None
    new_source: str = ""
    cell_type: Literal["code", "markdown"] | None = None
    edit_mode: Literal["replace", "insert", "delete"] = "replace"


class ReadTool:
    definition = ToolDefinition(name="Read", input_model=ReadToolInput)

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        raw_value = payload.get("file_path")
        content = str(raw_value) if isinstance(raw_value, str) else None
        return ToolPermissionTarget(tool_name=self.definition.name, content=content)

    def execute(self, arguments: ReadToolInput, *, cwd: str) -> dict[str, object]:
        path = _require_absolute_file(arguments.file_path)
        if arguments.pages is not None:
            return {
                "type": "text",
                "file": {
                    "filePath": str(path),
                    "content": _read_pdf_pages(path, arguments.pages),
                    "numLines": None,
                    "startLine": None,
                    "totalLines": None,
                },
            }
        text = _read_text(path)
        lines = text.splitlines()
        offset = arguments.offset or 0
        selected = lines[offset : offset + arguments.limit] if arguments.limit is not None else lines[offset:]
        start_line = offset + 1 if lines else 1
        return {
            "type": "text",
            "file": {
                "filePath": str(path),
                "content": _number_lines(selected, start=start_line),
                "numLines": len(selected),
                "startLine": start_line,
                "totalLines": len(lines),
            },
        }


class EditTool:
    definition = ToolDefinition(name="Edit", input_model=EditToolInput)

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        raw_value = payload.get("file_path")
        content = str(raw_value) if isinstance(raw_value, str) else None
        return ToolPermissionTarget(tool_name=self.definition.name, content=content)

    def execute(self, arguments: EditToolInput, *, cwd: str) -> dict[str, object]:
        path = _require_absolute_file(arguments.file_path)
        if arguments.old_string == arguments.new_string:
            raise ToolError("No changes to make: old_string and new_string are exactly the same.")
        text = _read_text(path)
        occurrences = text.count(arguments.old_string)
        if occurrences == 0:
            raise ToolError("old_string not found in file")
        if not arguments.replace_all and occurrences > 1:
            raise ToolError("old_string is not unique in the file")
        replacements = occurrences if arguments.replace_all else 1
        updated = text.replace(arguments.old_string, arguments.new_string, replacements)
        path.write_text(updated, encoding="utf-8")
        return {
            "filePath": str(path),
            "content": updated,
            "replacements": replacements,
        }


class WriteTool:
    definition = ToolDefinition(name="Write", input_model=WriteToolInput)

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        raw_value = payload.get("file_path")
        content = str(raw_value) if isinstance(raw_value, str) else None
        return ToolPermissionTarget(tool_name=self.definition.name, content=content)

    def execute(self, arguments: WriteToolInput, *, cwd: str) -> dict[str, object]:
        path = Path(arguments.file_path)
        if not path.is_absolute():
            raise ToolError("file_path must be absolute")
        if not path.parent.exists():
            raise ToolError("Parent directory does not exist")
        original = _read_text(path) if path.exists() else None
        write_type = "update" if path.exists() else "create"
        path.write_text(arguments.content, encoding="utf-8")
        return {
            "type": write_type,
            "filePath": str(path),
            "content": arguments.content,
            "originalFile": original,
        }


class GlobTool:
    definition = ToolDefinition(name="Glob", input_model=GlobToolInput)

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        raw_value = payload.get("pattern")
        content = str(raw_value) if isinstance(raw_value, str) else None
        return ToolPermissionTarget(tool_name=self.definition.name, content=content)

    def execute(self, arguments: GlobToolInput, *, cwd: str) -> dict[str, object]:
        base_path = Path(arguments.path or cwd)
        if not base_path.exists():
            raise ToolError(f"Path does not exist: {base_path}")
        if not base_path.is_dir():
            raise ToolError(f"Path is not a directory: {base_path}")
        pattern = str(base_path / arguments.pattern)
        matches = [Path(match) for match in glob_module.glob(pattern, recursive=True) if Path(match).is_file()]
        matches.sort(key=lambda candidate: candidate.stat().st_mtime, reverse=True)
        filenames = [str(match) for match in matches]
        return {
            "durationMs": 0,
            "numFiles": len(filenames),
            "filenames": filenames,
            "truncated": False,
        }


class GrepTool:
    definition = ToolDefinition(name="Grep", input_model=GrepToolInput)

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        raw_value = payload.get("pattern")
        content = str(raw_value) if isinstance(raw_value, str) else None
        return ToolPermissionTarget(tool_name=self.definition.name, content=content)

    def execute(self, arguments: GrepToolInput, *, cwd: str) -> dict[str, object]:
        search_root = Path(arguments.path or cwd)
        if not search_root.exists():
            raise ToolError(f"Path does not exist: {search_root}")
        files = _grep_candidate_files(search_root, arguments.glob, arguments.type)
        flags = re.MULTILINE
        if arguments.ignore_case:
            flags |= re.IGNORECASE
        if arguments.multiline:
            flags |= re.DOTALL
        pattern = re.compile(arguments.pattern, flags)

        matched_files: list[str] = []
        content_lines: list[str] = []
        total_matches = 0
        context = _resolve_context(arguments)

        for candidate in files:
            try:
                text = candidate.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            if arguments.multiline:
                matches = list(pattern.finditer(text))
                if not matches:
                    continue
                matched_files.append(str(candidate))
                total_matches += len(matches)
                if arguments.output_mode == "content":
                    for match in matches:
                        start_line = text.count("\n", 0, match.start()) + 1
                        snippet = match.group(0)
                        content_lines.append(f"{candidate}:{start_line}:{snippet}")
                continue

            lines = text.splitlines()
            file_matches = 0
            for index, line in enumerate(lines, start=1):
                if not pattern.search(line):
                    continue
                file_matches += 1
                total_matches += 1
                if arguments.output_mode == "content":
                    start = max(1, index - context)
                    end = min(len(lines), index + context)
                    for line_number in range(start, end + 1):
                        rendered = lines[line_number - 1]
                        if arguments.line_numbers:
                            content_lines.append(f"{candidate}:{line_number}:{rendered}")
                        else:
                            content_lines.append(rendered)
            if file_matches:
                matched_files.append(str(candidate))

        limited_files, applied_limit = _apply_limit(matched_files, arguments.head_limit, arguments.offset)
        result: dict[str, object] = {
            "mode": arguments.output_mode,
            "numFiles": len(limited_files),
            "filenames": limited_files,
        }
        if arguments.offset:
            result["appliedOffset"] = arguments.offset
        if applied_limit is not None:
            result["appliedLimit"] = applied_limit
        if arguments.output_mode == "count":
            result["numMatches"] = total_matches
            return result
        if arguments.output_mode == "content":
            limited_content, content_limit = _apply_limit(content_lines, arguments.head_limit, arguments.offset)
            result["content"] = "\n".join(limited_content)
            result["numLines"] = len(limited_content)
            if content_limit is not None:
                result["appliedLimit"] = content_limit
            return result
        return result


class NotebookEditTool:
    definition = ToolDefinition(name="NotebookEdit", input_model=NotebookEditToolInput)

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        raw_value = payload.get("notebook_path")
        content = str(raw_value) if isinstance(raw_value, str) else None
        return ToolPermissionTarget(tool_name=self.definition.name, content=content)

    def execute(self, arguments: NotebookEditToolInput, *, cwd: str) -> dict[str, object]:
        path = _require_absolute_path(arguments.notebook_path)
        if path.suffix != ".ipynb":
            raise ToolError("notebook_path must point to a .ipynb file")
        if not path.exists():
            raise ToolError("Notebook file does not exist")
        if path.is_dir():
            raise ToolError("Path is a directory, not a file")
        notebook = _load_notebook(path)
        language = _notebook_language(notebook)
        edit_mode = arguments.edit_mode
        cell_index = _resolve_notebook_cell_index(notebook, arguments.cell_id, edit_mode)
        original_text = path.read_text(encoding="utf-8")

        if edit_mode == "replace":
            target_cell = notebook["cells"][cell_index]
            if arguments.cell_type is not None:
                target_cell["cell_type"] = arguments.cell_type
            target_cell["source"] = _normalize_notebook_source(arguments.new_source)
            if target_cell.get("cell_type") == "code":
                target_cell["execution_count"] = None
                target_cell["outputs"] = []
            edited_cell_id = _cell_id_for_output(target_cell, fallback_index=cell_index)
            cell_type = str(target_cell.get("cell_type", arguments.cell_type or "code"))
        elif edit_mode == "insert":
            if arguments.cell_type is None:
                raise ToolError("cell_type is required when using edit_mode=insert")
            inserted_cell = _build_notebook_cell(arguments.new_source, arguments.cell_type, notebook)
            notebook["cells"].insert(cell_index, inserted_cell)
            edited_cell_id = _cell_id_for_output(inserted_cell, fallback_index=cell_index)
            cell_type = arguments.cell_type
        else:
            target_cell = notebook["cells"].pop(cell_index)
            edited_cell_id = _cell_id_for_output(target_cell, fallback_index=cell_index)
            cell_type = str(target_cell.get("cell_type", arguments.cell_type or "code"))

        updated_text = json.dumps(notebook, ensure_ascii=False, indent=1) + "\n"
        path.write_text(updated_text, encoding="utf-8")
        return {
            "new_source": arguments.new_source,
            "cell_id": edited_cell_id,
            "cell_type": cell_type,
            "language": language,
            "edit_mode": edit_mode,
            "notebook_path": str(path),
            "original_file": original_text,
            "updated_file": updated_text,
        }


def _require_absolute_file(file_path: str) -> Path:
    path = _require_absolute_path(file_path)
    if not path.exists():
        raise ToolError("File does not exist")
    if path.is_dir():
        raise ToolError("Path is a directory, not a file")
    return path


def _require_absolute_path(file_path: str) -> Path:
    path = Path(file_path)
    if not path.is_absolute():
        raise ToolError("file_path must be absolute")
    return path


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ToolError("Only UTF-8 text files are supported") from exc


def _read_pdf_pages(path: Path, pages: str) -> str:
    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # pragma: no cover - pypdf error types vary by version
        raise ToolError("PDF file could not be read") from exc
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:  # pragma: no cover - pypdf error types vary by version
            raise ToolError("PDF file could not be read") from exc
    page_indexes = _parse_pdf_page_selection(pages, len(reader.pages))
    rendered_pages: list[str] = []
    for page_index in page_indexes:
        try:
            rendered_pages.append(reader.pages[page_index].extract_text() or "")
        except Exception as exc:  # pragma: no cover - pypdf error types vary by version
            raise ToolError("PDF file could not be read") from exc
    return "\n".join(rendered_pages)


def _parse_pdf_page_selection(pages: str, page_count: int) -> list[int]:
    selected: list[int] = []
    seen: set[int] = set()
    for part in pages.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            if not start_text.strip() or not end_text.strip():
                raise ToolError("Invalid PDF page range")
            start = _parse_pdf_page_number(start_text, page_count)
            end = _parse_pdf_page_number(end_text, page_count)
            if end < start:
                raise ToolError("Invalid PDF page range")
            indexes = range(start - 1, end)
        else:
            indexes = [_parse_pdf_page_number(token, page_count) - 1]
        for index in indexes:
            if index not in seen:
                seen.add(index)
                selected.append(index)
    if not selected:
        raise ToolError("PDF page ranges must not be empty")
    return selected


def _parse_pdf_page_number(value: str, page_count: int) -> int:
    try:
        page_number = int(value)
    except ValueError as exc:
        raise ToolError("Invalid PDF page range") from exc
    if page_number < 1 or page_number > page_count:
        raise ToolError("PDF page range is out of bounds")
    return page_number


def _load_notebook(path: Path) -> dict[str, Any]:
    try:
        notebook = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise ToolError("Only UTF-8 text files are supported") from exc
    except json.JSONDecodeError as exc:
        raise ToolError("Notebook is not valid JSON") from exc
    if not isinstance(notebook, dict):
        raise ToolError("Notebook JSON must be an object")
    cells = notebook.get("cells")
    if not isinstance(cells, list):
        raise ToolError("Notebook is missing a valid cells array")
    return notebook


def _resolve_notebook_cell_index(notebook: dict[str, Any], cell_id: str | None, edit_mode: str) -> int:
    cells = notebook["cells"]
    if cell_id is None:
        if edit_mode == "insert":
            return 0
        raise ToolError("cell_id must be specified when not inserting a new cell")
    direct_index = next((index for index, cell in enumerate(cells) if cell.get("id") == cell_id), -1)
    if direct_index != -1:
        return direct_index + 1 if edit_mode == "insert" else direct_index
    parsed_index = _parse_cell_index(cell_id)
    if parsed_index is None:
        raise ToolError(f'Cell with ID "{cell_id}" not found in notebook')
    if edit_mode == "insert":
        if parsed_index >= len(cells):
            raise ToolError(f"Cell with index {parsed_index} does not exist in notebook")
        return parsed_index + 1
    if parsed_index >= len(cells):
        raise ToolError(f"Cell with index {parsed_index} does not exist in notebook")
    return parsed_index


def _parse_cell_index(cell_id: str) -> int | None:
    if cell_id.isdigit():
        return int(cell_id)
    if cell_id.startswith("cell-") and cell_id[5:].isdigit():
        return int(cell_id[5:])
    return None


def _build_notebook_cell(new_source: str, cell_type: Literal["code", "markdown"], notebook: dict[str, Any]) -> dict[str, Any]:
    cell: dict[str, Any] = {
        "cell_type": cell_type,
        "metadata": {},
        "source": _normalize_notebook_source(new_source),
    }
    if _notebook_supports_cell_ids(notebook):
        cell["id"] = uuid.uuid4().hex[:12]
    if cell_type == "code":
        cell["execution_count"] = None
        cell["outputs"] = []
    return cell


def _notebook_supports_cell_ids(notebook: dict[str, Any]) -> bool:
    nbformat = notebook.get("nbformat")
    nbformat_minor = notebook.get("nbformat_minor")
    if not isinstance(nbformat, int):
        return False
    if nbformat > 4:
        return True
    return nbformat == 4 and isinstance(nbformat_minor, int) and nbformat_minor >= 5


def _cell_id_for_output(cell: dict[str, Any], *, fallback_index: int) -> str:
    value = cell.get("id")
    if isinstance(value, str) and value:
        return value
    return f"cell-{fallback_index}"


def _normalize_notebook_source(text: str) -> list[str]:
    return text.splitlines(keepends=True) or [""]


def _notebook_language(notebook: dict[str, Any]) -> str:
    metadata = notebook.get("metadata")
    if not isinstance(metadata, dict):
        return "python"
    language_info = metadata.get("language_info")
    if not isinstance(language_info, dict):
        return "python"
    language = language_info.get("name")
    return language if isinstance(language, str) and language else "python"


def _number_lines(lines: list[str], *, start: int) -> str:
    return "\n".join(f"{line_number:6}\t{line}" for line_number, line in enumerate(lines, start=start))


def _grep_candidate_files(search_root: Path, glob_pattern: str | None, type_: str | None) -> list[Path]:
    if search_root.is_file():
        return [search_root]
    type_globs = _type_to_glob_patterns(type_) if type_ else []
    candidates: list[Path] = []
    for root, dirs, files in os.walk(search_root):
        dirs[:] = [directory for directory in dirs if directory not in {".git", ".hg", ".svn", ".bzr", "__pycache__"}]
        for file_name in files:
            candidate = Path(root) / file_name
            if glob_pattern is not None:
                relative = candidate.relative_to(search_root).as_posix()
                if not fnmatch.fnmatch(relative, glob_pattern) and not fnmatch.fnmatch(file_name, glob_pattern):
                    continue
            if type_:
                basename = candidate.name
                matched = any(fnmatch.fnmatch(basename, g) for g in type_globs)
                if not matched:
                    continue
            candidates.append(candidate)
    return sorted(candidates)


def _resolve_context(arguments: GrepToolInput) -> int:
    if arguments.context is not None:
        return arguments.context
    if arguments.context_alias is not None:
        return arguments.context_alias
    return max(arguments.before_context or 0, arguments.after_context or 0)


def _apply_limit(items: list[str], limit: int | None, offset: int) -> tuple[list[str], int | None]:
    if limit == 0:
        return items[offset:], None
    effective_limit = 250 if limit is None else limit
    sliced = items[offset : offset + effective_limit]
    return sliced, effective_limit if len(items) - offset > effective_limit else None
