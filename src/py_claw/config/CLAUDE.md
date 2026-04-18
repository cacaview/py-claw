[根目录](../../../CLAUDE.md) > [src](../CLAUDE.md) > **config**

# config

## 模块职责

运行时配置的单一来源，从 `~/.config/py-claw/config.json`（XDG Base Directory 规范）读取。无环境变量回退，测试时通过 `PY_CLAW_CONFIG_PATH` 隔离。

## 入口与启动

无独立启动入口；被 `cli/main.py` 在 `_build_state()` 中调用。

## 对外接口

- `load_config(path?: Path) -> Config`：从 JSON 文件加载配置；文件不存在时返回空 `Config`
- `save_config(Config, path?: Path) -> void`：将配置写回 JSON 文件
- `get_config_path() -> Path`：返回默认配置路径
- `PY_CLAW_CONFIG_PATH`：环境变量，覆盖默认配置路径（测试隔离用）

## 配置格式

```json
{
    "api": {
        "api_key": "sk-...",
        "api_url": "https://api.example.com/v1/messages",
        "model": "gpt-5.4"
    }
}
```

`api_url` 和 `model` 必须同时填写才视为已配置。

## 与 CLI 的关系

`cli/main.py::_build_state()` 的 backend 选择逻辑：

```
--sdk-url flag → SdkUrlQueryBackend
config.api.is_configured() → ApiQueryBackend(api_key, api_url, model)
其他情况 → query_backend = None → PlaceholderQueryBackend
```

## 测试隔离

`tests/conftest.py` 设置 `PY_CLAW_CONFIG_PATH` 指向不存在的路径，确保测试不加载用户配置，始终使用 `PlaceholderQueryBackend`。

## 相关文件清单

- `__init__.py`
- `loader.py`

## 变更记录 (Changelog)

- 2026-04-18：简化配置，只保留 `api_key`/`api_url`/`model` 三个字段，移除 `provider`；CLI 统一使用 `ApiQueryBackend`
