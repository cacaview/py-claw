# TUI 调试工作流

> 适用于 `py-claw --tui` / `src/py_claw/ui/` 的交互调试、回归验证与自动化测试编写。

## 目标

这份工作流解决三个问题：

1. **先确认问题是测试写错，还是 TUI 真有 bug**
2. **把黑盒交互调试、最小探针脚本、pytest 回归三层分开**
3. **在 Claude Code 会话里，稳定复用同一套排查顺序**

---

## 分层调试策略

### 第 1 层：最小黑盒验证

先验证“用户操作后，界面有没有按预期变化”。

适用场景：
- 某个快捷键没反应
- overlay 打不开/关不掉
- suggestion 看起来出现了，但导航不生效
- 焦点看起来不对

优先观察：
- 输入框内容是否变化
- `PromptFooter` 是否进入 suggestion 状态
- overlay 是否真的 mount 到 app
- `selected_index` / `has_suggestions` / `_active_overlay` 是否变化

### 第 2 层：最小探针脚本

当黑盒现象确认后，用一个临时 `python - <<'PY'` 脚本验证 widget 内部状态。

适用场景：
- 要区分“按键没到 widget”还是“状态更新了但 UI 没同步”
- 要确认 `PromptInput.selected_index`、`PromptFooter.selected_index` 是否脱节
- 要确认 `on_input_change -> engine.get_suggestions -> screen.set_suggestion_items` 这条链是否完整

建议打印：
- `len(prompt.suggestion_items)`
- `prompt.selected_index`
- `footer.selected_index`
- `footer.has_suggestions`
- `screen._active_overlay`

### 第 3 层：pytest 回归测试

只有在第 1、2 层确认行为后，再把它固化成测试。

适用场景：
- 已经确认是稳定行为
- 修复后要防回归
- 想补 `todo.md` 里提到的 Prompt suggestion UX / overlay / 焦点恢复 测试

原则：
- **先探针，后测试**
- 不要在行为还没搞清时直接堆集成测试
- 测试 fixture 要尽量贴近 `src/py_claw/ui/textual_app.py` 的真实链路

---

## 推荐排查顺序

### A. 先确认真实行为

对于任一 TUI bug，按下面顺序：

1. **复现用户路径**
   - 例如：输入 `/`、按 `Down`、按 `Esc`
2. **确认输入状态**
   - `prompt.suggestion_items` 是否非空
3. **确认 UI 同步状态**
   - `footer.has_suggestions`
   - `footer.selected_index`
4. **确认跨 widget 消息是否同步**
   - `PromptInput.selected_index` 改了没有
   - `REPLScreen.on_message()` 有没有把状态同步到 footer
5. **再决定修代码还是修测试**

---

## 已验证有效的调试手段

### 1. 用最小探针脚本检查 suggestion 状态

适合排查：
- `/` 后 suggestion 是否出现
- `Down` 是否真的改变了 `PromptInput.selected_index`
- `Esc` 是否真的清掉 suggestion

示例：

```python
python - <<'PY'
import asyncio
from textual.app import App, ComposeResult
from py_claw.ui.screens.repl import REPLScreen
from py_claw.ui.typeahead import CommandItem, SuggestionEngine
from py_claw.ui.textual_app import _format_prompt_hint

commands = [
    CommandItem(name='help', description='Show help', kind='local'),
    CommandItem(name='commit', description='Commit changes', kind='local'),
    CommandItem(name='config', description='Edit config', kind='local'),
]
engine = SuggestionEngine(command_items=commands, max_results=10)

class A(App):
    def compose(self) -> ComposeResult:
        def on_change(text: str):
            s = self.query_one(REPLScreen)
            s.set_prompt_hint(_format_prompt_hint(text, engine))
            s.set_suggestion_items(engine.get_suggestions(text, len(text)))
        yield REPLScreen(on_input_change=on_change, suggestion_engine=engine, command_items=commands)

async def main():
    app = A()
    async with app.run_test() as pilot:
        screen = app.query_one(REPLScreen)
        prompt = screen.query_one('#repl-prompt-input')
        footer = screen.query_one('#repl-footer')

        screen.focus_prompt()
        await pilot.press('/')
        await pilot.pause()
        print('suggestions', len(prompt.suggestion_items), 'footer_has', footer.has_suggestions)

        await pilot.press('down')
        await pilot.pause()
        print('prompt.selected_index', prompt.selected_index)
        print('footer.selected_index', footer.selected_index)

        await pilot.press('escape')
        await pilot.pause()
        print('footer.has_suggestions', footer.has_suggestions)

asyncio.run(main())
PY
```

如果结果类似：

- `prompt.selected_index` 变了
- 但 `footer.selected_index` 没变

说明问题通常在：
- `PromptInput -> REPLScreen` 的消息传播
- 或 `REPLScreen.on_message()` 的同步逻辑

### 2. overlay 调试看 app，不要只看 screen

