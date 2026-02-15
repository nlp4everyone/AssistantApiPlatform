from abc import ABC, abstractmethod
from typing import Generator
import time


class BaseEventGenerator(ABC):
    """Base class for all event generators."""
    
    def __init__(self, thread_id: str, run_id: str, assistant_id: str):
        self.thread_id = thread_id
        self.run_id = run_id
        self.assistant_id = assistant_id
        self.created_at = int(time.time())
    
    @abstractmethod
    def generate_events(self) -> Generator[str, None, None]:
        """Generate all events for this type."""
        pass
