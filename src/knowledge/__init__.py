"""
GreenClaw CPU — Knowledge Base System.

RAG-powered knowledge bases: upload documents, URLs, and text,
then search your personal knowledge using semantic similarity.

Supports:
- Document upload (PDF, DOCX, TXT, MD, CSV, etc.)
- URL scraping
- Text chunks with embeddings
- Semantic search
- Multiple knowledge bases
- Source attribution

MIT License — GreenClaw Team
"""

import hashlib
import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ─── Chunking ────────────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """
    Split text into overlapping chunks.

    Args:
        text: The text to chunk.
        chunk_size: Target characters per chunk.
        overlap: Character overlap between chunks.

    Returns:
        List of text chunks.
    """
    if len(text) <= chunk_size:
        return [text.strip()] if text.strip() else []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        # Try to break at sentence or paragraph boundary
        if end < len(text):
            for sep in ["\n\n", "\n", ". ", " "]:
                # Find last separator in chunk
                last_sep = chunk.rfind(sep)
                if last_sep > chunk_size // 2:
                    chunk = chunk[:last_sep + len(sep)]
                    end = start + len(chunk)
                    break

        chunks.append(chunk.strip())
        start = end - overlap
        if start <= chunks[-1].__len__() if chunks else 0:
            start = end

    # Filter empty chunks
    return [c for c in chunks if c.strip()]


# ─── Embedding provider ──────────────────────────────────────────────────────

