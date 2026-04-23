"""3-Tier Memory System for C.E.H. (Core Engine Hub).

Implements:
  1. Persistent Memory: agent.md reading/writing with structured sections
  2. Short-term Memory: Context window management with snip/microcompact strategies
  3. Long-term Memory: Vector DB integration interface (FAISS / ChromaDB)

State persistence uses sqlite3 with atomic transactions.
Context isolation separates memory, tool output, and instruction chunks.
System prompt protection: chunk_type="instruction" chunks are NEVER trimmed
or summarized during compaction.
"""

from __future__ import annotations

import abc
import datetime
import hashlib
import json
import logging
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_DB_PATH = ".ceh_state.db"
COMPACTION_THRESHOLD = 0.80  # trigger at 80% of max window
DEFAULT_MAX_TOKENS = 8192

# Chunk types for context isolation
CHUNK_TYPE_INSTRUCTION = "instruction"
CHUNK_TYPE_MEMORY = "memory"
CHUNK_TYPE_TOOL = "tool"

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

try:
    from pydantic import BaseModel, Field

    class SessionModel(BaseModel):
        """Pydantic model for a session record."""
        id: str
        created_at: int
        metadata: Dict[str, Any] = Field(default_factory=dict)

    class StepModel(BaseModel):
        """Pydantic model for a step record."""
        id: str
        session_id: str
        step_number: int
        role: str
        content: str
        timestamp: int

    class ContextChunkModel(BaseModel):
        """Pydantic model for a context chunk record."""
        id: str
        session_id: str
        chunk_type: str  # instruction | memory | tool
        content: str
        token_count: int

    class AgentConfig(BaseModel):
        """Agent configuration loaded from agent.md."""
        name: str = "CEH-Agent"
        version: str = "0.1.0"
        description: str = "Your local AI assistant"
        model_path: str = "./models/llama-3-8b.Q4_K_M.gguf"
        n_gpu_layers: int = -1
        n_ctx: int = 8192
        temperature: float = 0.7
        max_context_tokens: int = 8192
        compaction_strategy: str = "microcompact"
        permission_mode: str = "autonomous"
        max_auto_errors: int = 3
        success_reset: int = 5
        tools: Dict[str, bool] = Field(default_factory=lambda: {
            "file_read": True,
            "file_write": True,
            "execute_command": True,
            "web_search": False,
        })
        log_level: str = "INFO"
        log_format: str = "json"

except ImportError:  # pragma: no cover — pydantic is a hard dep
    BaseModel = object  # type: ignore
    SessionModel = StepModel = ContextChunkModel = AgentConfig = object  # type: ignore


