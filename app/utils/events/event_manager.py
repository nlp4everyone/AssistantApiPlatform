from typing import Generator
from .generators import ThreadRunEventGenerator, ThreadMessageEventGenerator, ThreadRunStepEventGenerator
from .sse_formatter import sse_event


class EventManager:
    """Manager class to coordinate all event generators."""
    
    def __init__(self, thread_id: str, run_id: str, assistant_id: str, 
                 message_id: str, step_id: str, model: str):
        self.thread_run = ThreadRunEventGenerator(thread_id, run_id, assistant_id, model)
        self.thread_message = ThreadMessageEventGenerator(thread_id, run_id, assistant_id, message_id)
        self.thread_run_step = ThreadRunStepEventGenerator(thread_id, run_id, assistant_id, step_id, message_id)
    
    def generate_all_lifecycle_events(self) -> Generator[str, None, None]:
        """Generate all initial lifecycle events in correct order."""
        # Thread run events first
        for event in self.thread_run.generate_events():
            yield event

        # Thread run step events
        for event in self.thread_run_step.generate_events():
            yield event
        
        # thread message events
        for event in self.thread_message.generate_events():
            yield event
    
    def get_delta_event(self, content: str) -> str:
        """Get message delta event."""
        return self.thread_message.delta_event(content)
    
    def get_message_completed_event(self, content: str) -> str:
        """Get message completed event."""
        return self.thread_message.completed_event(content)
    
    def get_step_completed_event(self, prompt_tokens: int, completion_tokens: int) -> str:
        """Get step completed event."""
        return self.thread_run_step.completed_event(prompt_tokens, completion_tokens)
    
    def get_run_completed_event(self, instructions: str, prompt_tokens: int, completion_tokens: int) -> str:
        """Get run completed event."""
        return self.thread_run.completed_event(instructions, prompt_tokens, completion_tokens)
    
    def get_done_event(self) -> str:
        """Get final done event to signal completion."""
        return sse_event(event="done", data="[DONE]")
