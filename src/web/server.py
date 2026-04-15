"""
GreenClaw CPU — Web Server.

The ALL-IN-ONE GreenClaw web application:
- Chat with Claude-level AI
- Web search (Perplexity-level)
- Document upload + RAG (AnythingLLM-level)
- Agent system with tool use (OpenClaw-level)
- Multiple model providers
- Soul/personality switching
- Memory + knowledge bases
- Code execution, image understanding, and more

MIT License — GreenClaw Team
"""

import asyncio
import base64
import json
import logging
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Optional

import aiofiles
import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ─── Path setup ────────────────────────────────────────────────────────────────

THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = THIS_FILE.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ─── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ─── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="GreenClaw CPU",
    description="The ALL-IN-ONE AI Agent — Chat, Search, RAG, Code, Agents",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Static files ──────────────────────────────────────────────────────────────

STATIC_DIR = THIS_FILE.parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

from src.config import Config, get_config, reload_config

# ═══════════════════════════════════════════════════════════════════════════════
# Tool registry & knowledge base (initialized lazily)
# ═══════════════════════════════════════════════════════════════════════════════

_tool_registry = None
_kb_manager = None
_active_kb: Optional["KnowledgeBase"] = None


def get_tool_registry():
    """Get or create the global tool registry."""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = _build_tool_registry()
    return _tool_registry


def get_kb_manager():
    """Get or create the global KB manager."""
    global _kb_manager
    if _kb_manager is None:
        from src.knowledge import KBManager
        _kb_manager = KBManager()
    return _kb_manager


def _build_tool_registry():
    """Build the complete tool registry with all tools."""
    from src.tools.base import ToolRegistry, ToolCategory
    from src.tools.file_tools import register_file_tools
    from src.tools.web_tools import register_web_tools
    from src.tools.code_tools import register_code_tools
    from src.tools.document_tools import register_media_tools
    from src.tools.agent_tools import register_agent_tools

    registry = ToolRegistry()
    register_file_tools(registry)
    register_web_tools(registry)
    register_code_tools(registry)
    register_media_tools(registry)
    register_agent_tools(registry)

    logger.info(f"Tool registry built: {len(registry._tools)} tools")
    return registry


def _register_kb_tools(registry, kb_manager, config):
    """Register knowledge base tools with the registry."""
    from src.agent.orchestrator import create_kb_search_tool, KBAddTool, KBListTool

    kb_search = create_kb_search_tool(kb_manager, config)
    kb_add = KBAddTool(kb_manager, config)
    kb_list = KBListTool(kb_manager, config)

    registry.register(kb_search)
    registry.register(kb_add)
    registry.register(kb_list)


# ═══════════════════════════════════════════════════════════════════════════════
# Agent state
# ═══════════════════════════════════════════════════════════════════════════════

class AgentState:
    """Lazy-initialized agent state."""

    def __init__(self):
        self._config: Optional[Config] = None
        self._agent = None
        self._orchestrator = None
        self._initialized = False
        self._init_lock = asyncio.Lock()

    @property
    def config(self) -> Config:
        if self._config is None:
            self._config = get_config()
        return self._config

    async def ensure(self):
        """Lazily create agent and orchestrator."""
        async with self._init_lock:
            if self._initialized:
                return self._orchestrator

            cfg = self.config
            logger.info(f"Initializing GreenClaw: {cfg.model.provider}/{cfg.model.name}")

            # Model provider
            from src.models.factory import create_provider
            model_provider = create_provider(
                provider_name=cfg.model.provider,
                model_name=cfg.model.name,
                api_key=cfg.model.api_key,
                base_url=cfg.model.base_url,
                ollama_url=cfg.model.ollama_url,
                timeout=cfg.model.timeout,
            )

            # Soul manager
            soul_dir = Path(cfg.soul.soul_dir).expanduser().resolve()
            if not soul_dir.exists():
                soul_dir = PROJECT_ROOT / "souls"
            if not soul_dir.exists():
                soul_dir = PROJECT_ROOT.parent / "souls"

            from src.soul.soul_manager import SoulManager
            soul_manager = SoulManager(
                soul_dir=str(soul_dir),
                active_soul=cfg.soul.active_soul,
            )

            # Memory
            memory_dir = Path(cfg.memory.memory_dir).expanduser().resolve()
            if not memory_dir.exists():
                memory_dir = PROJECT_ROOT / "memory"

            from src.memory.memory import Memory
            memory = Memory(
                memory_dir=str(memory_dir),
                enabled=cfg.memory.enabled,
                consolidation_threshold=cfg.memory.consolidation_threshold,
            )

            # Tool registry
            tool_registry = get_tool_registry()
            kb_manager = get_kb_manager()
            _register_kb_tools(tool_registry, kb_manager, cfg)

            # Knowledge base
            global _active_kb
            _active_kb = kb_manager.get_or_create("default", cfg)

            # Orchestrator
            from src.agent.orchestrator import GreenClawOrchestrator
            self._orchestrator = GreenClawOrchestrator(
                model_provider=model_provider,
                soul_manager=soul_manager,
                memory=memory,
                tool_registry=tool_registry,
                knowledge_base=_active_kb,
                stream=cfg.model.stream,
            )

            self._initialized = True
            logger.info("GreenClaw fully initialized!")
            return self._orchestrator

    async def reload(self, new_config: Optional[Config] = None):
        """Reload agent with new config."""
        async with self._init_lock:
            if self._agent:
                await self._agent.close()
            global _tool_registry, _kb_manager, _active_kb
            _tool_registry = None
            _kb_manager = None
            _active_kb = None
            self._config = new_config
            self._initialized = False