class Embedder:
    """
    Generate text embeddings using available models.

    Falls back gracefully: Ollama → OpenAI → simple hash-based (no RAG).
    """

    def __init__(self, provider: str = "ollama", model: str = "nomic-embed-text"):
        self.provider = provider
        self.model = model
        self._client = None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a list of texts.

        Returns:
            List of embedding vectors (one per input text).
        """
        if not texts:
            return []

        # Try Ollama embeddings
        if self.provider in ("ollama", "openai", "openrouter", "localai"):
            try:
                return await self._embed_ollama(texts)
            except Exception as e:
                logger.debug(f"Ollama embedding failed: {e}")

        # Try OpenAI-compatible embeddings
        try:
            return await self._embed_openai(texts)
        except Exception:
            pass

        # Fallback: pseudo-embeddings (hash-based, for demo)
        return [self._pseudo_embed(t) for t in texts]

    async def _embed_ollama(self, texts: list[str]) -> list[list[float]]:
        """Embed using Ollama's embedding endpoint."""
        import httpx

        embeddings = []
        base_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        model = self.model or "nomic-embed-text"

        async with httpx.AsyncClient(timeout=30.0) as client:
            for text in texts:
                resp = await client.post(
                    f"{base_url}/api/embeddings",
                    json={"model": model, "prompt": text},
                )
                resp.raise_for_status()
                data = resp.json()
                embeddings.append(data.get("embedding", []))

        return embeddings

    async def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        """Embed using OpenAI-compatible API."""
        import httpx

        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        api_key = os.environ.get("OPENAI_API_KEY", "")
        model = "text-embedding-3-small"

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{base_url}/embeddings",
                headers=headers,
                json={"model": model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()
            return [item["embedding"] for item in data.get("data", [])]

    def _pseudo_embed(self, text: str) -> list[float]:
        """Pseudo-embedding based on word hashes (fallback)."""
        import hashlib
        vec = []
        words = re.findall(r"\w+", text.lower())
        for i in range(384):  # Nominal 384-dim vector
            h = hashlib.sha256(f"{words[i % max(len(words), 1)]}_{i}".encode()).digest()
            val = int.from_bytes(h[:4], "big") / (2**32 - 1) * 2 - 1
            vec.append(val)
        return vec


def cosine_sim(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ─── Document record ─────────────────────────────────────────────────────────

@dataclass
class Chunk:
    """A single text chunk with its embedding and metadata."""
    id: str
    text: str
    embedding: list[float]
    metadata: dict


@dataclass
class KBDocument:
    """A document in a knowledge base."""
    id: str
    name: str
    source: str  # "file", "url", "text"
    source_path: str
    chunks: list[Chunk] = field(default_factory=list)
    created_at: float = field(default_factory=0)


# ─── Knowledge Base ────────────────────────────────────────────────────────────

class KnowledgeBase:
    """
    A RAG-powered knowledge base.

    Upload documents, URLs, or text → chunks → embeddings → searchable.
    Uses ChromaDB for vector storage if available, otherwise pure Python.
    """

    def __init__(
        self,
        name: str = "default",
        kb_dir: Optional[str] = None,
        embedder: Optional[Embedder] = None,
        chunk_size: int = 500,
    ):
        self.name = name
        self.chunk_size = chunk_size
        self.embedder = embedder or Embedder()
        self.documents: dict[str, KBDocument] = {}
        self._chroma_client = None
        self._chroma_collection = None

        # Storage directory
        if kb_dir:
            self.kb_dir = Path(kb_dir).expanduser().resolve()
        else:
            self.kb_dir = Path("~/.greenchlaw/kb").expanduser()

        self.kb_dir.mkdir(parents=True, exist_ok=True)
        self.meta_file = self.kb_dir / f"{name}.meta.json"
        self._load_meta()

        # Try to use ChromaDB
        self._init_chroma()

    def _init_chroma(self):
        """Initialize ChromaDB if available."""
        try:
            import chromadb
            self._chroma_client = chromadb.PersistentClient(path=str(self.kb_dir / "chroma"))
            self._chroma_collection = self._chroma_client.get_or_create_collection(
                name=self.name,
                metadata={"kb_name": self.name},
            )
            logger.info(f"ChromaDB initialized for KB: {self.name}")
        except ImportError:
            logger.debug("ChromaDB not available, using in-memory search")
        except Exception as e:
            logger.warning(f"ChromaDB init failed: {e}")

    def _load_meta(self):
        """Load document metadata from disk."""
        if self.meta_file.exists():
            try:
                with open(self.meta_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Reconstruct documents (chunks loaded lazily)
                    for doc_id, doc_data in data.items():
                        self.documents[doc_id] = KBDocument(
                            id=doc_data["id"],
                            name=doc_data["name"],
                            source=doc_data["source"],
                            source_path=doc_data["source_path"],
                            created_at=doc_data.get("created_at", 0),
                        )
            except Exception as e:
                logger.warning(f"Failed to load KB meta: {e}")

    def _save_meta(self):
        """Save document metadata to disk."""
        data = {}
        for doc_id, doc in self.documents.items():
            data[doc_id] = {
                "id": doc.id,
                "name": doc.name,
                "source": doc.source,
                "source_path": doc.source_path,
                "created_at": doc.created_at,
            }
        with open(self.meta_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _gen_id(self, text: str) -> str:
        """Generate a stable ID from text."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    async def add_text(
        self,
        text: str,
        name: str,
        source: str = "text",
        source_path: str = "",
        metadata: Optional[dict] = None,
    ) -> str:
        """Add text content to the knowledge base."""
        import time

        doc_id = self._gen_id(text[:200])
        if doc_id in self.documents:
            return doc_id

        chunks = chunk_text(text, chunk_size=self.chunk_size)
        if not chunks:
            raise ValueError("No text content to add")

        # Generate embeddings
        embeddings = await self.embedder.embed(chunks)

        doc_chunks = []
        for chunk_text, embedding in zip(chunks, embeddings):
            chunk_id = self._gen_id(chunk_text)
            chunk = Chunk(
                id=chunk_id,
                text=chunk_text,
                embedding=embedding,
                metadata=metadata or {},
            )
            doc_chunks.append(chunk)

            # Store in ChromaDB if available
            if self._chroma_collection is not None:
                try:
                    self._chroma_collection.add(
                        ids=[chunk_id],
                        embeddings=[embedding],
                        documents=[chunk_text],
                        metadatas=[{"doc_id": doc_id, "doc_name": name, **(metadata or {})}],
                    )
                except Exception as e:
                    logger.warning(f"ChromaDB add failed: {e}")

        doc = KBDocument(
            id=doc_id,
            name=name,
            source=source,
            source_path=source_path,
            chunks=doc_chunks,
            created_at=time.time(),
        )
        self.documents[doc_id] = doc
        self._save_meta()

        logger.info(f"Added to KB '{self.name}': {name} ({len(chunks)} chunks)")
        return doc_id

    async def add_file(self, file_path: str, name: Optional[str] = None) -> str:
        """Add a file's content to the knowledge base."""
        from ..tools.document_tools import DocumentExtractTool
        import tempfile, asyncio

        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        tool = DocumentExtractTool()
        result = await tool.execute(file_path=file_path)
        if not result.success:
            raise RuntimeError(result.error or "Extraction failed")

        content = result.content.get("content", "") if isinstance(result.content, dict) else result.content
        return await self.add_text(
            text=content,
            name=name or path.name,
            source="file",
            source_path=str(path),
            metadata={"file_type": path.suffix, "file_size": path.stat().st_size},
        )

    async def add_url(self, url: str, name: Optional[str] = None) -> str:
        """Add URL content to the knowledge base."""
        from ..tools.web_tools import WebFetchTool

        tool = WebFetchTool()
        result = await tool.execute(url=url)
        if not result.success:
            raise RuntimeError(result.error or "Fetch failed")

        text = result.content.get("text", "") if isinstance(result.content, dict) else result.content
        title = name or url
        return await self.add_text(
            text=text,
            name=title,
            source="url",
            source_path=url,
            metadata={"url": url},
        )

    async def search(
        self,
        query: str,
        top_k: int = 5,
        min_similarity: float = 0.3,
    ) -> list[dict]:
        """
        Search the knowledge base for relevant chunks.

        Args:
            query: The search query.
            top_k: Number of results to return.
            min_similarity: Minimum cosine similarity (0-1).

        Returns:
            List of result dicts with text, source, similarity, and doc name.
        """
        # Get query embedding
        query_embeddings = await self.embedder.embed([query])
        query_emb = query_embeddings[0]

        results = []

        if self._chroma_collection is not None:
            # ChromaDB query
            try:
                chroma_results = self._chroma_collection.query(
                    query_embeddings=[query_emb],
                    n_results=min(top_k * 2, 100),
                    include=["documents", "metadatas", "distances"],
                )
                for i, (doc, meta, dist) in enumerate(zip(
                    chroma_results["documents"][0],
                    chroma_results["metadatas"][0],
                    chroma_results["distances"][0],
                )):
                    similarity = 1 - dist  # Convert distance to similarity
                    if similarity >= min_similarity:
                        results.append({
                            "text": doc,
                            "source": meta.get("source", "unknown"),
                            "doc_name": meta.get("doc_name", "Unknown"),
                            "doc_id": meta.get("doc_id", ""),
                            "similarity": round(similarity, 3),
                            "metadata": {k: v for k, v in meta.items() if k not in ("doc_id", "doc_name", "source")},
                        })
            except Exception as e:
                logger.warning(f"ChromaDB query failed: {e}")

        # Fallback: brute-force search over all chunks
        if not results:
            for doc in self.documents.values():
                for chunk in doc.chunks:
                    sim = cosine_sim(query_emb, chunk.embedding)
                    if sim >= min_similarity:
                        results.append({
                            "text": chunk.text,
                            "source": doc.source,
                            "doc_name": doc.name,
                            "doc_id": doc.id,
                            "similarity": round(sim, 3),
                            "metadata": chunk.metadata,
                        })

        # Sort by similarity and dedupe
        results.sort(key=lambda x: x["similarity"], reverse=True)
        seen = set()
        deduped = []
        for r in results:
            key = r["text"][:100]
            if key not in seen:
                seen.add(key)
                deduped.append(r)

        return deduped[:top_k]

    def list_documents(self) -> list[dict]:
        """List all documents in the knowledge base."""
        return [
            {
                "id": doc.id,
                "name": doc.name,
                "source": doc.source,
                "source_path": doc.source_path,
                "chunks": len(doc.chunks),
                "created_at": doc.created_at,
            }
            for doc in self.documents.values()
        ]

    async def delete_document(self, doc_id: str) -> bool:
        """Delete a document from the knowledge base."""
        if doc_id not in self.documents:
            return False

        doc = self.documents[doc_id]

        # Remove from ChromaDB
        if self._chroma_collection is not None:
            try:
                self._chroma_collection.delete(where={"doc_id": doc_id})
            except Exception as e:
                logger.warning(f"ChromaDB delete failed: {e}")

        del self.documents[doc_id]
        self._save_meta()
        return True

    async def get_stats(self) -> dict:
        """Get knowledge base statistics."""
        total_chunks = sum(len(d.chunks) for d in self.documents.values())
        total_chars = sum(sum(len(c.text) for c in d.chunks) for d in self.documents.values())
        return {
            "name": self.name,
            "documents": len(self.documents),
            "total_chunks": total_chunks,
            "total_characters": total_chars,
            "storage_dir": str(self.kb_dir),
        }


# ─── Knowledge Base Manager ────────────────────────────────────────────────────

class KBManager:
    """Manages multiple knowledge bases."""

    def __init__(self, kb_dir: Optional[str] = None):
        if kb_dir:
            self.kb_dir = Path(kb_dir).expanduser().resolve()
        else:
            self.kb_dir = Path("~/.greenchlaw/kb").expanduser()
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        self._kbs: dict[str, KnowledgeBase] = {}
        self._embedder: Optional[Embedder] = None

    def get_embedder(self, config) -> Embedder:
        """Get or create the embedder based on config."""
        if self._embedder is None:
            self._embedder = Embedder(
                provider=config.model.provider,
                model="nomic-embed-text",
            )
        return self._embedder

    def get_or_create(
        self,
        name: str,
        config,
        chunk_size: int = 500,
    ) -> KnowledgeBase:
        """Get or create a knowledge base."""
        if name not in self._kbs:
            embedder = self.get_embedder(config)
            self._kbs[name] = KnowledgeBase(
                name=name,
                kb_dir=str(self.kb_dir / name),
                embedder=embedder,
                chunk_size=chunk_size,
            )
        return self._kbs[name]

    def list_kbs(self) -> list[str]:
        """List all knowledge base directories."""
        return [d.name for d in self.kb_dir.iterdir() if d.is_dir()]
