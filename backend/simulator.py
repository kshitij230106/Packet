"""Discrete-event network simulation engine for single-bottleneck QoS simulation.
"""

import heapq
from typing import Dict, List, Optional, Tuple
from backend.models import PacketEvent, SimulationConfig, TimeSeriesSample
from backend.packet import Packet
from backend.schedulers.base import BaseScheduler
from backend.schedulers.wfq import WFQScheduler

# Event Types
EVENT_ARRIVAL = 1
EVENT_TX_COMPLETE = 2


class SimulationEngine:
    """Discrete-event simulator modeling packet arrivals, queueing,

    serialization delays, drops, and link transmission.
    """

    def __init__(self, config: SimulationConfig, scheduler: BaseScheduler):
        self.config = config
        self.scheduler = scheduler
        self.link_capacity_bps = config.link_capacity_mbps * 1_000_000.0
        self.duration = config.simulation_duration_sec

        # State
        self.current_time = 0.0
        self.link_busy = False
        self.current_transmitting_packet: Optional[Packet] = None
        self.total_busy_time = 0.0

        # Collections
        self.transmitted_packets: List[Packet] = []
        self.dropped_packets: List[Packet] = []
        self.all_packets: List[Packet] = []

        # Time-series and event telemetry
        self.time_series: List[TimeSeriesSample] = []
        self.packet_events: List[PacketEvent] = []

        # Event queue: min-heap of (time, tiebreaker, event_type, data)
        self.event_queue: List[Tuple[float, int, int, any]] = []
        self._tiebreaker = 0

    def _push_event(self, time_sec: float, event_type: int, data: any) -> None:
        self._tiebreaker += 1
        heapq.heappush(self.event_queue, (time_sec, self._tiebreaker, event_type, data))

    def _record_time_sample(self, time_sec: float) -> None:
        """Capture queue occupancy and link status snapshot."""
        q_lengths = self.scheduler.get_queue_lengths()
        tx_class = self.current_transmitting_packet.traffic_class if self.current_transmitting_packet else None
        self.time_series.append(
            TimeSeriesSample(
                time_sec=round(time_sec, 4),
                queue_lengths=dict(q_lengths),
                total_queue_length=sum(q_lengths.values()),
                link_busy=self.link_busy,
                current_tx_class=tx_class,
            )
        )

    def _record_packet_event(
        self,
        time_sec: float,
        event_type: str,
        packet: Packet,
        detail: Optional[str] = None,
    ) -> None:
        """Record discrete packet event for frontend animation and playback."""
        # Limit event list to 1500 events to prevent massive payload over wire while keeping rich animation
        if len(self.packet_events) < 1500:
            self.packet_events.append(
                PacketEvent(
                    time_sec=round(time_sec, 5),
                    event_type=event_type,
                    packet_id=packet.packet_id,
                    traffic_class=packet.traffic_class,
                    size_bytes=packet.size_bytes,
                    queue_lengths=self.scheduler.get_queue_lengths(),
                    detail=detail,
                )
            )

    def run(self, packet_trace: List[Packet]) -> None:
        """Execute discrete-event simulation over the given packet trace."""
        self.scheduler.reset()
        self.current_time = 0.0
        self.link_busy = False
        self.current_transmitting_packet = None
        self.total_busy_time = 0.0
        self.transmitted_packets.clear()
        self.dropped_packets.clear()
        self.all_packets = list(packet_trace)
        self.time_series.clear()
        self.packet_events.clear()
        self.event_queue.clear()
        self._tiebreaker = 0

        # Enqueue all arrival events
        for packet in self.all_packets:
            self._push_event(packet.arrival_time, EVENT_ARRIVAL, packet)

        last_sample_time = 0.0
        sample_interval = 0.05  # Sample queue state every 50ms

        # Record initial state
        self._record_time_sample(0.0)

        # Discrete-event loop
        while self.event_queue:
            time_sec, _, event_type, data = heapq.heappop(self.event_queue)
            self.current_time = time_sec

            # Record periodic time series samples
            while last_sample_time + sample_interval <= self.current_time:
                last_sample_time += sample_interval
                self._record_time_sample(last_sample_time)

            if event_type == EVENT_ARRIVAL:
                packet: Packet = data
                self._handle_arrival(packet)
            elif event_type == EVENT_TX_COMPLETE:
                packet: Packet = data
                self._handle_tx_complete(packet)

        # Capture final state
        self._record_time_sample(self.current_time)

    def _handle_arrival(self, packet: Packet) -> None:
        """Process packet arrival event."""
        # 1. Emit arrival event
        self._record_packet_event(self.current_time, "arrival", packet, "Arrived at router")

        # 2. Attempt enqueue into scheduler
        accepted = self.scheduler.enqueue(packet, self.current_time)

        if not accepted:
            # Packet dropped due to full buffer
            self.dropped_packets.append(packet)
            self._record_packet_event(
                self.current_time,
                "dropped",
                packet,
                f"Dropped: {packet.drop_reason}",
            )
            return

        self._record_packet_event(self.current_time, "enqueued", packet, "Enqueued in buffer")

        # 3. If link is idle, immediately start transmitting next packet
        if not self.link_busy:
            self._schedule_next_transmission()

    def _schedule_next_transmission(self) -> None:
        """Select next packet from scheduler and schedule its transmission completion."""
        if not self.scheduler.has_packets():
            self.link_busy = False
            self.current_transmitting_packet = None
            if isinstance(self.scheduler, WFQScheduler):
                self.scheduler.set_transmitting_class(None, self.current_time)
            return

        next_packet = self.scheduler.dequeue(self.current_time)
        if next_packet is None:
            self.link_busy = False
            self.current_transmitting_packet = None
            if isinstance(self.scheduler, WFQScheduler):
                self.scheduler.set_transmitting_class(None, self.current_time)
            return

        # Serialization time: L (bits) / C (bps)
        serialization_time = (next_packet.size_bytes * 8.0) / self.link_capacity_bps
        next_packet.tx_start_time = self.current_time
        next_packet.tx_completion_time = self.current_time + serialization_time

        self.link_busy = True
        self.current_transmitting_packet = next_packet

        if isinstance(self.scheduler, WFQScheduler):
            self.scheduler.set_transmitting_class(next_packet.traffic_class, self.current_time)

        self._record_packet_event(
            self.current_time,
            "tx_start",
            next_packet,
            f"Serializing ({round(serialization_time * 1000, 2)} ms)",
        )

        # Schedule completion event
        self._push_event(next_packet.tx_completion_time, EVENT_TX_COMPLETE, next_packet)

    def _handle_tx_complete(self, packet: Packet) -> None:
        """Process transmission completion event."""
        # Serialization finished
        duration = packet.serialization_delay or 0.0
        self.total_busy_time += duration
        self.transmitted_packets.append(packet)

        self._record_packet_event(
            self.current_time,
            "tx_complete",
            packet,
            f"Transmitted in {round(packet.total_delay * 1000, 2)} ms total delay",
        )

        self.link_busy = False
        self.current_transmitting_packet = None

        # Look for next packet
        self._schedule_next_transmission()