# ---------------------------------------------------------------------------
# Token Estimator
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Rough token count estimation: ~4 chars per token for English text."""
    if not text:
        return 0
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# SessionManager — sqlite3 backend with atomic transactions
# ---------------------------------------------------------------------------

class SessionManager:
    """Manages sessions, steps, and context chunks in sqlite3.

    All database operations use atomic transactions.
    Database path: ``.ceh_state.db`` (configurable).
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        self._init_db()

    # -- public helpers -----------------------------------------------------

    def create_session(self, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Create a new session and return its ID."""
        session_id = str(uuid.uuid4())
        now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        meta_json = json.dumps(metadata or {})
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO sessions (id, created_at, metadata) VALUES (?, ?, ?)",
                (session_id, now, meta_json),
            )
            conn.commit()
        finally:
            conn.close()
        logger.info("Session created session_id=%s", session_id)
        return session_id

    def get_session(self, session_id: str) -> Optional[SessionModel]:
        """Retrieve a session by ID."""
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT id, created_at, metadata FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return SessionModel(
            id=row[0],
            created_at=row[1],
            metadata=json.loads(row[2]),
        )

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its steps and chunks atomically."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DELETE FROM context_chunks WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM steps WHERE session_id = ?", (session_id,))
            result = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
            return result.rowcount > 0
        finally:
            conn.close()

    def add_step(
        self,
        session_id: str,
        step_number: int,
        role: str,
        content: str,
    ) -> str:
        """Add a step to a session atomically. Returns step ID."""
        step_id = str(uuid.uuid4())
        now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO steps (id, session_id, step_number, role, content, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (step_id, session_id, step_number, role, content, now),
            )
            conn.commit()
        finally:
            conn.close()
        return step_id

    def get_steps(self, session_id: str) -> List[StepModel]:
        """Retrieve all steps for a session ordered by step_number."""
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT id, session_id, step_number, role, content, timestamp "
                "FROM steps WHERE session_id = ? ORDER BY step_number",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()
        return [
            StepModel(
                id=r[0], session_id=r[1], step_number=r[2],
                role=r[3], content=r[4], timestamp=r[5],
            )
            for r in rows
        ]

    def add_context_chunk(
        self,
        session_id: str,
        chunk_type: str,
        content: str,
        token_count: int,
    ) -> str:
        """Add a context chunk atomically. Returns chunk ID."""
        chunk_id = str(uuid.uuid4())
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO context_chunks (id, session_id, chunk_type, content, token_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (chunk_id, session_id, chunk_type, content, token_count),
            )
            conn.commit()
        finally:
            conn.close()
        return chunk_id

    def get_context_chunks(self, session_id: str) -> List[ContextChunkModel]:
        """Retrieve all context chunks for a session."""
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT id, session_id, chunk_type, content, token_count "
                "FROM context_chunks WHERE session_id = ? ORDER BY rowid",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()
        return [
            ContextChunkModel(
                id=r[0], session_id=r[1], chunk_type=r[2],
                content=r[3], token_count=r[4],
            )
            for r in rows
        ]

    def delete_context_chunks(self, session_id: str) -> int:
        """Delete all context chunks for a session. Returns count deleted."""
        conn = sqlite3.connect(self.db_path)
        try:
            result = conn.execute(
                "DELETE FROM context_chunks WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
            return result.rowcount
        finally:
            conn.close()

    def get_eligible_chunks_for_compaction(
        self, session_id: str
    ) -> List[ContextChunkModel]:
        """Return only memory and tool chunks (NOT instruction) for compaction."""
        all_chunks = self.get_context_chunks(session_id)
        return [c for c in all_chunks if c.chunk_type in (CHUNK_TYPE_MEMORY, CHUNK_TYPE_TOOL)]

    def replace_chunks(self, session_id: str, new_chunks: List[ContextChunkModel]) -> None:
        """Atomically replace all context chunks for a session."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DELETE FROM context_chunks WHERE session_id = ?", (session_id,))
            for chunk in new_chunks:
                conn.execute(
                    "INSERT INTO context_chunks (id, session_id, chunk_type, content, token_count) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (chunk.id, chunk.session_id, chunk.chunk_type, chunk.content, chunk.token_count),
                )
            conn.commit()
        finally:
            conn.close()

    # -- init ---------------------------------------------------------------

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    created_at INTEGER,
                    metadata TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS steps (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    step_number INTEGER,
                    role TEXT,
                    content TEXT,
                    timestamp INTEGER,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS context_chunks (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    chunk_type TEXT,
                    content TEXT,
                    token_count INTEGER,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)
            conn.commit()
        finally:
            conn.close()

    # -- state persistence --------------------------------------------------

    def save_full_state(self, session_id: str, state: Dict[str, Any]) -> None:
        """Save full agent state as a context chunk under session."""
        content_json = json.dumps(state)
        token_count = estimate_tokens(content_json)
        self.add_context_chunk(session_id, CHUNK_TYPE_MEMORY, content_json, token_count)

    def restore_full_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Restore full agent state from the latest memory chunk."""
        chunks = self.get_context_chunks(session_id)
        # Find the latest memory chunk
        memory_chunks = [c for c in chunks if c.chunk_type == CHUNK_TYPE_MEMORY]
        if not memory_chunks:
            return None
        latest = memory_chunks[-1]
        try:
            return json.loads(latest.content)
        except json.JSONDecodeError:
            logger.error("Failed to parse saved state chunk_id=%s", latest.id)
            return None


# ---------------------------------------------------------------------------
# ContextManager — short-term memory with compaction
# ---------------------------------------------------------------------------

class ContextManager:
    """Manages short-term context with token tracking and compaction.

    Strategies:
      - ``snip``: trim oldest eligible context when limit exceeded.
      - ``microcompact``: summarize trimmed context via LLM call.

    System prompt protection: chunks with ``chunk_type="instruction"`` are
    NEVER trimmed or summarized during compaction.
    """

    def __init__(
        self,
        session_manager: SessionManager,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        strategy: str = "microcompact",
        llm_summarize_callback: Optional[callable] = None,
    ) -> None:
        self.session_manager = session_manager
        self.max_tokens = max_tokens
        self.strategy = strategy
        self.llm_summarize_callback = llm_summarize_callback

    # -- public API ---------------------------------------------------------

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        chunk_type: str = CHUNK_TYPE_MEMORY,
    ) -> str:
        """Add a message to context. Returns chunk ID."""
        token_count = estimate_tokens(content)
        chunk_id = self.session_manager.add_context_chunk(
            session_id, chunk_type, content, token_count,
        )
        # Check if compaction is needed
        self._maybe_compact(session_id)
        return chunk_id

    def add_instruction(
        self, session_id: str, content: str
    ) -> str:
        """Add a protected instruction chunk (system prompt, identity)."""
        return self.add_message(session_id, "system", content, CHUNK_TYPE_INSTRUCTION)

    def add_tool_output(
        self, session_id: str, content: str
    ) -> str:
        """Add a tool output chunk."""
        return self.add_message(session_id, "tool", content, CHUNK_TYPE_TOOL)

    def get_context(self, session_id: str) -> List[ContextChunkModel]:
        """Return all context chunks for the session."""
        return self.session_manager.get_context_chunks(session_id)

    def get_context_text(self, session_id: str) -> str:
        """Return concatenated context text (all chunk types)."""
        chunks = self.get_context(session_id)
        parts: List[str] = []
        for chunk in chunks:
            parts.append(f"[{chunk.chunk_type}] {chunk.content}")
        return "\n".join(parts)

    def get_total_token_count(self, session_id: str) -> int:
        """Return total token count for all chunks in the session."""
        chunks = self.get_context_chunks(session_id)
        return sum(c.token_count for c in chunks)

    def clear_context(self, session_id: str) -> int:
        """Clear all context chunks. Returns count deleted."""
        return self.session_manager.delete_context_chunks(session_id)

    # -- compaction ---------------------------------------------------------

    def _maybe_compact(self, session_id: str) -> None:
        """Trigger compaction if context reaches 80% of max window."""
        total_tokens = self.get_total_token_count(session_id)
        threshold = self.max_tokens * COMPACTION_THRESHOLD
        if total_tokens >= threshold:
            logger.info(
                "Context compaction triggered total_tokens=%d threshold=%d max_tokens=%d strategy=%s",
                total_tokens,
                threshold,
                self.max_tokens,
                self.strategy,
            )
            self.compact(session_id)

    def compact(self, session_id: str) -> None:
        """Compact context using the configured strategy.

        Only ``chunk_type="memory"`` and ``chunk_type="tool"`` chunks are
        eligible for trimming/summarization. Instruction chunks are preserved.
        """
        # Separate protected and eligible chunks
        all_chunks = self.session_manager.get_context_chunks(session_id)
        protected = [c for c in all_chunks if c.chunk_type == CHUNK_TYPE_INSTRUCTION]
        eligible = [c for c in all_chunks if c.chunk_type in (CHUNK_TYPE_MEMORY, CHUNK_TYPE_TOOL)]

        if not eligible:
            return

        if self.strategy == "snip":
            new_chunks = self._compact_snip(protected, eligible)
        elif self.strategy == "microcompact":
            new_chunks = self._compact_microcompact(protected, eligible)
        else:
            logger.warning("Unknown strategy, keeping all chunks strategy=%s", self.strategy)
            new_chunks = all_chunks

        self.session_manager.replace_chunks(session_id, new_chunks)
        logger.info(
            "Context compacted before=%d after=%d strategy=%s",
            len(all_chunks),
            len(new_chunks),
            self.strategy,
        )

    def _compact_snip(
        self,
        protected: List[ContextChunkModel],
        eligible: List[ContextChunkModel],
    ) -> List[ContextChunkModel]:
        """Snip strategy: remove oldest eligible chunks until under threshold."""
        # Remove oldest first (eligible are ordered by rowid)
        remaining = list(eligible)
        while remaining and self._total_tokens(protected + remaining) >= self.max_tokens:
            removed = remaining.pop(0)
            logger.debug("Snip removed chunk chunk_id=%s tokens=%d", removed.id, removed.token_count)

        return protected + remaining

    def _compact_microcompact(
        self,
        protected: List[ContextChunkModel],
        eligible: List[ContextChunkModel],
    ) -> List[ContextChunkModel]:
        """Microcompact strategy: summarize oldest eligible chunks via LLM."""
        if not self.llm_summarize_callback:
            logger.warning("No LLM callback for microcompact; falling back to snip")
            return self._compact_snip(protected, eligible)

        remaining = list(eligible)
        to_summarize: List[ContextChunkModel] = []

        # Collect chunks to summarize until under threshold
        while remaining and self._total_tokens(protected + remaining) >= self.max_tokens:
            chunk = remaining.pop(0)
            to_summarize.append(chunk)

        if to_summarize:
            summary = self._summarize_chunks(to_summarize)
            summary_chunk = ContextChunkModel(
                id=str(uuid.uuid4()),
                session_id=to_summarize[0].session_id,
                chunk_type=CHUNK_TYPE_MEMORY,
                content=summary,
                token_count=estimate_tokens(summary),
            )
            return protected + remaining + [summary_chunk]

        return protected + remaining

    def _summarize_chunks(self, chunks: List[ContextChunkModel]) -> str:
        """Call the LLM callback to summarize chunks."""
        combined = "\n".join(f"[{c.chunk_type}] {c.content}" for c in chunks)
        try:
            summary = self.llm_summarize_callback(combined)
            if summary:
                return summary
        except Exception as e:  # noqa: BLE001 — fallback safe
            logger.error("LLM summarize failed error=%s", str(e))
        # Fallback: truncate each chunk to first 200 chars
        parts = []
        for c in chunks:
            truncated = c.content[:200] + "..." if len(c.content) > 200 else c.content
            parts.append(f"[{c.chunk_type}] {truncated}")
        return "Summarized (fallback): " + "\n".join(parts)

    def _total_tokens(self, chunks: List[ContextChunkModel]) -> int:
        """Sum token counts for a list of chunks."""
        return sum(c.token_count for c in chunks)

    def get_context_chunks(self, session_id: str) -> List[ContextChunkModel]:
        """Alias for session_manager.get_context_chunks."""
        return self.session_manager.get_context_chunks(session_id)


# ---------------------------------------------------------------------------
# VectorDBInterface — abstract long-term memory
# ---------------------------------------------------------------------------

class VectorDBInterface(abc.ABC):
    """Abstract interface for vector database backends."""

    @abc.abstractmethod
    def add_documents(
        self,
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        """Add documents to the vector store. Returns document IDs."""

    @abc.abstractmethod
    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar documents. Returns list of {id, score, metadata, document}."""

    @abc.abstractmethod
    def delete(self, ids: List[str]) -> bool:
        """Delete documents by ID. Returns True if successful."""

    @abc.abstractmethod
    def close(self) -> None:
        """Close the vector DB connection."""


class FAISSAdapter(VectorDBInterface):
    """FAISS-based vector store adapter."""

    def __init__(self, dim: int = 768, index_type: str = "Flat") -> None:
        self.dim = dim
        self.index_type = index_type
        self._documents: List[str] = []
        self._metadatas: List[Dict[str, Any]] = []
        self._ids: List[str] = []
        self._index = None
        self._initialized = False

    def _ensure_index(self) -> None:
        """Lazy-initialize FAISS index."""
        if self._initialized:
            return
        try:
            import faiss  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "faiss is required for FAISSAdapter. "
                "Install with: pip install faiss-cpu"
            ) from exc
        if self.index_type == "Flat":
            self._index = faiss.IndexFlatL2(self.dim)
        else:
            self._index = faiss.IndexFlatIP(self.dim)
        self._initialized = True

    def add_documents(
        self,
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        self._ensure_index()
        # Simple embedding: use hash-based vector (placeholder for real embeddings)
        ids: List[str] = []
        vectors = []
        for doc in documents:
            doc_id = str(uuid.uuid4())
            ids.append(doc_id)
            self._documents.append(doc)
            self._metadatas.append(metadatas[len(self._metadatas)] if metadatas else {})
            # Hash-based embedding (placeholder)
            h = hashlib.sha256(doc.encode()).digest()
            vec = [float(b) / 255.0 for b in h[:self.dim]]
            vectors.append(vec)

        if vectors and self._index is not None:
            import numpy as np  # type: ignore
            matrix = np.array(vectors, dtype=np.float32)
            self._index.add(matrix)
        self._ids.extend(ids)
        return ids

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        self._ensure_index()
        if not self._documents or self._index is None:
            return []

        import numpy as np  # type: ignore
        h = hashlib.sha256(query.encode()).digest()
        vec = np.array([[float(b) / 255.0 for b in h[:self.dim]]], dtype=np.float32)
        distances, indices = self._index.search(vec, min(top_k, len(self._documents)))

        results = []
        for dist, idx in zip(distances[0], indices[0], strict=False):
            if idx < 0 or idx >= len(self._documents):
                continue
            results.append({
                "id": self._ids[idx],
                "score": float(dist),
                "metadata": self._metadatas[idx],
                "document": self._documents[idx],
            })
        return results

    def delete(self, ids: List[str]) -> bool:
        # FAISS doesn't support deletion by ID natively in all index types
        # Mark as deleted by filtering in search
        delete_set = set(ids)
        self._documents = [
            d for d, i in zip(self._documents, self._ids, strict=False) if i not in delete_set
        ]
        self._metadatas = [
            m for m, i in zip(self._metadatas, self._ids, strict=False) if i not in delete_set
        ]
        self._ids = [i for i in self._ids if i not in delete_set]
        return True

    def close(self) -> None:
        self._index = None


class ChromaDBAdapter(VectorDBInterface):
    """ChromaDB-based vector store adapter."""

    def __init__(self, collection_name: str = "ceh_memory", persist_path: Optional[str] = None) -> None:
        self.collection_name = collection_name
        self.persist_path = persist_path
        self._client = None
        self._collection = None

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        try:
            import chromadb  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "chromadb is required for ChromaDBAdapter. "
                "Install with: pip install chromadb"
            ) from exc
        if self.persist_path:
            self._client = chromadb.PersistentClient(path=self.persist_path)
        else:
            self._client = chromadb.EphemeralClient()
        self._collection = self._client.get_or_create_collection(self.collection_name)

    def add_documents(
        self,
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        self._ensure_client()
        ids = [str(uuid.uuid4()) for _ in documents]
        embeddings = self._embed_documents(documents)
        self._collection.add(
            documents=documents,
            ids=ids,
            metadatas=metadatas or [{} for _ in ids],
            embeddings=embeddings,
        )
        return ids

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        self._ensure_client()
        embedding = self._embed_query(query)
        kwargs: Dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": min(top_k, self._collection.count()),
        }
        if filter_metadata:
            kwargs["where"] = filter_metadata
        results = self._collection.query(**kwargs)
        output = []
        for i in range(len(results["ids"][0])):
            output.append({
                "id": results["ids"][0][i],
                "score": float(results["distances"][0][i]) if results["distances"] else 0.0,
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "document": results["documents"][0][i] if results["documents"] else "",
            })
        return output

    def delete(self, ids: List[str]) -> bool:
        self._ensure_client()
        self._collection.delete(ids=ids)
        return True

    def close(self) -> None:
        if self._client is not None:
            # ChromaDB ephemeral client closes automatically
            self._client = None

    def _embed_documents(self, documents: List[str]) -> List[List[float]]:
        """Generate simple embeddings (placeholder for real embedding model)."""
        embeddings = []
        for doc in documents:
            h = hashlib.sha256(doc.encode()).digest()
            # Use first 384 bytes as float vector
            vec = [float(b) / 255.0 for b in h[:384]]
            embeddings.append(vec)
        return embeddings

    def _embed_query(self, query: str) -> List[float]:
        """Generate embedding for a query."""
        h = hashlib.sha256(query.encode()).digest()
        return [float(b) / 255.0 for b in h[:384]]


