from __future__ import annotations

import os
import time
from enum import Enum
from typing import Any

from pydantic import Field

from py_claw.schemas.common import PyClawBaseModel
from py_claw.tools.base import ToolDefinition, ToolPermissionTarget

try:
    from playwright.sync_api import sync_playwright, Browser, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class BrowserAction(str, Enum):
    """Browser actions."""

    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    SCREENSHOT = "screenshot"
    GET_TEXT = "get_text"
    GET_HTML = "get_html"
    WAIT = "wait"
    SCROLL = "scroll"
    EVALUATE = "evaluate"


class WebBrowserToolInput(PyClawBaseModel):
    """Input for WebBrowserTool."""

    action: BrowserAction = Field(description="Browser action to perform")
    url: str | None = Field(default=None, description="URL for navigate action")
    selector: str | None = Field(default=None, description="CSS selector for click/type actions")
    text: str | None = Field(default=None, description="Text to type")
    wait_ms: int = Field(default=1000, ge=0, le=30000, description="Wait time in milliseconds")
    screenshot_path: str | None = Field(default=None, description="Path to save screenshot")


class WebBrowserTool:
    """Tool for browser automation using Playwright.

    Provides full browser automation including navigation, clicking,
    typing, screenshots, and JavaScript evaluation.
    """

    definition = ToolDefinition(name="WebBrowser", input_model=WebBrowserToolInput)

    def __init__(self) -> None:
        self._browser: Browser | None = None
        self._page: Page | None = None
        self._playwright = None

    def _ensure_browser(self) -> tuple[Browser, Page]:
        """Ensure browser is running and return browser/page pair."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "Playwright is not installed. Install it with: pip install playwright && playwright install chromium"
            )

        if self._browser is None or not self._browser.is_connected():
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
            self._page = self._browser.new_page()

        return self._browser, self._page

    def _close_browser(self) -> None:
        """Close browser if open."""
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
            self._page = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        url = payload.get("url", "")
        return ToolPermissionTarget(
            tool_name=self.definition.name,
            content=str(url) if isinstance(url, str) else None,
        )

    def execute(self, arguments: WebBrowserToolInput, *, cwd: str) -> dict[str, object]:
        if not PLAYWRIGHT_AVAILABLE:
            return {
                "error": "playwright_not_installed",
                "message": "Playwright is required for browser automation. Install with: pip install playwright && playwright install chromium",
            }

        action = arguments.action

        try:
            if action == BrowserAction.NAVIGATE:
                return self._navigate(arguments.url, cwd)
            elif action == BrowserAction.SCREENSHOT:
                return self._screenshot(arguments.screenshot_path)
            elif action == BrowserAction.CLICK:
                return self._click(arguments.selector)
            elif action == BrowserAction.TYPE:
                return self._type(arguments.selector, arguments.text)
            elif action == BrowserAction.GET_TEXT:
                return self._get_text(arguments.selector)
            elif action == BrowserAction.GET_HTML:
                return self._get_html(arguments.selector)
            elif action == BrowserAction.WAIT:
                return self._wait(arguments.wait_ms)
            elif action == BrowserAction.SCROLL:
                return self._scroll(arguments.selector)
            elif action == BrowserAction.EVALUATE:
                return self._evaluate(arguments.selector)
            else:
                return {"error": f"Unknown action: {action}"}
        except Exception as e:
            self._close_browser()
            return {"error": str(e), "action": action.value}

    def _navigate(self, url: str | None, cwd: str) -> dict[str, object]:
        """Navigate to a URL."""
        if not url:
            return {"error": "url is required for navigate action"}

        if not url.startswith(("http://", "https://")):
            return {"error": f"Invalid URL scheme: {url}. Must start with http:// or https://"}

        _, page = self._ensure_browser()
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return {
                "action": "navigate",
                "url": url,
                "status": "completed",
                "title": page.title(),
                "final_url": page.url,
                "status_code": response.status if response else None,
            }
        except Exception as e:
            return {"error": f"Navigation failed: {str(e)}", "url": url}

    def _screenshot(self, path: str | None) -> dict[str, object]:
        """Take a screenshot."""
        if not path:
            return {"error": "screenshot_path is required for screenshot action"}

        if self._page is None:
            return {"error": "No page available. Navigate to a URL first."}

        try:
            path = os.path.abspath(path)
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            self._page.screenshot(path=path, full_page=True)
            return {
                "action": "screenshot",
                "path": path,
                "status": "completed",
            }
        except Exception as e:
            return {"error": f"Screenshot failed: {str(e)}", "path": path}

    def _click(self, selector: str | None) -> dict[str, object]:
        """Click an element."""
        if not selector:
            return {"error": "selector is required for click action"}

        if self._page is None:
            return {"error": "No page available. Navigate to a URL first."}

        try:
            self._page.click(selector, timeout=10000)
            return {
                "action": "click",
                "selector": selector,
                "status": "completed",
            }
        except Exception as e:
            return {"error": f"Click failed: {str(e)}", "selector": selector}

    def _type(self, selector: str | None, text: str | None) -> dict[str, object]:
        """Type text into an element."""
        if not selector:
            return {"error": "selector is required for type action"}
        if not text:
            return {"error": "text is required for type action"}

        if self._page is None:
            return {"error": "No page available. Navigate to a URL first."}

        try:
            self._page.fill(selector, text, timeout=10000)
            return {
                "action": "type",
                "selector": selector,
                "text": text,
                "status": "completed",
            }
        except Exception as e:
            return {"error": f"Type failed: {str(e)}", "selector": selector}

    def _get_text(self, selector: str | None) -> dict[str, object]:
        """Get text content of an element."""
        if not selector:
            return {"error": "selector is required for get_text action"}

        if self._page is None:
            return {"error": "No page available. Navigate to a URL first."}

        try:
            element = self._page.wait_for_selector(selector, timeout=10000)
            if element:
                return {
                    "action": "get_text",
                    "selector": selector,
                    "text": element.inner_text(),
                    "status": "completed",
                }
            return {"error": f"Element not found: {selector}", "selector": selector}
        except Exception as e:
            return {"error": f"Get text failed: {str(e)}", "selector": selector}

    def _get_html(self, selector: str | None) -> dict[str, object]:
        """Get HTML content of an element."""
        if not selector:
            return {"error": "selector is required for get_html action"}

        if self._page is None:
            return {"error": "No page available. Navigate to a URL first."}

        try:
            element = self._page.wait_for_selector(selector, timeout=10000)
            if element:
                return {
                    "action": "get_html",
                    "selector": selector,
                    "html": element.inner_html(),
                    "status": "completed",
                }
            return {"error": f"Element not found: {selector}", "selector": selector}
        except Exception as e:
            return {"error": f"Get HTML failed: {str(e)}", "selector": selector}

    def _wait(self, wait_ms: int) -> dict[str, object]:
        """Wait for a specified duration."""
        time.sleep(wait_ms / 1000)

        if self._page:
            self._page.wait_for_timeout(wait_ms)

        return {
            "action": "wait",
            "wait_ms": wait_ms,
            "status": "completed",
        }

    def _scroll(self, selector: str | None) -> dict[str, object]:
        """Scroll to an element or position."""
        if self._page is None:
            return {"error": "No page available. Navigate to a URL first."}

        try:
            if selector:
                element = self._page.wait_for_selector(selector, timeout=10000)
                if element:
                    element.scroll_into_view_if_needed()
                    return {
                        "action": "scroll",
                        "selector": selector,
                        "status": "completed",
                    }
                return {"error": f"Element not found: {selector}", "selector": selector}
            else:
                self._page.evaluate("window.scrollBy(0, window.innerHeight)")
                return {
                    "action": "scroll",
                    "status": "completed",
                    "direction": "down",
                }
        except Exception as e:
            return {"error": f"Scroll failed: {str(e)}"}

    def _evaluate(self, script: str | None) -> dict[str, object]:
        """Evaluate JavaScript in the browser context."""
        if not script:
            return {"error": "script is required for evaluate action"}

        if self._page is None:
            return {"error": "No page available. Navigate to a URL first."}

        try:
            result = self._page.evaluate(script)
            return {
                "action": "evaluate",
                "script": script,
                "result": result,
                "status": "completed",
            }
        except Exception as e:
            return {"error": f"Evaluate failed: {str(e)}", "script": script}
