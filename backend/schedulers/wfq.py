"""Weighted Fair Queuing (WFQ) Scheduler.

Implements packetized fair queuing (PGPS / WFQ) using virtual finish times.
Flows receive service proportional to their configured weights while normalizing
for packet sizes, preventing bulk flows from monopolizing link bandwidth.
"""

from collections import deque
from typing import Dict, List, Optional
from backend.models import SimulationConfig
from backend.packet import Packet
from backend.schedulers.base import BaseScheduler


class WFQScheduler(BaseScheduler):
    """Packet-by-packet Weighted Fair Queuing (WFQ / PGPS) scheduler.

    Mathematical Foundation:
    1. Generalized Processor Sharing (GPS) virtual time progression:
       dV/dt = 1 / sum_{j in B(t)} w_j
       where B(t) is the set of currently backlogged (active) flows, and w_j is flow weight.

    2. Virtual start and finish times for packet k of flow i:
       S_i^k = max(F_i^{k-1}, V(a_i^k))
       F_i^k = S_i^k + (L_i^k / w_i)
       where L_i^k is packet size in bytes and w_i is flow weight.

    3. Selection rule:
       Whenever the bottleneck link is free, select the head-of-line packet with the
       smallest virtual finish time F_i^k among all non-empty queues.
    """

    def __init__(self, config: SimulationConfig):
        super().__init__(config)
        # Flow queues: class_name -> deque[Packet]
        self.queues: Dict[str, deque[Packet]] = {
            name: deque() for name in self.class_configs.keys()
        }
        # Flow weights
        self.weights: Dict[str, float] = {
            name: max(0.001, cfg.wfq_weight) for name, cfg in self.class_configs.items()
        }
        # Last virtual finish time for each flow: class_name -> float
        self.last_finish_time: Dict[str, float] = {
            name: 0.0 for name in self.class_configs.keys()
        }
        # Virtual time state
        self.link_capacity_bytes_per_sec = (config.link_capacity_mbps * 1_000_000.0) / 8.0
        self.virtual_time: float = 0.0
        self.last_vtime_update: float = 0.0
        # Flow actively transmitting on the link (if any)
        self.active_transmitting_class: Optional[str] = None

    @property
    def name(self) -> str:
        return "Weighted Fair Queuing (WFQ)"

    @property
    def description(self) -> str:
        return (
            "Allocates bandwidth in proportion to configured weights (w_i) while normalizing "
            "for packet lengths (L_i). Head-of-line packets are served in order of smallest "
            "virtual finish time F_i = max(F_{i,prev}, V(a_i)) + (L_i / w_i)."
        )

    def reset(self) -> None:
        for q in self.queues.values():
            q.clear()
        for name in self.last_finish_time.keys():
            self.last_finish_time[name] = 0.0
        self.virtual_time = 0.0
        self.last_vtime_update = 0.0
        self.active_transmitting_class = None

    def _get_active_classes(self) -> List[str]:
        """A flow is backlogged if it has packets queued or is currently transmitting."""
        active = [name for name, q in self.queues.items() if len(q) > 0]
        if self.active_transmitting_class and self.active_transmitting_class not in active:
            active.append(self.active_transmitting_class)
        return active

    def _update_virtual_time(self, current_time: float) -> None:
        """Advance virtual time V(t) based on elapsed real time and active weights.
        Rate: dV/dt = C_bytes_per_sec / sum_{j in B(t)} w_j
        Ensures virtual time rounds match packet size units (bytes).
        """
        if current_time <= self.last_vtime_update:
            return

        dt = current_time - self.last_vtime_update
        active_classes = self._get_active_classes()

        if active_classes:
            sum_active_weights = sum(self.weights[c] for c in active_classes)
            if sum_active_weights > 0:
                self.virtual_time += (self.link_capacity_bytes_per_sec * dt) / sum_active_weights

        self.last_vtime_update = current_time

    def set_transmitting_class(self, cls_name: Optional[str], current_time: float) -> None:
        """Notify scheduler of currently transmitting flow to maintain GPS backlog set."""
        self._update_virtual_time(current_time)
        self.active_transmitting_class = cls_name

    def enqueue(self, packet: Packet, current_time: float) -> bool:
        self._update_virtual_time(current_time)
        cls_name = packet.traffic_class

        if cls_name not in self.queues:
            self.queues[cls_name] = deque()
            self.weights[cls_name] = 1.0
            self.last_finish_time[cls_name] = 0.0

        queue = self.queues[cls_name]
        cfg = self.class_configs.get(cls_name)
        capacity = cfg.queue_capacity if cfg else 50

        # Buffer capacity check
        if len(queue) >= capacity:
            packet.dropped = True
            packet.drop_reason = "queue_overflow"
            return False

        # Calculate virtual start and finish times
        weight = self.weights[cls_name]
        prev_finish = self.last_finish_time[cls_name]

        # S_i^k = max(F_i^{k-1}, V(a_i^k))
        virtual_start = max(prev_finish, self.virtual_time)
        # F_i^k = S_i^k + (L_i / w_i)
        virtual_finish = virtual_start + (packet.size_bytes / weight)

        packet.queue_entry_time = current_time
        packet.virtual_start_time = virtual_start
        packet.virtual_finish_time = virtual_finish

        # Update last finish time for this flow
        self.last_finish_time[cls_name] = virtual_finish

        queue.append(packet)
        return True

    def dequeue(self, current_time: float) -> Optional[Packet]:
        self._update_virtual_time(current_time)

        # Candidate selection: look at head-of-line packet from each non-empty queue
        candidate_class: Optional[str] = None
        min_finish_time: float = float("inf")

        for cls_name, queue in self.queues.items():
            if queue:
                head_pkt = queue[0]
                finish_time = head_pkt.virtual_finish_time
                if finish_time is not None and finish_time < min_finish_time:
                    min_finish_time = finish_time
                    candidate_class = cls_name

        if candidate_class is not None:
            pkt = self.queues[candidate_class].popleft()
            return pkt

        return None

    def has_packets(self) -> bool:
        return any(len(q) > 0 for q in self.queues.values())

    def get_queue_lengths(self) -> Dict[str, int]:
        return {name: len(q) for name, q in self.queues.items()}

    def get_total_queue_length(self) -> int:
        return sum(len(q) for q in self.queues.values())