# ---------------------------------------------------------------------------
# PersistentMemory — agent.md reading/writing
# ---------------------------------------------------------------------------

class PersistentMemory:
    """Persistent configuration storage using sqlite3 and agent.md."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH, agent_md_path: str = "agent.md") -> None:
        self.db_path = db_path
        self.agent_md_path = Path(agent_md_path)
        self._session_manager = SessionManager(db_path)

    def load_config(self) -> AgentConfig:
        """Load agent configuration from agent.md."""
        if not self.agent_md_path.exists():
            logger.warning("agent.md not found, using defaults")
            return AgentConfig()
        content = self.agent_md_path.read_text(encoding="utf-8")
        return self._parse_agent_md(content)

    def save_config(self, config: AgentConfig) -> None:
        """Save agent configuration to agent.md."""
        content = self._format_agent_md(config)
        self.agent_md_path.write_text(content, encoding="utf-8")
        # Also persist to sqlite3
        self._session_manager.save_full_state(
            "config",
            config.model_dump() if hasattr(config, "model_dump") else config.__dict__,
        )

    def get(self, key: str) -> Optional[str]:
        """Retrieve a config value by key from sqlite3."""
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT content FROM context_chunks WHERE session_id = 'config' AND chunk_type = 'instruction' ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        try:
            data = json.loads(row[0])
            return str(data.get(key, ""))
        except (json.JSONDecodeError, TypeError):
            return None

    def set(self, key: str, value: str) -> None:
        """Store a config value by key in sqlite3."""
        existing = self.get("all")
        data = {}
        if existing:
            try:
                data = json.loads(existing)
            except (json.JSONDecodeError, TypeError):
                data = {}
        data[key] = value
        content_json = json.dumps(data)
        token_count = estimate_tokens(content_json)
        self._session_manager.add_context_chunk(
            "config", CHUNK_TYPE_INSTRUCTION, content_json, token_count,
        )

    def _parse_agent_md(self, content: str) -> AgentConfig:
        """Parse agent.md YAML-like content into AgentConfig."""
        data: Dict[str, Any] = {}
        current_section = None
        _current_subsection = None

        for line in content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            # Detect sections (MUST come before generic # check)
            if stripped.startswith("## "):
                current_section = stripped[3:].strip().lower()
                continue

            if stripped.startswith("### "):
                _ = stripped[4:].strip().lower()
                continue

            # Skip other comments
            if stripped.startswith("#"):
                continue

            # Parse key: value
            if ":" in stripped and not stripped.startswith("-"):
                key, _, value = stripped.partition(":")
                key = key.strip()
                value = value.strip()

                # Skip if key matches section header (e.g., "tools:" under "## Tools")
                if current_section and key == current_section:
                    continue

                # Convert types
                if value.lower() == "true":
                    value = True
                elif value.lower() == "false":
                    value = False
                else:
                    try:
                        value = int(value)
                    except ValueError:
                        try:
                            value = float(value)
                        except ValueError:
                            pass  # Keep as string

                # Normalize section matching (handle "permission settings" vs "permissions")
                is_model = current_section in ("model",)
                is_memory = current_section in ("memory",)
                is_permissions = current_section in ("permissions", "permission settings")
                is_tools = current_section in ("tools",)
                is_logging = current_section in ("logging",)

                if is_model:
                    data.setdefault("model_path", "")
                    data[f"model_{key}"] = value
                elif is_memory:
                    data[f"memory_{key}"] = value
                elif is_permissions:
                    data[f"permission_{key}"] = value
                elif is_tools:
                    data.setdefault("tools", {})
                    data["tools"][key] = value
                elif is_logging:
                    data[f"log_{key}"] = value
                else:
                    data[key] = value

        # Default tools dict
        _default_tools = {"file_read": True, "file_write": True, "execute_command": True, "web_search": False}

        # Map parsed keys to AgentConfig fields
        config_dict = {
            "name": data.get("name", "CEH-Agent"),
            "version": data.get("version", "0.1.0"),
            "description": data.get("description", "Your local AI assistant"),
            "model_path": data.get("model_path", data.get("model_path", "./models/llama-3-8b.Q4_K_M.gguf")),
            "n_gpu_layers": data.get("n_gpu_layers", data.get("model_n_gpu_layers", -1)),
            "n_ctx": data.get("n_ctx", data.get("model_n_ctx", 8192)),
            "temperature": data.get("temperature", data.get("model_temperature", 0.7)),
            "max_context_tokens": data.get("max_context_tokens", data.get("memory_max_context_tokens", 8192)),
            "compaction_strategy": data.get("compaction_strategy", data.get("memory_compaction_strategy", "microcompact")),
            "permission_mode": data.get("permission_mode", data.get("permission_mode", "autonomous")),
            "max_auto_errors": data.get("max_auto_errors", data.get("max_auto_errors", 3)),
            "success_reset": data.get("success_reset", data.get("success_reset", 5)),
            "tools": data.get("tools") if isinstance(data.get("tools"), dict) else _default_tools,
            "log_level": data.get("log_level", data.get("log_level", "INFO")),
            "log_format": data.get("log_format", data.get("log_format", "json")),
        }
        return AgentConfig(**config_dict)

    def _format_agent_md(self, config: AgentConfig) -> str:
        """Format AgentConfig back to agent.md YAML-like content."""
        return f"""# Agent Configuration

