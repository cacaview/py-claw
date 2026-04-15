# services/model

## 模块职责

`services/model/` 实现模型选择、别名解析和 API provider 检测，对应 TypeScript `ClaudeCode-main/src/utils/model/`。

## 子模块

- `providers.py` — API Provider 检测 (firstParty, Bedrock, Vertex, Foundry)
- `model.py` — 模型选择、别名解析、规范化名称处理

## 关键函数

### providers.py

- `get_api_provider()` — 检测当前 API provider
- `is_first_party_anthropic_base_url()` — 检测是否使用官方 Anthropic API

### model.py

- `get_main_loop_model()` — 获取主循环模型
- `get_default_opus_model()` / `get_default_sonnet_model()` / `get_default_haiku_model()` — 各系列默认模型
- `parse_user_specified_model()` — 解析用户指定的模型输入（含别名、[1m] 后缀）
- `first_party_name_to_canonical()` — 将完整模型名转换为规范简称
- `render_model_name()` / `get_public_model_name()` — 人类可读的模型名称
- `normalize_model_string_for_api()` — 移除 [1m]/[2m] 后缀

## 测试

- `tests/test_services_model.py` — 模型选择和解析测试

## 变更记录

- 2026-04-14：新增 `services/model/` 模块，实现 U11 功能
