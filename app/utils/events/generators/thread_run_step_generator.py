# Typing
from typing import Generator
# Base generator
from .base_generator import BaseEventGenerator
# Event
from ..sse_formatter import sse_event
# Schemas
from app.schemas.runs import RunStepObject, StepDetails, MessageCreation, TokenUsage

class ThreadRunStepEventGenerator(BaseEventGenerator):
    """Generator for ThreadRunStep events."""
    
    def __init__(self, thread_id: str, run_id: str, assistant_id: str, step_id: str, message_id: str):
        super().__init__(thread_id, run_id, assistant_id)
        self.step_id = step_id
        self.message_id = message_id
    
    def generate_events(self) -> Generator[str, None, None]:
        """Generate thread run step lifecycle events: created, in_progress."""
        yield self._created_event()
        yield self._in_progress_event()
    
    def _created_event(self) -> str:
        """Generate step created event."""
        return sse_event(
            event="thread.run.step.created",
            data=RunStepObject(
                id=self.step_id,
                created_at=self.created_at,
                expired_at=self.created_at,
                run_id=self.run_id,
                assistant_id=self.assistant_id,
                thread_id=self.thread_id,
                status="in_progress",
                step_details=StepDetails(
                    message_creation=MessageCreation(message_id=self.message_id)
                )
            ).model_dump()
        )
    
    def _in_progress_event(self) -> str:
        """Generate step in_progress event."""
        return sse_event(
            event="thread.run.step.in_progress",
            data=RunStepObject(
                id=self.step_id,
                created_at=self.created_at,
                expired_at=self.created_at,
                run_id=self.run_id,
                assistant_id=self.assistant_id,
                thread_id=self.thread_id,
                status="in_progress",
                step_details=StepDetails(
                    message_creation=MessageCreation(message_id=self.message_id)
                )
            ).model_dump()
        )
    
    def completed_event(self, prompt_tokens: int, completion_tokens: int) -> str:
        """Generate step completed event."""
        return sse_event(
            event="thread.run.step.completed",
            data=RunStepObject(
                id=self.step_id,
                created_at=self.created_at,
                expired_at=self.created_at,
                run_id=self.run_id,
                assistant_id=self.assistant_id,
                thread_id=self.thread_id,
                status="completed",
                step_details=StepDetails(
                    message_creation=MessageCreation(message_id=self.message_id)
                ),
                usage=TokenUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens
                )
            ).model_dump()
        )
