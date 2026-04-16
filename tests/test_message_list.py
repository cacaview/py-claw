import pytest
from datetime import datetime
from textual.app import App, ComposeResult
from py_claw.ui.screens.repl import REPLScreen
from py_claw.ui.widgets.messages import MessageList, MessageItem, MessageRole

class TestApp(App):
    def compose(self) -> ComposeResult:
        screen = REPLScreen(id='repl-screen')
        screen._model = 'claude-3-5-sonnet-20241022'
        yield screen

@pytest.mark.asyncio
async def test_message_list_operations():
    app = TestApp()
    async with app.run_test() as pilot:
        repl = app.query_one('#repl-screen')
        log = app.query_one('#repl-message-log', MessageList)
        
        # Test appending messages
        log.add_message(MessageItem(MessageRole.USER, 'Hello world', timestamp=datetime.now()))
        log.add_message(MessageItem(MessageRole.ASSISTANT, 'I am here', timestamp=datetime.now()))
        
        await pilot.pause()
        assert len(log._messages) == 2
        
        # Test update last message
        log.update_last_message('\nHow can I help?', True)
        assert log._messages[-1].content == 'I am here\nHow can I help?'
        
        # Test tool progress
        repl.append_tool_progress('ls', 1.25)
        assert len(log._messages) == 3
        assert log._messages[-1].role == MessageRole.TOOL
        assert log._messages[-1].tool_name == 'ls'
        
        # Test error
        repl.append_error('System error here')
        assert len(log._messages) == 4
        assert log._messages[-1].role == MessageRole.SYSTEM
        
        # Test clear
        repl.clear_log()
        assert len(log._messages) == 0