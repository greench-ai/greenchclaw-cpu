"""
GreenClaw CPU — Tool System.

A powerful, extensible tool system that gives GreenClaw agency:
- File operations
- Web search & fetch
- Code execution
- Image understanding
- Knowledge base operations
- Sub-agent spawning

Freedom is Key — add any tool you want.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ToolCategory(Enum):
    """Categories for organizing tools."""
    FILE = "file"
    WEB = "web"
    CODE = "code"
    MEDIA = "media"
    KNOWLEDGE = "knowledge"
    AGENT = "agent"
    SYSTEM = "system"


@dataclass
class ToolResult:
    """Result returned by a tool execution."""
    success: bool
    content: Any = None
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "content": self.content,
            "error": self.error,
            "metadata": self.metadata,
        }

    def __str__(self) -> str:
        if not self.success:
            return f"[Tool Error] {self.error}"
        if isinstance(self.content, str):
            return self.content
        try:
            return json.dumps(self.content, indent=2, ensure_ascii=False)
        except Exception:
            return str(self.content)


class Tool(ABC):
    """
    Base class for all GreenClaw tools.

    Tools are the actions GreenClaw can take to accomplish goals.
    Each tool has a name, description, category, and execution logic.

    Tools can be synchronous or async.
    """

    name: str = ""          # Unique identifier, e.g. "file_read"
    description: str = ""   # Human-readable description for the LLM
    category: ToolCategory = ToolCategory.SYSTEM
    parameters: dict = {}   # JSON Schema for parameters (optional)
    examples: list[str] = [] # Example usage strings

    def __init__(self):
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """
        Execute the tool with the given parameters.

        Args:
            **kwargs: Tool-specific parameters.

        Returns:
            ToolResult with success/content/error.
        """
        pass

    def to_json(self) -> dict:
        """Serialize tool metadata for the LLM."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "parameters": self.parameters,
            "examples": self.examples,
        }

    def __repr__(self) -> str:
        return f"<Tool {self.name}>"


def tool(
    name: str,
    description: str,
    category: ToolCategory = ToolCategory.SYSTEM,
    parameters: Optional[dict] = None,
    examples: Optional[list[str]] = None,
) -> Callable:
    """
    Decorator to create a tool from an async function.

    Usage:
        @tool(name="my_tool", description="Does something useful")
        async def my_tool(tool_context, arg1: str, arg2: int = 10) -> ToolResult:
            return ToolResult(success=True, content=f"Did {arg1} {arg2} times")

    The first parameter (after self) should be ToolContext.
    """
    def decorator(func: Callable) -> Tool:
        class FunctionTool(Tool):
            name = name
            description = description
            category = category
            parameters = parameters or {}
            examples = examples or []

            def __init__(self, fn: Callable):
                super().__init__()
                self._fn = fn
                # Extract signature for parameter hints
                import inspect
                sig = inspect.signature(fn)
                self._param_names = [
                    p for p in sig.parameters.keys()
                    if p not in ("self", "tool_context", "context")
                ]

            async def execute(self, **kwargs) -> ToolResult:
                try:
                    # Filter to known params
                    params = {k: v for k, v in kwargs.items() if k in self._param_names}
                    result = await self._fn(**params)
                    if isinstance(result, ToolResult):
                        return result
                    return ToolResult(success=True, content=result)
                except Exception as e:
                    logger.error(f"Tool {self.name} failed: {e}")
                    return ToolResult(success=False, error=str(e))

        class WrappedTool(FunctionTool):
            def __repr__(self):
                return f"<ToolFunction {name}>"

        return WrappedTool(func)

    return decorator


@dataclass
class ToolContext:
    """Context passed to every tool execution."""
    session_id: str = ""
    user_id: str = "default"
    working_dir: str = "."
    env: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.metadata.get(key, default)


class ToolRegistry:
    """
    Registry of all available tools.

    Tools can be registered by name and looked up for execution.
    This is the central hub for GreenClaw's agency.
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._categories: dict[ToolCategory, list[Tool]] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool
        if tool.category not in self._categories:
            self._categories[tool.category] = []
        if tool not in self._categories[tool.category]:
            self._categories[tool.category].append(tool)
        logger.info(f"Registered tool: {tool.name} ({tool.category.value})")

    def register_function(
        self,
        func: Callable,
        name: str,
        description: str,
        category: ToolCategory = ToolCategory.SYSTEM,
    ) -> Tool:
        """Register an async function as a tool."""
        import inspect
        sig = inspect.signature(func)
        param_names = [
            p for p in sig.parameters.keys()
            if p not in ("self", "tool_context", "context")
        ]

        class FunctionTool(Tool):
            name = name
            description = description
            category = category

            def __init__(self, fn):
                super().__init__()
                self._fn = fn
                self._param_names = param_names

            async def execute(self, **kwargs) -> ToolResult:
                try:
                    params = {k: v for k, v in kwargs.items() if k in self._param_names}
                    result = await self._fn(**params)
                    if isinstance(result, ToolResult):
                        return result
                    return ToolResult(success=True, content=result)
                except Exception as e:
                    return ToolResult(success=False, error=str(e))

        tool_instance = FunctionTool(func)
        self.register(tool_instance)
        return tool_instance

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_all(self) -> list[dict]:
        """List all tools as JSON-serializable metadata."""
        return [t.to_json() for t in self._tools.values() if t.enabled]

    def list_by_category(self, category: ToolCategory) -> list[Tool]:
        """List tools in a specific category."""
        return self._categories.get(category, [])

    def get_system_prompt(self) -> str:
        """Generate the system prompt section describing all available tools."""
        tools = self.list_all()
        if not tools:
            return ""

        lines = [
            "\n\n=== AVAILABLE TOOLS ===",
            "You have access to the following tools. Use them to accomplish tasks.\n",
        ]

        for t in tools:
            lines.append(f"**{t['name']}** — {t['description']}")
            if t.get("parameters"):
                params = t["parameters"]
                if "properties" in params:
                    for pname, pdef in params["properties"].items():
                        ptype = pdef.get("type", "any")
                        pdesc = pdef.get("description", "")
                        required = params.get("required", [])
                        req_mark = " (required)" if pname in required else " (optional)"
                        lines.append(f"  - {pname}: {ptype}{req_mark} — {pdesc}")

        lines.append("\nUse tools by outputting a JSON object like:")
        lines.append('```json\n{"tool": "tool_name", "parameters": {"param": "value"}}\n```')

        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"<ToolRegistry {len(self._tools)} tools>"
