"""Abstract base class for all network queue scheduling algorithms.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional
from backend.models import SimulationConfig
from backend.packet import Packet


class BaseScheduler(ABC):
    """Common interface for packet schedulers."""

    def __init__(self, config: SimulationConfig):
        self.config = config
        self.class_configs = config.classes
        self.global_queue_capacity = config.global_queue_capacity

    @property
    @abstractmethod
    def name(self) -> str:
        """Display name of the algorithm."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Short educational description of how the algorithm operates."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Clear all internal queues and state."""
        pass

    @abstractmethod
    def enqueue(self, packet: Packet, current_time: float) -> bool:
        """Attempt to enqueue a newly arrived packet.

        Returns:
            True if packet was accepted into queue, False if dropped due to queue overflow.
        """
        pass

    @abstractmethod
    def dequeue(self, current_time: float) -> Optional[Packet]:
        """Select and remove the next packet to transmit based on the scheduling policy.

        Returns:
            Packet to transmit, or None if queues are empty.
        """
        pass

    @abstractmethod
    def has_packets(self) -> bool:
        """Whether there are any packets waiting in the scheduler."""
        pass

    @abstractmethod
    def get_queue_lengths(self) -> Dict[str, int]:
        """Current packet count per traffic class queue."""
        pass

    @abstractmethod
    def get_total_queue_length(self) -> int:
        """Total number of packets currently buffered in the scheduler."""
        pass
