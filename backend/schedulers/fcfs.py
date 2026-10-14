"""First-Come First-Served (FCFS) Scheduler.

A single FIFO queue serves packets strictly in the order they arrived,
regardless of traffic priority or flow weight.
"""

from collections import deque
from typing import Dict, Optional
from backend.models import SimulationConfig
from backend.packet import Packet
from backend.schedulers.base import BaseScheduler


class FCFSScheduler(BaseScheduler):
    """First-Come First-Served (FIFO) packet scheduler.

    Educational Characteristics:
    - Zero flow isolation: High-volume flows (such as File Downloads) fill up the shared
      queue and impose massive queuing delay (bufferbloat) on latency-sensitive flows
      like Video and Gaming.
    - Simplest implementation, but completely blind to QoS priorities.
    """

    def __init__(self, config: SimulationConfig):
        super().__init__(config)
        self.queue: deque[Packet] = deque()
        # Compute aggregate default capacity from classes if global is not explicitly given
        if self.global_queue_capacity is not None:
            self.max_capacity = self.global_queue_capacity
        else:
            self.max_capacity = sum(c.queue_capacity for c in self.class_configs.values())

    @property
    def name(self) -> str:
        return "First-Come First-Served (FCFS)"

    @property
    def description(self) -> str:
        return (
            "Serves packets strictly in arrival order from a unified FIFO queue. "
            "No prioritization or flow isolation is applied."
        )

    def reset(self) -> None:
        self.queue.clear()

    def enqueue(self, packet: Packet, current_time: float) -> bool:
        # Check buffer capacity
        if len(self.queue) >= self.max_capacity:
            packet.dropped = True
            packet.drop_reason = "queue_overflow"
            return False

        packet.queue_entry_time = current_time
        self.queue.append(packet)
        return True

    def dequeue(self, current_time: float) -> Optional[Packet]:
        if not self.queue:
            return None
        return self.queue.popleft()

    def has_packets(self) -> bool:
        return len(self.queue) > 0

    def get_queue_lengths(self) -> Dict[str, int]:
        counts: Dict[str, int] = {c: 0 for c in self.class_configs.keys()}
        for p in self.queue:
            counts[p.traffic_class] = counts.get(p.traffic_class, 0) + 1
        return counts

    def get_total_queue_length(self) -> int:
        return len(self.queue)
