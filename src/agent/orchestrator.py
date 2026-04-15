"""
GreenClaw CPU — Agent Orchestrator.

The brain that coordinates models, tools, souls, memory, and knowledge bases
into a fully autonomous AI agent that can use tools and spawn sub-agents.

Features:
- ReAct pattern (Reason → Act → Observe → Respond)
- Tool use with streaming
- Knowledge base integration (RAG)
- Multi-agent spawning
- Real-time streaming to WebSocket clients

MIT License — GreenClaw Team
"""

import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ─── ReAct constants ────────────────────────────────────────────────────────────

MAX_TOOL_CALLS = 10        # Max tool calls per message
MAX_STREAM_CHUNK = 500     # Max chars per streaming chunk


class GreenClawOrchestrator:
    """
    The main orchestrator that gives GreenClaw agency.

    Uses the ReAct pattern:
    1. Think about what to do
    2. Use tools if needed
    3. Observe results
    4. Formulate response

    Integrates with:
    - ModelProvider (for LLM calls)
    - ToolRegistry (for tool execution)
    - SoulManager (for personality)
    - Memory (for conversation history)
    - KnowledgeBase (for RAG)
    - WebSocket (for streaming to clients)
    """

    def __init__(
        self,
        model_provider,
        soul_manager,
        memory,
        tool_registry=None,
        knowledge_base=None,
        stream: bool = True,
        max_tool_calls: int = MAX_TOOL_CALLS,
    ):
        self.model = model_provider
        self.soul = soul_manager
        self.memory = memory
        self.tools = tool_registry
        self.kb = knowledge_base
        self.stream = stream
        self.max_tool_calls = max_tool_calls

        # WebSocket send function (set by server)
        self._ws_sender: Optional[Callable] = None
        self._session_id: str = ""

    def set_websocket(self, sender: Callable, session_id: str = ""):
        """Set the WebSocket sender for streaming."""
        self._ws_sender = sender
        self._session_id = session_id

    async def _send_ws(self, event_type: str, data: Any):
        """Send an event to the WebSocket client."""
        if self._ws_sender:
            try:
                await self._ws_sender({"type": event_type, **data})
            except Exception as e:
                logger.debug(f"WebSocket send failed: {e}")

    # ─── Tool use ────────────────────────────────────────────────────────────

    def _extract_tool_calls(self, text: str) -> list[tuple[str, dict]]:
        """
        Extract tool calls from model response text.

        Looks for JSON blocks like: {"tool": "name", "parameters": {...}}
        """
        tool_calls = []

        # Find all JSON blocks
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        for match in re.finditer(json_pattern, text):
            try:
                obj = json.loads(match.group())
                if "tool" in obj and "parameters" in obj:
                    name = obj["tool"].strip()
                    params = obj.get("parameters", {})
                    if name and isinstance(params, dict):
                        tool_calls.append((name, params))
                        continue
                # Also accept "tool_name" + "args" pattern
                if "tool_name" in obj or "tool_name" in str(obj).lower():
                    name = obj.get("tool_name") or obj.get("toolName") or ""
                    args = obj.get("args") or obj.get("arguments") or obj.get("parameters", {})
                    if name:
                        tool_calls.append((name, args if isinstance(args, dict) else {}))
            except json.JSONDecodeError:
                continue

        return tool_calls

    async def _execute_tool(self, tool_name: str, parameters: dict) -> str:
        """
        Execute a tool and return its result as a string.

        Handles tool not found, execution errors, and results.
        """
        if not self.tools:
            return f"[Error] No tools available."

        tool = self.tools.get(tool_name)
        if not tool:
            available = ", ".join(t.name for t in self.tools.list_all())
            return f"[Error] Unknown tool: '{tool_name}'. Available tools: {available}"

        try:
            result = await tool.execute(**parameters)

            if result.success:
                content = result.content
                if isinstance(content, str):
                    # Truncate long results
                    if len(content) > 3000:
                        content = content[:3000] + f"\n\n… [truncated, {len(content)} total chars]"
                else:
                    content = json.dumps(content, indent=2, ensure_ascii=False)
                    if len(content) > 3000:
                        content = content[:3000] + "\n\n… [truncated]"
                return content
            else:
                return f"[Tool Error] {result.error}"

        except Exception as e:
            logger.error(f"Tool '{tool_name}' raised: {e}")
            return f"[Tool Error] {e}"

    # ─── Knowledge base ──────────────────────────────────────────────────────

    async def _rag_query(self, query: str, top_k: int = 5) -> str:
        """
        Query the knowledge base for relevant context.

        If the query seems like a search/information request and KB has relevant docs,
        inject relevant chunks into context.
        """
        if not self.kb:
            return ""

        try:
            results = await self.kb.search(query, top_k=top_k)
            if not results:
                return ""

            context_parts = ["[KNOWLEDGE BASE RESULTS]"]
            for i, r in enumerate(results, 1):
                context_parts.append(
                    f"\n--- Result {i} ({r['doc_name']}, similarity: {r['similarity']}) ---\n"
                    f"{r['text']}"
                )
            return "\n".join(context_parts)

        except Exception as e:
            logger.debug(f"RAG query failed: {e}")
            return ""

    # ─── Message building ─────────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        """Build the complete system prompt with tools and KB description."""
        prompt = self.soul.get_system_prompt()

        # Add tool descriptions
        if self.tools:
            tool_prompt = self.tools.get_system_prompt()
            if tool_prompt:
                prompt += tool_prompt

        # Add knowledge base info
        if self.kb:
            try:
                import asyncio
                stats = asyncio.get_event_loop().run_until_complete(self.kb.get_stats())
                if stats["documents"] > 0:
                    prompt += (
                        f"\n\n=== KNOWLEDGE BASE ===\n"
                        f"You have access to a personal knowledge base with {stats['documents']} documents "
                        f"({stats['total_chunks']} chunks). "
                        f"When answering questions about uploaded documents, search the knowledge base using "
                        f"the kb_search tool to find relevant context.\n"
                    )
            except Exception:
                pass

        # Add instructions
        prompt += """
\n\n=== INSTRUCTIONS ===
- Be helpful, direct, and thorough
- Use tools when they can help accomplish the task
- For file operations, web search, code execution, etc., use the appropriate tool
- If you need to look up information in the knowledge base, use kb_search
- For complex tasks, use spawn_agent to delegate to a sub-agent
- Format code with proper syntax
- Be precise with numbers and facts
- Think step by step for complex problems
"""
        return prompt

    def _build_messages(
        self,
        user_input: str,
        tool_results: Optional[list[tuple[str, str]]] = None,
        system_additions: Optional[str] = None,
    ) -> list[dict[str, str]]:
        """Build the message list for the LLM."""
        messages = []

        # System prompt
        system = self._build_system_prompt()
        if system_additions:
            system += "\n\n" + system_additions
        messages.append({"role": "system", "content": system})

        # Conversation history
        history = self.memory.get_conversation_history(limit=50)
        messages.extend(history)

        # Tool results from previous calls
        if tool_results:
            for tool_name, result in tool_results:
                messages.append({
                    "role": "user",
                    "content": f"[Tool Result: {tool_name}]\n{result}\n\nWhat does this result mean? What's your next step?",
                })

        # Current user input
        messages.append({"role": "user", "content": user_input})

        return messages

    # ─── Main run loop ───────────────────────────────────────────────────────

    async def run(
        self,
        user_input: str,
        stream_callback: Optional[Callable[[str], Any]] = None,
    ) -> str:
        """
        Process a user message through the full ReAct loop.

        Args:
            user_input: The user's message.
            stream_callback: Optional async callback for streaming tokens.

        Returns:
            The final text response.
        """
        # Add user message to memory
        self.memory.add("user", user_input)

        # Check for knowledge base queries
        rag_context = await self._rag_query(user_input)
        system_additions = ""
        if rag_context:
            system_additions = (
                "IMPORTANT: The user may be asking about documents in the knowledge base. "
                "Use the kb_search tool to find relevant information first.\n"
                + rag_context
            )

        tool_results: list[tuple[str, str]] = []
        final_response = ""
        tool_count = 0

        # ── ReAct loop ────────────────────────────────────────────────────────
        for round_num in range(self.max_tool_calls):
            messages = self._build_messages(
                user_input,
                tool_results=tool_results if tool_results else None,
                system_additions=system_additions if round_num == 0 else None,
            )

            # Decide whether to stream
            use_stream = self.stream and self.model.supportsstreaming()

            if use_stream:
                # Stream the response
                response_text = ""
                thinking = True  # First text is "thinking", then actual response

                async for chunk in self.model.stream_chat(messages):
                    response_text += chunk

                    # Send to WebSocket
                    await self._send_ws("token", {"content": chunk})

                    # Callback
                    if stream_callback:
                        try:
                            await stream_callback(chunk)
                        except Exception:
                            pass

                final_response = response_text

            else:
                final_response = await self.model.chat(messages)
                await self._send_ws("token", {"content": final_response})

            # Extract and execute tool calls from response
            tool_calls = self._extract_tool_calls(final_response)

            if not tool_calls:
                # No more tools — we're done
                break

            for tool_name, parameters in tool_calls:
                if tool_count >= self.max_tool_calls:
                    break

                tool_count += 1

                # Execute tool
                await self._send_ws("status", {"status": "tool", "tool": tool_name})
                result_text = await self._execute_tool(tool_name, parameters)
                tool_results.append((tool_name, result_text))

                # Stream tool result
                await self._send_ws("tool_result", {
                    "tool": tool_name,
                    "result": result_text[:500],  # Preview for UI
                    "truncated": len(result_text) > 500,
                })

        # Add assistant response to memory
        self.memory.add("assistant", final_response)

        return final_response

    # ─── Sync wrapper (for non-streaming contexts) ────────────────────────────

    async def run_simple(self, user_input: str) -> str:
        """Simple non-streaming run."""
        return await self.run(user_input, stream_callback=None)


