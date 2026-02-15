# Typing
from typing import Generator
# Base generator
from .base_generator import BaseEventGenerator
# Event
from ..sse_formatter import sse_event
# Schemas
from app.schemas.runs import RunObject, TokenUsage

class ThreadRunEventGenerator(BaseEventGenerator):
    """Generator for ThreadRun lifecycle events."""
    
    def __init__(self, thread_id: str, run_id: str, assistant_id: str, model: str):
        super().__init__(thread_id, run_id, assistant_id)
        self.model = model
    
    def generate_events(self) -> Generator[str, None, None]:
        """Generate thread run lifecycle events: created, queued, in_progress."""
        yield self._created_event()
        yield self._queued_event()
        yield self._in_progress_event()
    
    def _created_event(self) -> str:
        return sse_event(
            event="thread.run.created",
            data=RunObject(
                id=self.run_id,
                created_at=self.created_at,
                expires_at=self.created_at,
                assistant_id=self.assistant_id,
                thread_id=self.thread_id,
                status="queued",
                model=self.model
            ).model_dump()
        )
    
    def _queued_event(self) -> str:
        return sse_event(
            event="thread.run.queued",
            data=RunObject(
                id=self.run_id,
                created_at=self.created_at,
                expires_at=self.created_at,
                assistant_id=self.assistant_id,
                thread_id=self.thread_id,
                status="queued",
                model=self.model
            ).model_dump()
        )
    
    def _in_progress_event(self) -> str:
        return sse_event(
            event="thread.run.in_progress",
            data=RunObject(
                id=self.run_id,
                created_at=self.created_at,
                expires_at=self.created_at,
                assistant_id=self.assistant_id,
                thread_id=self.thread_id,
                status="in_progress",
                model=self.model
            ).model_dump()
        )
    
    def completed_event(self, instructions: str, prompt_tokens: int, completion_tokens: int) -> str:
        """Generate run completed event."""
        return sse_event(
            event="thread.run.completed",
            data=RunObject(
                id=self.run_id,
                created_at=self.created_at,
                expires_at=self.created_at,
                assistant_id=self.assistant_id,
                thread_id=self.thread_id,
                status="completed",
                model=self.model,
                instructions=instructions,
                usage=TokenUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens
                )
            ).model_dump()
        )