state = AgentState()


# ═══════════════════════════════════════════════════════════════════════════════
# WebSocket connection manager
# ═══════════════════════════════════════════════════════════════════════════════

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def send_json(self, ws: WebSocket, data: dict):
        try:
            await ws.send_json(data)
        except Exception:
            self.disconnect(ws)

    async def broadcast(self, data: dict):
        for conn in list(self.active):
            try:
                await conn.send_json(data)
            except Exception:
                self.disconnect(conn)


manager = ConnectionManager()


# ═══════════════════════════════════════════════════════════════════════════════
# WebSocket: Streaming chat
# ═══════════════════════════════════════════════════════════════════════════════

@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """
    WebSocket for streaming chat with full tool support.

    Client → Server messages:
      {"type": "message", "content": "..."}
      {"type": "ping"}

    Server → Client events:
      {"type": "status", "status": "idle|thinking|streaming|tool", "detail": "..."}
      {"type": "token", "content": "..."}
      {"type": "tool_start", "tool": "tool_name", "params": {...}}
      {"type": "tool_result", "tool": "tool_name", "result": "..."}
      {"type": "done", "content": "..."}
      {"type": "error", "message": "..."}
    """
    await manager.connect(websocket)
    session_id = str(uuid.uuid4())[:8]
    logger.info(f"WS [{session_id}] connected")

    try:
        # Initial status
        cfg = state.config
        await manager.send_json(websocket, {
            "type": "status",
            "status": "idle",
            "model": cfg.model.name,
            "provider": cfg.model.provider,
        })

        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await manager.send_json(websocket, {"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = msg.get("type")

            if msg_type == "message":
                user_content = msg.get("content", "").strip()
                if not user_content:
                    continue

                orch = await state.ensure()
                orch.set_websocket(
                    lambda e: manager.send_json(websocket, e),
                    session_id=session_id,
                )

                await manager.send_json(websocket, {
                    "type": "status",
                    "status": "thinking",
                    "detail": "Analyzing request…",
                })

                try:
                    response = await orch.run(user_content)
                    await manager.send_json(websocket, {
                        "type": "done",
                        "content": response,
                    })

                except Exception as e:
                    logger.error(f"Chat error [{session_id}]: {e}")
                    await manager.send_json(websocket, {
                        "type": "error",
                        "message": str(e),
                    })

            elif msg_type == "ping":
                await manager.send_json(websocket, {"type": "pong"})

            else:
                await manager.send_json(websocket, {
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}",
                })

    except WebSocketDisconnect:
        logger.info(f"WS [{session_id}] disconnected")
    finally:
        manager.disconnect(websocket)


# ═══════════════════════════════════════════════════════════════════════════════
# REST API: Core endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
async def health():
    """System health check."""
    result = {"healthy": True, "components": {}}
    try:
        orch = await state.ensure()
        model_health = await orch.model.health_check()
        result["components"]["model"] = model_health
        result["components"]["soul"] = orch.soul.get_active_soul() is not None
        result["components"]["memory"] = orch.memory.enabled
        result["components"]["tools"] = len(get_tool_registry()._tools)
        result["healthy"] = model_health if isinstance(model_health, bool) else all(model_health.values())
    except Exception as e:
        result["healthy"] = False
        result["error"] = str(e)
    return JSONResponse(result)


class ConfigUpdateRequest(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    active_soul: Optional[str] = None


@app.get("/api/config")
async def get_config():
    """Get current configuration."""
    cfg = state.config
    return {
        "model": {
            "provider": cfg.model.provider,
            "name": cfg.model.name,
            "ollama_url": cfg.model.ollama_url,
            "stream": cfg.model.stream,
        },
        "soul": {
            "active_soul": cfg.soul.active_soul,
            "available": [],
        },
        "memory": {"enabled": cfg.memory.enabled},
        "server": {"port": cfg.server.port},
    }


@app.post("/api/config")
async def update_config(body: ConfigUpdateRequest):
    """Update configuration."""
    try:
        if body.active_soul:
            orch = await state.ensure()
            orch.soul.switch_soul(body.active_soul)
            return {"status": "ok", "message": f"Switched to soul: {body.active_soul}"}
        return {"status": "ok", "message": "Config updated"}
    except Exception as e:
        raise HTTPException(status_code=500, message=str(e))


@app.get("/api/models")
async def list_models():
    """List available models."""
    cfg = state.config
    models = []

    if cfg.model.provider == "ollama":
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{cfg.model.ollama_url}/api/tags")
                if resp.status_code == 200:
                    for m in resp.json().get("models", []):
                        models.append({"name": m.get("name", ""), "size": m.get("size", 0)})
        except Exception as e:
            logger.warning(f"Could not fetch Ollama models: {e}")

    return {"provider": cfg.model.provider, "models": models}


@app.get("/api/tools")
async def list_tools():
    """List all available tools."""
    registry = get_tool_registry()
    return {"tools": registry.list_all()}


@app.get("/api/souls")
async def list_souls():
    """List available souls."""
    try:
        orch = await state.ensure()
        return {
            "souls": orch.soul.list_available_souls(),
            "active": orch.soul._active_soul_name,
        }
    except Exception as e:
        raise HTTPException(status_code=500, message=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# REST API: Knowledge base
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/kb/search")
async def kb_search(query: str = Form(...), kb_name: str = Form("default"), top_k: int = Form(5)):
    """Search a knowledge base."""
    try:
        cfg = state.config
        kb_mgr = get_kb_manager()
        kb = kb_mgr.get_or_create(kb_name, cfg)
        results = await kb.search(query, top_k=top_k)
        return {"results": results, "query": query, "kb": kb_name}
    except Exception as e:
        raise HTTPException(status_code=500, message=str(e))


@app.post("/api/kb/add/text")
async def kb_add_text(
    content: str = Form(...),
    name: str = Form(""),
    kb_name: str = Form("default"),
):
    """Add raw text to a knowledge base."""
    try:
        cfg = state.config
        kb_mgr = get_kb_manager()
        kb = kb_mgr.get_or_create(kb_name, cfg)
        doc_id = await kb.add_text(content, name=name or "Text Note", source="text")
        stats = await kb.get_stats()
        return {"status": "ok", "doc_id": doc_id, "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, message=str(e))


@app.post("/api/kb/add/url")
async def kb_add_url(
    url: str = Form(...),
    name: str = Form(""),
    kb_name: str = Form("default"),
):
    """Add a URL to a knowledge base."""
    try:
        cfg = state.config
        kb_mgr = get_kb_manager()
        kb = kb_mgr.get_or_create(kb_name, cfg)
        doc_id = await kb.add_url(url, name=name)
        stats = await kb.get_stats()
        return {"status": "ok", "doc_id": doc_id, "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/kb/add/file")
async def kb_add_file(
    file: UploadFile = File(...),
    kb_name: str = Form("default"),
    name: str = Form(""),
):
    """Upload and index a file into a knowledge base."""
    try:
        cfg = state.config
        kb_mgr = get_kb_manager()
        kb = kb_mgr.get_or_create(kb_name, cfg)

        # Save uploaded file to temp dir
        suffix = Path(file.filename).suffix if file.filename else ""
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            async with aiofiles.open(tmp.name, "wb") as out:
                content = await file.read()
                await out.write(content)
            tmp_path = tmp.name

        try:
            file_name = name or file.filename or "uploaded_file"
            doc_id = await kb.add_file(tmp_path, name=file_name)
            stats = await kb.get_stats()
            return {
                "status": "ok",
                "doc_id": doc_id,
                "file_name": file_name,
                "stats": stats,
            }
        finally:
            os.unlink(tmp_path)

    except Exception as e:
        raise HTTPException(status_code=500, message=str(e))


@app.get("/api/kb/list")
async def kb_list(kb_name: str = "default"):
    """List documents in a knowledge base."""
    try:
        cfg = state.config
        kb_mgr = get_kb_manager()
        kb = kb_mgr.get_or_create(kb_name, cfg)
        docs = kb.list_documents()
        stats = await kb.get_stats()
        return {"documents": docs, "stats": stats, "kb": kb_name}
    except Exception as e:
        raise HTTPException(status_code=500, message=str(e))


@app.delete("/api/kb/document/{doc_id}")
async def kb_delete(doc_id: str, kb_name: str = "default"):
    """Delete a document from a knowledge base."""
    try:
        cfg = state.config
        kb_mgr = get_kb_manager()
        kb = kb_mgr.get_or_create(kb_name, cfg)
        success = await kb.delete_document(doc_id)
        return {"status": "ok" if success else "not_found", "doc_id": doc_id}
    except Exception as e:
        raise HTTPException(status_code=500, message=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# REST API: Chat (non-WebSocket fallback)
# ═══════════════════════════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str
    stream: bool = False


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Non-streaming chat endpoint (REST fallback)."""
    try:
        orch = await state.ensure()
        response = await orch.run_simple(request.message)
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, message=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# REST API: Memory
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/memory/stats")
async def memory_stats():
    """Get memory statistics."""
    try:
        orch = await state.ensure()
        return {
            "enabled": orch.memory.enabled,
            "message_count": orch.memory.get_recent_count(),
            "total_messages": orch.memory._message_count,
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/memory/clear")
async def memory_clear():
    """Clear conversation memory."""
    try:
        orch = await state.ensure()
        orch.memory.clear()
        return {"status": "ok", "message": "Memory cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, message=str(e))


@app.get("/api/memory/history")
async def memory_history(limit: int = 50):
    """Get conversation history."""
    try:
        orch = await state.ensure()
        history = orch.memory.get_conversation_history(limit=limit)
        return {"history": history}
    except Exception as e:
        raise HTTPException(status_code=500, message=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# REST API: Image understanding
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/analyze/image")
async def analyze_image(file: UploadFile = File(...), prompt: str = Form("Describe this image in detail.")):
    """Analyze an uploaded image."""
    try:
        # Save to temp
        suffix = Path(file.filename).suffix if file.filename else ".png"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            async with aiofiles.open(tmp.name, "wb") as out:
                content = await file.read()
                await out.write(content)
            tmp_path = tmp.name

        try:
            from src.tools.document_tools import ImageUnderstandTool
            tool = ImageUnderstandTool()
            result = await tool.execute(image_path=tmp_path, prompt=prompt)
            return result.to_dict()
        finally:
            os.unlink(tmp_path)
    except Exception as e:
        raise HTTPException(status_code=500, message=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# Static file serving
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({
        "message": "GreenClaw CPU — The ALL-IN-ONE AI Agent",
        "version": "0.1.0",
        "endpoints": {
            "websocket": "/ws/chat",
            "chat": "POST /api/chat",
            "health": "GET /api/health",
            "config": "GET /api/config",
            "tools": "GET /api/tools",
            "knowledge_base": {
                "search": "POST /api/kb/search",
                "add_text": "POST /api/kb/add/text",
                "add_url": "POST /api/kb/add/url",
                "add_file": "POST /api/kb/add/file",
                "list": "GET /api/kb/list",
            },
        },
    })


@app.get("/favicon.ico")
async def favicon():
    return JSONResponse({}, status_code=204)


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

def run_server(host: str = "0.0.0.0", port: int = 51234, reload: bool = False):
    logging.info(f"Starting GreenClaw CPU Web on http://{host}:{port}")
    uvicorn.run(
        "src.web.server:app",
        host=host,
        port=port,
        log_level="info",
        proxy_headers=True,
        forwarded_allow_ips="*",
        reload=reload,
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="GreenClaw CPU Web Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=51234)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port, reload=args.reload)