# ─── Tool: knowledge base search ──────────────────────────────────────────────

def create_kb_search_tool(kb_manager, config) -> "KBSearchTool":
    """Create a KB search tool bound to the KB manager."""
    return KBSearchTool(kb_manager, config)


class KBSearchTool:
    """Tool for searching the knowledge base."""

    name = "kb_search"
    description = (
        "Search the personal knowledge base for relevant documents. "
        "Use this when the user asks about uploaded files, documents, URLs, "
        "or any information that may have been added to the knowledge base. "
        "Returns the most relevant text chunks with source attribution."
    )
    category = "knowledge"

    def __init__(self, kb_manager, config):
        self._kb_manager = kb_manager
        self._config = config

    async def execute(self, query: str, kb_name: str = "default", top_k: int = 5) -> dict:
        """Search a knowledge base."""
        try:
            kb = self._kb_manager.get_or_create(kb_name, self._config)
            results = await kb.search(query, top_k=top_k)

            if not results:
                return {
                    "success": True,
                    "content": "(No relevant results found in knowledge base)",
                    "results": [],
                }

            formatted = []
            for i, r in enumerate(results, 1):
                formatted.append(
                    f"--- {r['doc_name']} (relevance: {r['similarity']}) ---\n"
                    f"{r['text'][:500]}"
                )

            return {
                "success": True,
                "content": "\n\n".join(formatted),
                "results": [
                    {
                        "text": r["text"],
                        "doc_name": r["doc_name"],
                        "source": r["source"],
                        "similarity": r["similarity"],
                    }
                    for r in results
                ],
            }
        except Exception as e:
            return {"success": False, "error": str(e), "content": f"[KB Search Error] {e}"}


