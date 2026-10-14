"""Strict Priority Scheduler.

Maintains distinct FIFO queues for each traffic class ordered by priority.
Always dispatches packets from the highest-priority non-empty queue,
which can cause starvation of lower-priority traffic if high-priority flows are heavy.
"""

from collections import deque
from typing import Dict, List, Optional, Tuple
from backend.models import SimulationConfig
from backend.packet import Packet
from backend.schedulers.base import BaseScheduler


class StrictPriorityScheduler(BaseScheduler):
    """Strict Priority packet scheduler.

    Educational Characteristics:
    - Excellent low latency for mission-critical traffic (Emergency Messages, Video).
    - High starvation risk: Low priority queues (e.g. File Downloads) receive ZERO service
      as long as any higher-priority queue has queued packets.
    """

    def __init__(self, config: SimulationConfig):
        super().__init__(config)
        # Dictionary of class_name -> deque[Packet]
        self.queues: Dict[str, deque[Packet]] = {
            name: deque() for name in self.class_configs.keys()
        }
        # Pre-sort classes by priority: 1 is highest priority, 10 is lowest
        # Stored as list of (class_name, priority)
        self.priority_order: List[Tuple[str, int]] = sorted(
            [(name, cfg.priority) for name, cfg in self.class_configs.items()],
            key=lambda item: item[1]
        )

    @property
    def name(self) -> str:
        return "Strict Priority Scheduling"

    @property
    def description(self) -> str:
        return (
            "Serves packets from the highest-priority non-empty queue first. "
            "Guarantees minimum latency for critical traffic, but can starve lower-priority traffic."
        )

    def reset(self) -> None:
        for q in self.queues.values():
            q.clear()

    def enqueue(self, packet: Packet, current_time: float) -> bool:
        cls_name = packet.traffic_class
        if cls_name not in self.queues:
            self.queues[cls_name] = deque()

        queue = self.queues[cls_name]
        cfg = self.class_configs.get(cls_name)
        capacity = cfg.queue_capacity if cfg else 50

        # Enforce per-queue buffer limit
        if len(queue) >= capacity:
            packet.dropped = True
            packet.drop_reason = "queue_overflow"
            return False

        packet.queue_entry_time = current_time
        queue.append(packet)
        return True

    def dequeue(self, current_time: float) -> Optional[Packet]:
        # Inspect queues in strict priority order (lowest numerical value first)
        for cls_name, _ in self.priority_order:
            q = self.queues.get(cls_name)
            if q and len(q) > 0:
                return q.popleft()
        return None

    def has_packets(self) -> bool:
        return any(len(q) > 0 for q in self.queues.values())

    def get_queue_lengths(self) -> Dict[str, int]:
        return {name: len(q) for name, q in self.queues.items()}

    def get_total_queue_length(self) -> int:
        return sum(len(q) for q in self.queues.values())