## Identity
name: {config.name}
version: {config.version}
description: {config.description}

## Model Settings
model:
  path: {config.model_path}
  n_gpu_layers: {config.n_gpu_layers}
  n_ctx: {config.n_ctx}
  temperature: {config.temperature}

## Memory Settings
memory:
  max_context_tokens: {config.max_context_tokens}
  compaction_strategy: {config.compaction_strategy}

## Permission Settings
permissions:
  mode: {config.permission_mode}
  max_auto_errors: {config.max_auto_errors}
  success_reset: {config.success_reset}

## Tools
tools:
  file_read: {config.tools.get('file_read', True)}
  file_write: {config.tools.get('file_write', True)}
  execute_command: {config.tools.get('execute_command', True)}
  web_search: {config.tools.get('web_search', False)}

## Logging
logging:
  level: {config.log_level}
  format: {config.log_format}
"""


# ---------------------------------------------------------------------------
# MemorySystem — main orchestrator
# ---------------------------------------------------------------------------

class MemorySystem:
    """Main orchestrator for the 3-tier memory system.

    Combines PersistentMemory, ContextManager, and VectorDBInterface
    into a unified API.
    """

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        agent_md_path: str = "agent.md",
        max_tokens: int = DEFAULT_MAX_TOKENS,
        strategy: str = "microcompact",
        vector_db: Optional[VectorDBInterface] = None,
        llm_summarize_callback: Optional[callable] = None,
    ) -> None:
        self.db_path = db_path
        self.agent_md_path = agent_md_path
        self.vector_db = vector_db
        self._persistent = PersistentMemory(db_path, agent_md_path)
        self._session_manager = SessionManager(db_path)
        self._context_manager = ContextManager(
            session_manager=self._session_manager,
            max_tokens=max_tokens,
            strategy=strategy,
            llm_summarize_callback=llm_summarize_callback,
        )

    # -- persistent memory --------------------------------------------------

    def load_config(self) -> AgentConfig:
        """Load agent configuration from agent.md."""
        return self._persistent.load_config()

    def save_config(self, config: AgentConfig) -> None:
        """Save agent configuration to agent.md and sqlite3."""
        self._persistent.save_config(config)

    # -- session management -------------------------------------------------

    def create_session(self, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Create a new session and return its ID."""
        return self._session_manager.create_session(metadata)

    def get_session(self, session_id: str) -> Optional[SessionModel]:
        """Retrieve a session by ID."""
        return self._session_manager.get_session(session_id)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its data."""
        return self._session_manager.delete_session(session_id)

    # -- context management -------------------------------------------------

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        chunk_type: str = CHUNK_TYPE_MEMORY,
    ) -> str:
        """Add a message to context."""
        return self._context_manager.add_message(session_id, role, content, chunk_type)

    def add_instruction(self, session_id: str, content: str) -> str:
        """Add a protected instruction chunk."""
        return self._context_manager.add_instruction(session_id, content)

    def add_tool_output(
        self, session_id: str, content: str, chunk_type: str = CHUNK_TYPE_TOOL
    ) -> str:
        """Add a tool output chunk."""
        return self._context_manager.add_tool_output(session_id, content)

    def get_context(self, session_id: str) -> List[ContextChunkModel]:
        """Return all context chunks."""
        return self._context_manager.get_context(session_id)

    def get_context_text(self, session_id: str) -> str:
        """Return concatenated context text."""
        return self._context_manager.get_context_text(session_id)

    def get_total_token_count(self, session_id: str) -> int:
        """Return total token count."""
        return self._context_manager.get_total_token_count(session_id)

    def compact_context(self, session_id: str) -> None:
        """Manually trigger context compaction."""
        self._context_manager.compact(session_id)

    def clear_context(self, session_id: str) -> int:
        """Clear all context chunks."""
        return self._context_manager.clear_context(session_id)

    # -- vector DB ----------------------------------------------------------

    def store_in_vector_db(
        self,
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        """Store documents in the vector DB (optional)."""
        if self.vector_db is None:
            logger.warning("Vector DB not configured, skipping storage")
            return []
        return self.vector_db.add_documents(documents, metadatas)

    def search_vector_db(
        self,
        query: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Search the vector DB (optional)."""
        if self.vector_db is None:
            return []
        return self.vector_db.search(query, top_k)

    # -- state persistence --------------------------------------------------

    def save_full_state(self, session_id: str, state: Dict[str, Any]) -> None:
        """Save full agent state to sqlite3."""
        self._session_manager.save_full_state(session_id, state)

    def restore_full_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Restore full agent state from sqlite3."""
        return self._session_manager.restore_full_state(session_id)

    # -- steps management ---------------------------------------------------

    def add_step(
        self,
        session_id: str,
        step_number: int,
        role: str,
        content: str,
    ) -> str:
        """Add a step to a session."""
        return self._session_manager.add_step(session_id, step_number, role, content)

    def get_steps(self, session_id: str) -> List[StepModel]:
        """Retrieve all steps for a session."""
        return self._session_manager.get_steps(session_id)
