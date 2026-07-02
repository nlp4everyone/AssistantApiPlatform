# Typing
from typing import Generator
# Base generator
from .base_generator import BaseEventGenerator
# Event
from ..sse_formatter import sse_event
# Schemas
from app.schemas.runs import MessageDeltaEvent, MessageDelta, TextDeltaBlock, TextDelta
from app.schemas.messages.base import MessageObject
from app.schemas.messages.models import ContentItem, MessageTextContent
# Other components
import time

class ThreadMessageEventGenerator(BaseEventGenerator):
    """Generator for message lifecycle events."""
    
    def __init__(self, thread_id: str, run_id: str, assistant_id: str, message_id: str):
        super().__init__(thread_id, run_id, assistant_id)
        self.message_id = message_id
    
    def generate_events(self) -> Generator[str, None, None]:
        """Generate thread message lifecycle events: created, in_progress."""
        yield self._created_event()
        yield self._in_progress_event()
    
    def _created_event(self) -> str:
        return sse_event(
            event="thread.message.created",
            data=MessageObject(
                id=self.message_id,
                created_at=self.created_at,
                assistant_id=self.assistant_id,
                thread_id=self.thread_id,
                run_id=self.run_id,
                role="assistant",
                content=[],
                status="in_progress"
            ).model_dump()
        )

    def _in_progress_event(self) -> str:
        return sse_event(
            event="thread.message.in_progress",
            data=MessageObject(
                id=self.message_id,
                created_at=self.created_at,
                assistant_id=self.assistant_id,
                thread_id=self.thread_id,
                run_id=self.run_id,
                role="assistant",
                content=[],
                status="in_progress"
            ).model_dump()
        )
    
    def delta_event(self, content: str) -> str:
        """Generate message delta event for streaming content."""
        return sse_event(
            event="thread.message.delta",
            data=MessageDeltaEvent(
                id=self.message_id,
                delta=MessageDelta(content=[
                    TextDeltaBlock(
                        index=0,
                        text=TextDelta(value=content)
                    )
                ])
            ).model_dump()
        )
    
    def completed_event(self, content: str) -> str:
        """Generate message completed event in MessageObject format."""
        return sse_event(
            event="thread.message.completed",
            data=MessageObject(
                id=self.message_id,
                created_at=self.created_at,
                thread_id=self.thread_id,
                role="assistant",
                content=[ContentItem(
                    type="text",
                    text=MessageTextContent(value=content)
                )],
                assistant_id=self.assistant_id,
                run_id=self.run_id,
                completed_at=int(time.time()),
                status="completed"
            ).model_dump()
        )