overlay 多数是 `self.app.mount(dialog)`，不是 mount 在 `REPLScreen` 子树里。

所以测试和调试时：

- 错误方式：`screen.query(DialogClass)`
- 正确方式：`pilot.app.query(DialogClass)`

适用对象：
- `HelpMenuDialog`
- `HistorySearchDialog`
- `QuickOpenDialog`
- `ModelPickerDialog`
- `TasksPanel`

### 3. fixture 必须接近真实 `PyClawApp`

如果测试壳没有接上这条链：

- `on_input_change`
- `_format_prompt_hint(...)`
- `engine.get_suggestions(...)`
- `screen.set_suggestion_items(...)`

那么所有 Prompt suggestion UX 集成测试都会变成假失败。

最低要求：

```python
def _handle_input_change(self, text: str) -> None:
    self._screen().set_prompt_hint(_format_prompt_hint(text, suggestion_engine))
    items = suggestion_engine.get_suggestions(text, len(text))
    self._screen().set_suggestion_items(items)
```

---

## 当前已发现的真实问题

### 1. `ui.dialogs` 包初始化过重

现象：打开某个 overlay 时，`ui/dialogs/__init__.py` eager import 其它 dialog，导致某个弱依赖缺失时整个 overlay 系统一起炸。

处理原则：
- `ui/dialogs/__init__.py` 保持轻量
- 不要在包级别 eager import 全部 dialog

### 2. Prompt suggestion 导航状态可能只更新了 `PromptInput`，没同步到 `PromptFooter`

现象：
- `/` 后 suggestion 出现
- `Down` 后 `PromptInput.selected_index` 改变
- 但 `PromptFooter.selected_index` 不变
- `Esc` 后 footer 仍保持 `has_suggestions=True`

下一步应重点检查：
- `PromptInput.watch_selected_index()`
- `PromptInput.post_message(...)`
- `REPLScreen.on_message()` 对 `PromptInput.SuggestionIndexChanged` 的路由
- 清空 suggestion 时 footer 是否同步更新

### 3. `ListItem` 重名 ID 导致 `QuickOpenDialog` / `TasksPanel` mount 失败

现象：多个 ListItem 使用相同 `item_id`（如路径相同的文件），`_sanitize_item_id` 生成的 widget id 重复，Textual 抛出 `DuplicateIds` 异常。

已修复：`ListItem` 增加 `item_index` 参数，`_sanitize_item_id` 在 `index` 不为 `None` 时追加 `-{index}` 后缀；`quick_open.py` 和 `tasks_panel.py` 调用时传入 `item_index=i`。

调试建议：若 `DuplicateIds` 仍出现，检查是否有其他 dialog 使用相同 `item_id` 生成逻辑。

---

## pytest 编写约定

### 1. 先写稳定断言，再写细节断言

优先级：
1. 状态是否变化
2. 对应 widget 是否 mount/display
3. 文本渲染内容

例如 suggestion 测试优先断言：
- `len(prompt.suggestion_items) > 0`
- `footer.has_suggestions is True`
- `footer.selected_index == ...`

不要一开始就只盯着 renderable 文本。

### 2. Textual Pilot 的输入方式

当前环境下 `Pilot` 没有 `paste()`，统一用逐键 `press()` helper：

```python
async def type_text(pilot, text: str) -> None:
    for ch in text:
        key = 'space' if ch == ' ' else ch
        await pilot.press(key)
```

### 3. overlay 断言要留 `pause()`

打开或关闭 overlay 后，建议：

```python
await pilot.press('ctrl+r')
await pilot.pause()
```

否则容易把尚未完成的 mount/unmount 当成失败。

---

## 推荐的回归覆盖范围

### Prompt suggestion UX

至少覆盖：
- `/` 显示 command suggestions
- `/he + Tab` 接受最佳建议
- bare `#` 进入 channel suggestion
- bare `@` 进入 agent suggestion
- `fix /he` 进入 mid-input slash suggestion
- `Down / Up / PageUp / PageDown / Esc` 的状态变化
- footer 是唯一 suggestion 展示面

### overlay

至少覆盖：
- `?` 打开 help
- `Ctrl+R` 打开 history search
- `Ctrl+P` 打开 quick open
- `Ctrl+M` 打开 model picker
- `Ctrl+T` 打开 tasks panel
- `Esc` 关闭 overlay
- 已有 overlay 打开时，不重复打开第二个 overlay

---

## 继续工作时的默认流程

后续继续 TUI 工作时，默认按这个顺序：

1. 先复现现象
2. 用最小探针脚本打印 widget 内部状态
3. 修真实 bug
4. 再补 pytest 回归
5. 最后更新 `todo.md` / `src/py_claw/ui/CLAUDE.md`

这样可以避免：
- 在错误 fixture 上写很多假失败测试
- 把 overlay mount 位置判断错
- 把 Textual 事件分发问题误当成 suggestion engine 问题
