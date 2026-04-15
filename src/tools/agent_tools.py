"""
GreenClaw CPU — Agent Tools.

Spawn sub-agents, coordinate multi-agent workflows, and manage agent lifecycles.
OpenClaw-level multi-agent system built in.
"""

import asyncio
import logging
from typing import Any, Optional

from .base import Tool, ToolCategory, ToolResult

logger = logging.getLogger(__name__)


class SubAgentTool(Tool):
    """
    Spawn a sub-agent to handle a specific task in parallel.

    The sub-agent is a complete GreenClaw agent with its own:
    - Model provider (can use different model)
    - Soul/personality
    - Tool set (full access)
    - Memory (isolated or shared)

    Use this for complex tasks that benefit from parallel execution
    or a different personality/model than the main agent.
    """

    name = "spawn_agent"
    description = (
        "Spawn a sub-agent to handle a task in parallel. "
        "The sub-agent is a complete AI agent that can use all tools. "
        "Use for complex research, parallel tasks, different personas, "
        "or delegating work to specialized agents. "
        "Returns the sub-agent's response when complete."
    )
    category = ToolCategory.AGENT
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The task or question to give the sub-agent",
            },
            "model": {
                "type": "string",
                "description": "Model to use for this agent (optional, uses default if empty)",
            },
            "soul": {
                "type": "string",
                "description": "Soul/personality name for the sub-agent (optional)",
            },
            "max_tokens": {
                "type": "integer",
                "description": "Maximum response length (default: 4096)",
            },
            "timeout": {
                "type": "integer",
                "description": "Maximum time in seconds (default: 120, max: 300)",
            },
        },
        "required": ["task"],
    }

    async def execute(
        self,
        task: str,
        model: Optional[str] = None,
        soul: Optional[str] = None,
        max_tokens: int = 4096,
        timeout: int = 120,
    ) -> ToolResult:
        timeout = min(timeout, 300)

        from ..config import get_config
        from ..models.factory import create_provider
        from ..soul.soul_manager import SoulManager
        from ..memory.memory import Memory

        try:
            cfg = get_config()

            # Create provider for sub-agent
            provider = create_provider(
                provider_name=cfg.model.provider,
                model_name=model or cfg.model.name,
                api_key=cfg.model.api_key,
                base_url=cfg.model.base_url,
                ollama_url=cfg.model.ollama_url,
                timeout=min(timeout, 60),
            )

            # Create soul manager
            soul_dir = Path(cfg.soul.soul_dir).expanduser().resolve()
            soul_mgr = SoulManager(
                soul_dir=str(soul_dir),
                active_soul=soul or cfg.soul.active_soul,
            )

            # Create memory
            memory = Memory(enabled=False)  # Sub-agents use ephemeral memory by default

            # Create agent
            from ..agent.agent import Agent
            sub_agent = Agent(
                model_provider=provider,
                soul_manager=soul_mgr,
                memory=memory,
                stream=False,
            )

            # Run the sub-agent task
            logger.info(f"Spawning sub-agent for: {task[:100]}...")
            response = await asyncio.wait_for(
                sub_agent.run(task, stream=False),
                timeout=timeout,
            )

            # Clean up
            await sub_agent.close()

            return ToolResult(
                success=True,
                content=response,
                metadata={
                    "task": task[:100],
                    "model": model or cfg.model.name,
                    "soul": soul or cfg.soul.active_soul,
                },
            )

        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                error=f"Sub-agent timed out after {timeout}s",
            )
        except Exception as e:
            logger.error(f"Sub-agent error: {e}")
            return ToolResult(success=False, error=f"Sub-agent failed: {e}")


class ParallelAgentsTool(Tool):
    """
    Run multiple sub-agents in parallel and aggregate results.

    Great for research tasks where you need multiple perspectives,
    comparing answers, or parallel web searches.
    """

    name = "parallel_agents"
    description = (
        "Run multiple sub-agents simultaneously, each with a different task, "
        "and return all results when complete. "
        "Use for parallel research, comparing different approaches, "
        "or gathering diverse information at once."
    )
    category = ToolCategory.AGENT
    parameters = {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "description": "List of tasks to run in parallel (one per agent)",
                "items": {"type": "string"},
            },
            "model": {
                "type": "string",
                "description": "Model to use for all agents (optional)",
            },
            "max_tokens": {
                "type": "integer",
                "description": "Max tokens per agent (default: 2048)",
            },
            "timeout": {
                "type": "integer",
                "description": "Max time per agent in seconds (default: 60)",
            },
        },
        "required": ["tasks"],
    }

    async def execute(
        self,
        tasks: list[str],
        model: Optional[str] = None,
        max_tokens: int = 2048,
        timeout: int = 60,
    ) -> ToolResult:
        timeout = min(timeout, 120)
        max_tasks = min(len(tasks), 5)  # Limit parallel agents

        if len(tasks) > max_tasks:
            return ToolResult(
                success=False,
                error=f"Too many parallel tasks ({len(tasks)}). Maximum: {max_tasks}",
            )

        async def run_one(task: str, index: int) -> dict:
            try:
                from ..config import get_config
                from ..models.factory import create_provider
                from ..soul.soul_manager import SoulManager
                from ..memory.memory import Memory
                from ..agent.agent import Agent

                cfg = get_config()
                provider = create_provider(
                    cfg.model.provider,
                    model_name=model or cfg.model.name,
                    api_key=cfg.model.api_key,
                    base_url=cfg.model.base_url,
                    ollama_url=cfg.model.ollama_url,
                    timeout=min(timeout, 60),
                )
                soul_mgr = SoulManager(
                    soul_dir=str(Path(cfg.soul.soul_dir).expanduser().resolve()),
                    active_soul=cfg.soul.active_soul,
                )
                memory = Memory(enabled=False)
                agent = Agent(provider, soul_mgr, memory, stream=False)
                result = await asyncio.wait_for(agent.run(task, stream=False), timeout=timeout)
                await agent.close()
                return {"index": index, "task": task[:80], "result": result, "error": None}
            except Exception as e:
                return {"index": index, "task": task[:80], "result": None, "error": str(e)}

        results = await asyncio.gather(*[run_one(t, i) for i, t in enumerate(tasks[:max_tasks])])

        formatted = []
        for r in sorted(results, key=lambda x: x["index"]):
            formatted.append(f"--- Agent {r['index'] + 1} ---\nTask: {r['task']}\nResult: {r['result'] or r['error']}")

        return ToolResult(
            success=True,
            content="\n\n".join(formatted),
            metadata={"tasks_run": len(results), "successes": sum(1 for r in results if r['result'])},
        )


# Import Path for agent tool
from pathlib import Path


def register_agent_tools(registry) -> None:
    """Register agent and spawning tools."""
    registry.register(SubAgentTool())
    registry.register(ParallelAgentsTool())