class KBAddTool:
    """Tool for adding content to the knowledge base."""

    name = "kb_add"
    description = (
        "Add content to the personal knowledge base. "
        "Use kb_search to look up information, and kb_add to store new content. "
        "Supports: file paths (PDF, DOCX, TXT, etc.), URLs, or raw text. "
        "After adding, content becomes searchable for future queries."
    )
    category = "knowledge"

    def __init__(self, kb_manager, config):
        self._kb_manager = kb_manager
        self._config = config

    async def execute(
        self,
        content: Optional[str] = None,
        file_path: Optional[str] = None,
        url: Optional[str] = None,
        name: Optional[str] = None,
        kb_name: str = "default",
    ) -> dict:
        """Add content to the knowledge base."""
        try:
            kb = self._kb_manager.get_or_create(kb_name, self._config)

            if file_path:
                doc_id = await kb.add_file(file_path, name=name)
                return {"success": True, "content": f"Added file to knowledge base. Doc ID: {doc_id}", "doc_id": doc_id}
            elif url:
                doc_id = await kb.add_url(url, name=name)
                return {"success": True, "content": f"Added URL to knowledge base. Doc ID: {doc_id}", "doc_id": doc_id}
            elif content:
                doc_id = await kb.add_text(content, name=name or "Text Note", source="text")
                return {"success": True, "content": f"Added text to knowledge base. Doc ID: {doc_id}", "doc_id": doc_id}
            else:
                return {"success": False, "error": "Must provide content, file_path, or url", "content": "Must provide content, file_path, or url"}
        except Exception as e:
            return {"success": False, "error": str(e), "content": f"[KB Add Error] {e}"}


class KBListTool:
    """Tool for listing knowledge base documents."""

    name = "kb_list"
    description = "List all documents in a knowledge base."

    def __init__(self, kb_manager, config):
        self._kb_manager = kb_manager
        self._config = config

    async def execute(self, kb_name: str = "default") -> dict:
        """List knowledge base documents."""
        try:
            kb = self._kb_manager.get_or_create(kb_name, self._config)
            docs = kb.list_documents()
            stats = await kb.get_stats()
            return {
                "success": True,
                "content": json.dumps(docs, indent=2),
                "documents": docs,
                "stats": stats,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "content": f"[KB List Error] {e}"}
