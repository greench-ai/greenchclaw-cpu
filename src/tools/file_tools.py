"""
GreenClaw CPU — File Operation Tools.

Read, write, list, search, and manipulate files on the filesystem.
Freedom is Key — full filesystem access within safe boundaries.
"""

import os
import glob as _glob
import hashlib
import logging
from pathlib import Path
from typing import Optional

from .base import Tool, ToolCategory, ToolResult, tool

logger = logging.getLogger(__name__)


class FileReadTool(Tool):
    """Read the contents of a file."""

    name = "file_read"
    description = "Read the complete contents of a file. Use for viewing source code, configs, text files, logs, etc."
    category = ToolCategory.FILE
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Full path to the file to read",
            },
            "offset": {
                "type": "integer",
                "description": "Line number to start reading from (1-indexed)",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of lines to read (default: all)",
            },
        },
        "required": ["path"],
    }

    async def execute(self, path: str, offset: int = 1, limit: Optional[int] = None) -> ToolResult:
        try:
            file_path = Path(path).expanduser().resolve()
            if not file_path.exists():
                return ToolResult(success=False, error=f"File not found: {path}")
            if not file_path.is_file():
                return ToolResult(success=False, error=f"Not a file: {path}")

            size = file_path.stat().st_size
            if size > 10_000_000:
                return ToolResult(
                    success=False,
                    error=f"File too large ({size / 1024 / 1024:.1f} MB). Max 10MB."
                )

            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                if offset > 1:
                    lines = f.readlines()
                    lines = lines[offset - 1:]
                    content = "".join(lines[:limit] if limit else lines)
                elif limit:
                    lines = f.readlines()[:limit]
                    content = "".join(lines)
                else:
                    content = f.read()

            line_count = content.count("\n") + 1
            return ToolResult(
                success=True,
                content=content,
                metadata={"path": str(file_path), "size": size, "lines": line_count},
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Read error: {e}")


class FileWriteTool(Tool):
    """Write content to a file (creates or overwrites)."""

    name = "file_write"
    description = "Write content to a file. Creates the file if it doesn't exist, overwrites if it does. Use for creating source files, configs, notes, etc."
    category = ToolCategory.FILE
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Full path to the file to write",
            },
            "content": {
                "type": "string",
                "description": "The content to write to the file",
            },
            "append": {
                "type": "boolean",
                "description": "If true, append to existing file instead of overwriting (default: false)",
            },
        },
        "required": ["path", "content"],
    }

    async def execute(self, path: str, content: str, append: bool = False) -> ToolResult:
        try:
            file_path = Path(path).expanduser().resolve()
            file_path.parent.mkdir(parents=True, exist_ok=True)

            mode = "a" if append else "w"
            with open(file_path, mode, encoding="utf-8") as f:
                f.write(content)

            size = file_path.stat().st_size
            action = "appended to" if append else "written to"
            return ToolResult(
                success=True,
                content=f"Successfully {action} {file_path} ({size} bytes)",
                metadata={"path": str(file_path), "size": size, "bytes_written": len(content)},
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Write error: {e}")


class FileListTool(Tool):
    """List files in a directory."""

    name = "file_list"
    description = "List files and directories at a given path. Shows name, type, size, and modification time."
    category = ToolCategory.FILE
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path to list (default: current directory)",
            },
            "pattern": {
                "type": "string",
                "description": "Glob pattern to filter results (e.g. '*.py', '**/*.md')",
            },
            "recursive": {
                "type": "boolean",
                "description": "List subdirectories recursively (default: false)",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of entries to return (default: 100)",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        path: str = ".",
        pattern: Optional[str] = None,
        recursive: bool = False,
        limit: int = 100,
    ) -> ToolResult:
        try:
            base_path = Path(path).expanduser().resolve()
            if not base_path.exists():
                return ToolResult(success=False, error=f"Path not found: {path}")
            if not base_path.is_dir():
                return ToolResult(success=False, error=f"Not a directory: {path}")

            entries = []
            if pattern:
                if recursive:
                    glob_path = base_path / "**" / pattern
                    matched = _glob.glob(str(glob_path), recursive=True)
                else:
                    matched = _glob.glob(str(base_path / pattern))
                for p in matched[:limit]:
                    fp = Path(p)
                    entries.append({
                        "name": fp.name,
                        "path": str(fp),
                        "type": "dir" if fp.is_dir() else "file",
                        "size": fp.stat().st_size if fp.is_file() else 0,
                    })
            else:
                count = 0
                for entry in sorted(base_path.iterdir()):
                    if count >= limit:
                        break
                    entries.append({
                        "name": entry.name,
                        "path": str(entry),
                        "type": "dir" if entry.is_dir() else "file",
                        "size": entry.stat().st_size if entry.is_file() else 0,
                    })
                    count += 1

            return ToolResult(
                success=True,
                content=entries,
                metadata={"path": str(base_path), "count": len(entries)},
            )
        except Exception as e:
            return ToolResult(success=False, error=f"List error: {e}")


