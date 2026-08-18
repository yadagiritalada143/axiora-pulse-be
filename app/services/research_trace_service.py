"""
Research Trace Service
──────────────────────────────────────────────────────────────────────────────
Central service for capturing, storing, and streaming real-time research queries 
and research sources (URLs, citations) executed by orchestration agents.

Supports:
  1. ContextVar tracking for active `run_id` across async task boundaries
  2. In-memory buffer per run_id
  3. Server-Sent Events (SSE) subscriber broadcasting for real-time UI stream
"""
import asyncio
import logging
from contextvars import ContextVar
from datetime import datetime
from typing import Any, AsyncGenerator

from app.models.orchestration_models import (
    ResearchQueryTrace,
    ResearchSourceTrace,
    ResearchTraceResponse,
)

logger = logging.getLogger(__name__)

# ContextVar for implicit run_id propagation in async execution context
current_run_id_var: ContextVar[str | None] = ContextVar("current_run_id", default=None)
current_agent_var: ContextVar[str | None] = ContextVar("current_agent", default=None)


class ResearchTraceService:
    """
    Singleton service managing research traces and real-time SSE subscriptions.
    """

    _instance: "ResearchTraceService | None" = None

    def __new__(cls) -> "ResearchTraceService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._runs: dict[str, dict[str, Any]] = {}
            cls._instance._lock = asyncio.Lock()
        return cls._instance

    def set_context(self, run_id: str | None, agent_name: str | None = None) -> None:
        """Set contextvars for current run_id and agent_name."""
        current_run_id_var.set(run_id)
        if agent_name:
            current_agent_var.set(agent_name)

    def get_context_run_id(self) -> str | None:
        """Retrieve active run_id from contextvar."""
        return current_run_id_var.get()

    def get_context_agent_name(self) -> str | None:
        """Retrieve active agent_name from contextvar."""
        return current_agent_var.get()

    def start_run_trace(self, run_id: str) -> None:
        """Initialize trace store for a new orchestration run."""
        self._runs[run_id] = {
            "queries": [],
            "sources": [],
            "is_active": True,
            "subscribers": set(),
            "created_at": datetime.utcnow(),
        }
        logger.info(f"[ResearchTraceService] ▶ Started research trace for run_id={run_id}")

    def end_run_trace(self, run_id: str) -> None:
        """Mark orchestration run trace as completed and notify subscribers."""
        run_data = self._runs.get(run_id)
        if run_data:
            run_data["is_active"] = False
            # Send completion signal to SSE subscribers
            event = {
                "event": "run_completed",
                "run_id": run_id,
                "timestamp": datetime.utcnow().isoformat(),
            }
            for q in list(run_data["subscribers"]):
                try:
                    q.put_nowait(event)
                except Exception:
                    pass
        logger.info(f"[ResearchTraceService] ✓ Ended research trace for run_id={run_id}")

    async def log_query(
        self,
        query: str,
        run_id: str | None = None,
        agent_name: str | None = None,
        status: str = "completed",
    ) -> ResearchQueryTrace:
        """Record a research query and broadcast to stream subscribers."""
        target_run_id = run_id or self.get_context_run_id()
        target_agent = agent_name or self.get_context_agent_name() or "orchestration_agent"

        trace = ResearchQueryTrace(
            agent_name=target_agent,
            query=query,
            status=status,
            timestamp=datetime.utcnow(),
        )

        if not target_run_id:
            logger.debug(f"[ResearchTraceService] Query logged outside run context: '{query}'")
            return trace

        run_data = self._runs.setdefault(
            target_run_id,
            {
                "queries": [],
                "sources": [],
                "is_active": True,
                "subscribers": set(),
                "created_at": datetime.utcnow(),
            },
        )

        # Avoid duplicate queries
        existing_queries = {q.query for q in run_data["queries"]}
        if query not in existing_queries:
            run_data["queries"].append(trace)
            logger.info(
                f"[ResearchTraceService] Logged query for run_id={target_run_id[:8]}… | "
                f"agent={target_agent} | query='{query}'"
            )

            # Broadcast SSE event
            event = {
                "event": "research_query",
                "run_id": target_run_id,
                "data": trace.model_dump(mode="json"),
            }
            for subscriber_queue in list(run_data["subscribers"]):
                try:
                    subscriber_queue.put_nowait(event)
                except Exception:
                    pass

        return trace

    async def log_source(
        self,
        url: str,
        title: str | None = None,
        snippet: str | None = None,
        run_id: str | None = None,
        agent_name: str | None = None,
    ) -> ResearchSourceTrace:
        """Record a research source and broadcast to stream subscribers."""
        target_run_id = run_id or self.get_context_run_id()
        target_agent = agent_name or self.get_context_agent_name() or "orchestration_agent"

        trace = ResearchSourceTrace(
            agent_name=target_agent,
            title=title,
            url=url,
            snippet=snippet,
            timestamp=datetime.utcnow(),
        )

        if not target_run_id:
            logger.debug(f"[ResearchTraceService] Source logged outside run context: '{url}'")
            return trace

        run_data = self._runs.setdefault(
            target_run_id,
            {
                "queries": [],
                "sources": [],
                "is_active": True,
                "subscribers": set(),
                "created_at": datetime.utcnow(),
            },
        )

        # Avoid duplicate URLs per run
        existing_urls = {s.url for s in run_data["sources"]}
        if url not in existing_urls:
            run_data["sources"].append(trace)
            logger.info(
                f"[ResearchTraceService] Logged source for run_id={target_run_id[:8]}… | "
                f"agent={target_agent} | url='{url}'"
            )

            # Broadcast SSE event
            event = {
                "event": "research_source",
                "run_id": target_run_id,
                "data": trace.model_dump(mode="json"),
            }
            for subscriber_queue in list(run_data["subscribers"]):
                try:
                    subscriber_queue.put_nowait(event)
                except Exception:
                    pass

        return trace

    def get_traces(self, run_id: str) -> ResearchTraceResponse:
        """Fetch captured research queries and sources for a run_id."""
        run_data = self._runs.get(run_id)
        if not run_data:
            return ResearchTraceResponse(
                run_id=run_id,
                queries=[],
                sources=[],
                is_active=False,
            )

        return ResearchTraceResponse(
            run_id=run_id,
            queries=run_data["queries"],
            sources=run_data["sources"],
            is_active=run_data["is_active"],
        )

    async def subscribe_stream(self, run_id: str) -> AsyncGenerator[dict[str, Any], None]:
        """Subscribe to real-time research trace events (for SSE streaming)."""
        queue: asyncio.Queue = asyncio.Queue()
        run_data = self._runs.setdefault(
            run_id,
            {
                "queries": [],
                "sources": [],
                "is_active": True,
                "subscribers": set(),
                "created_at": datetime.utcnow(),
            },
        )

        run_data["subscribers"].add(queue)

        try:
            # Yield initial snapshot event
            yield {
                "event": "snapshot",
                "run_id": run_id,
                "data": self.get_traces(run_id).model_dump(mode="json"),
            }

            while True:
                # Wait for next event with a periodic heartbeat timeout
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield event
                    if event.get("event") == "run_completed":
                        break
                except asyncio.TimeoutError:
                    yield {
                        "event": "ping",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
        finally:
            if run_id in self._runs:
                self._runs[run_id]["subscribers"].discard(queue)


# Singleton instance
research_trace_service = ResearchTraceService()
