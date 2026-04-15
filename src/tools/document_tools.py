"""
GreenClaw CPU — Document & Media Tools.

Document upload, text extraction, and image understanding.
Supports PDFs, Office docs, images, URLs, and more.
"""

import base64
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from .base import Tool, ToolCategory, ToolResult

logger = logging.getLogger(__name__)


class DocumentExtractTool(Tool):
    """Extract text content from uploaded documents (PDF, DOCX, TXT, etc.)."""

    name = "document_extract"
    description = (
        "Extract text content from a document file. "
        "Supports PDF, DOCX, TXT, RTF, CSV, and more. "
        "Use this to read uploaded documents, research papers, contracts, etc."
    )
    category = ToolCategory.MEDIA
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the uploaded document file",
            },
            "max_chars": {
                "type": "integer",
                "description": "Maximum characters to extract (default: 50000)",
            },
        },
        "required": ["file_path"],
    }

    async def execute(
        self,
        file_path: str,
        max_chars: int = 50000,
    ) -> ToolResult:
        try:
            path = Path(file_path).expanduser().resolve()
            if not path.exists():
                return ToolResult(success=False, error=f"File not found: {file_path}")

            ext = path.suffix.lower()
            content = ""

            if ext == ".txt" or ext == ".text":
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(max_chars)

            elif ext == ".md":
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(max_chars)

            elif ext in {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".json", ".yaml", ".yml", ".sh", ".toml", ".xml", ".sql", ".go", ".rs", ".java", ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".swift", ".kt", ".scala", ".lua"}:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(max_chars)

            elif ext == ".pdf":
                content = await _extract_pdf(path, max_chars)

            elif ext in {".docx", ".doc"}:
                content = await _extract_docx(path, max_chars)

            elif ext == ".csv":
                content = await _extract_csv(path, max_chars)

            else:
                # Try to read as text
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read(max_chars)
                except Exception:
                    return ToolResult(
                        success=False,
                        error=f"Unsupported file type: {ext}. Supported: txt, md, py, js, ts, html, css, json, yaml, pdf, docx, csv, and more.",
                    )

            if len(content) >= max_chars:
                content = content[:max_chars] + f"\n\n… [truncated at {max_chars} chars]"

            return ToolResult(
                success=True,
                content={
                    "file_name": path.name,
                    "file_type": ext,
                    "size": path.stat().st_size,
                    "content": content,
                    "chars": len(content),
                },
                metadata={"path": str(path), "ext": ext},
            )

        except Exception as e:
            return ToolResult(success=False, error=f"Extraction error: {e}")


async def _extract_pdf(path: Path, max_chars: int) -> str:
    """Extract text from PDF using PyMuPDF (fitz) or pdfminer."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(path))
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
            if sum(len(t) for t in text_parts) >= max_chars:
                break
        doc.close()
        return "".join(text_parts)
    except ImportError:
        try:
            # Fallback: pdfminer
            from pdfminer.high_level import extract_text
            return extract_text(str(path), maxchars=max_chars)
        except ImportError:
            return "[PDF extraction requires PyMuPDF: pip install PyMuPDF]"
    except Exception as e:
        return f"[PDF extraction error: {e}]"


async def _extract_docx(path: Path, max_chars: int) -> str:
    """Extract text from DOCX using python-docx."""
    try:
        from docx import Document
        doc = Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        content = "\n".join(paragraphs)
        return content[:max_chars]
    except ImportError:
        return "[DOCX extraction requires python-docx: pip install python-docx]"
    except Exception as e:
        return f"[DOCX extraction error: {e}]"


async def _extract_csv(path: Path, max_chars: int) -> str:
    """Extract text from CSV as a formatted table."""
    try:
        import csv
        lines = []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            rows = list(reader)
            if not rows:
                return "(empty CSV)"
            header = rows[0]
            lines.append(" | ".join(header))
            lines.append(" | ".join(["---"] * len(header)))
            for row in rows[1:50]:  # Limit to 50 rows
                lines.append(" | ".join(str(c)[:50] for c in row))
            content = "\n".join(lines)
            return content[:max_chars]
    except Exception as e:
        return f"[CSV extraction error: {e}]"


class ImageUnderstandTool(Tool):
    """Understand and describe images using vision models."""

    name = "image_understand"
    description = (
        "Analyze an image and describe what's in it. "
        "Use for charts, diagrams, screenshots, photos, documents, UI designs, "
        "and any visual content. Returns a detailed text description."
    )
    category = ToolCategory.MEDIA
    parameters = {
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Path to an image file (local path or URL)",
            },
            "prompt": {
                "type": "string",
                "description": "Specific question or aspect to focus on (optional)",
            },
        },
        "required": ["image_path"],
    }

    async def execute(
        self,
        image_path: str,
        prompt: Optional[str] = None,
    ) -> ToolResult:
        from ..models.factory import create_provider
        from ..config import get_config

        try:
            cfg = get_config()

            # Load image
            if image_path.startswith(("http://", "https://")):
                image_data = await _fetch_image_data(image_path)
            else:
                path = Path(image_path).expanduser().resolve()
                if not path.exists():
                    return ToolResult(success=False, error=f"Image not found: {image_path}")
                image_data = path.read_bytes()

            # Encode as base64
            b64 = base64.b64encode(image_data).decode("utf-8")
            mime = _guess_mime(image_path)

            # Build vision prompt
            focus = f" Focus on: {prompt}" if prompt else ""
            vision_prompt = (
                f"Describe this image in detail.{focus} "
                "Include any text visible, objects, colors, layout, "
                "and any other relevant visual information."
            )

            # Call vision-capable model
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": vision_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    ],
                }
            ]

            # Use OpenAI or Anthropic for vision
            try:
                if cfg.model.provider in ("openai", "openrouter", "localai"):
                    provider = create_provider(
                        cfg.model.provider,
                        model_name=cfg.model.name,
                        api_key=cfg.model.api_key,
                        base_url=cfg.model.base_url,
                        ollama_url=cfg.model.ollama_url,
                    )
                    response = await provider.chat(messages)
                    return ToolResult(success=True, content=response)
                else:
                    return ToolResult(
                        success=False,
                        error="Image understanding requires OpenAI, OpenRouter, or LocalAI provider with vision support. "
                              "Set provider to 'openai' or 'openrouter' in config.",
                    )
            except Exception as e:
                return ToolResult(success=False, error=f"Vision model error: {e}")

        except Exception as e:
            return ToolResult(success=False, error=f"Image understanding failed: {e}")


async def _fetch_image_data(url: str) -> bytes:
    """Fetch image bytes from URL."""
    import httpx
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


def _guess_mime(path: str) -> str:
    ext = Path(path).suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".svg": "image/svg+xml",
    }
    return mime_map.get(ext, "image/jpeg")


def register_media_tools(registry) -> None:
    """Register document and media tools."""
    registry.register(DocumentExtractTool())
    registry.register(ImageUnderstandTool())