class FileSearchTool(Tool):
    """Search for text within files (grep-like)."""

    name = "file_search"
    description = "Search for text patterns within files using regex or plain text. Returns matching lines with context."
    category = ToolCategory.FILE
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Text or regex pattern to search for",
            },
            "path": {
                "type": "string",
                "description": "Directory or file path to search in",
            },
            "recursive": {
                "type": "boolean",
                "description": "Search subdirectories (default: true)",
            },
            "file_pattern": {
                "type": "string",
                "description": "Only search in files matching this pattern (e.g. '*.py')",
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "Case-sensitive search (default: false)",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum matching lines to return (default: 100)",
            },
        },
        "required": ["query", "path"],
    }

    async def execute(
        self,
        query: str,
        path: str = ".",
        recursive: bool = True,
        file_pattern: Optional[str] = None,
        case_sensitive: bool = False,
        max_results: int = 100,
    ) -> ToolResult:
        try:
            import re

            base_path = Path(path).expanduser().resolve()
            if not base_path.exists():
                return ToolResult(success=False, error=f"Path not found: {path}")

            flags = 0 if case_sensitive else re.IGNORECASE
            pattern = re.compile(query, flags)

            matches = []
            file_pattern_re = None
            if file_pattern:
                # Simple glob to regex
                fp = file_pattern.replace(".", r"\.").replace("*", ".*").replace("?", ".")
                file_pattern_re = re.compile(fp)

            def search_file(file_path: Path):
                results = []
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        for lineno, line in enumerate(f, 1):
                            if pattern.search(line):
                                results.append({
                                    "file": str(file_path),
                                    "line": lineno,
                                    "text": line.rstrip(),
                                })
                                if len(results) >= max_results:
                                    return results
                except Exception:
                    pass
                return results

            # Collect files
            if base_path.is_file():
                files = [base_path]
            else:
                if recursive:
                    files = [p for p in base_path.rglob("*") if p.is_file()]
                else:
                    files = [p for p in base_path.iterdir() if p.is_file()]

            if file_pattern_re:
                files = [f for f in files if file_pattern_re.search(f.name)]

            for file_path in files[:500]:  # max 500 files
                matches.extend(search_file(file_path))
                if len(matches) >= max_results:
                    break

            return ToolResult(
                success=True,
                content=matches[:max_results],
                metadata={"query": query, "path": str(base_path), "matches": len(matches)},
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Search error: {e}")


class FileInfoTool(Tool):
    """Get detailed information about a file or directory."""

    name = "file_info"
    description = "Get detailed information about a file or directory: size, modification time, permissions, type, checksum."
    category = ToolCategory.FILE
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to get information about",
            },
        },
        "required": ["path"],
    }

    async def execute(self, path: str) -> ToolResult:
        try:
            file_path = Path(path).expanduser().resolve()
            if not file_path.exists():
                return ToolResult(success=False, error=f"Path not found: {path}")

            stat = file_path.stat()
            info = {
                "path": str(file_path),
                "name": file_path.name,
                "type": "directory" if file_path.is_dir() else "file",
                "size": stat.st_size,
                "size_human": _human_size(stat.st_size),
                "modified": _format_time(stat.st_mtime),
                "created": _format_time(stat.st_ctime),
                "permissions": oct(stat.st_mode)[-3:],
                "readable": os.access(file_path, os.R_OK),
                "writable": os.access(file_path, os.W_OK),
            }

            if file_path.is_file():
                # MD5 checksum
                md5 = hashlib.md5()
                with open(file_path, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        md5.update(chunk)
                info["md5"] = md5.hexdigest()

            return ToolResult(success=True, content=info, metadata={"path": str(file_path)})
        except Exception as e:
            return ToolResult(success=False, error=f"Info error: {e}")


def _human_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def _format_time(timestamp: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def register_file_tools(registry) -> None:
    """Register all file operation tools."""
    registry.register(FileReadTool())
    registry.register(FileWriteTool())
    registry.register(FileListTool())
    registry.register(FileSearchTool())
    registry.register(FileInfoTool())
