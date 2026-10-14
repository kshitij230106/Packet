"""Packet data structure representing discrete network packets in the simulation.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Packet:
    """Represents an individual discrete network packet.

    Attributes:
        packet_id: Unique identifier for the packet (e.g., 'p_video_10').
        traffic_class: Class identifier ('emergency', 'video', 'gaming', 'file').
        arrival_time: Timestamp (in simulated seconds) when packet arrives at the router.
        size_bytes: Size of the packet in bytes.
        queue_entry_time: Timestamp when packet enters the scheduler queue.
        tx_start_time: Timestamp when transmission begins on the bottleneck link.
        tx_completion_time: Timestamp when transmission finishes.
        dropped: Flag indicating if the packet was dropped.
        drop_reason: Reason for drop (e.g., 'queue_overflow', 'buffer_exhausted').
        virtual_start_time: Virtual start time computed by fair queuing schedulers.
        virtual_finish_time: Virtual finish time computed by fair queuing schedulers.
    """
    packet_id: str
    traffic_class: str
    arrival_time: float
    size_bytes: int
    queue_entry_time: Optional[float] = None
    tx_start_time: Optional[float] = None
    tx_completion_time: Optional[float] = None
    dropped: bool = False
    drop_reason: Optional[str] = None
    virtual_start_time: Optional[float] = None
    virtual_finish_time: Optional[float] = None

    @property
    def size_bits(self) -> int:
        """Packet size in bits."""
        return self.size_bytes * 8

    @property
    def queuing_delay(self) -> Optional[float]:
        """Time spent waiting in the queue in seconds."""
        if self.tx_start_time is not None and self.queue_entry_time is not None:
            return max(0.0, self.tx_start_time - self.queue_entry_time)
        return None

    @property
    def serialization_delay(self) -> Optional[float]:
        """Transmission/serialization time over the link in seconds."""
        if self.tx_completion_time is not None and self.tx_start_time is not None:
            return max(0.0, self.tx_completion_time - self.tx_start_time)
        return None

    @property
    def total_delay(self) -> Optional[float]:
        """Total end-to-end simulated delay (arrival to completion) in seconds."""
        if self.tx_completion_time is not None:
            return max(0.0, self.tx_completion_time - self.arrival_time)
        return None

    def clone(self) -> "Packet":
        """Create a fresh copy of the packet for replaying across different schedulers."""
        return Packet(
            packet_id=self.packet_id,
            traffic_class=self.traffic_class,
            arrival_time=self.arrival_time,
            size_bytes=self.size_bytes,
            queue_entry_time=None,
            tx_start_time=None,
            tx_completion_time=None,
            dropped=False,
            drop_reason=None,
            virtual_start_time=None,
            virtual_finish_time=None,
        )

    def to_dict(self) -> dict:
        """Serialize packet representation for API responses and visual traces."""
        return {
            "packet_id": self.packet_id,
            "traffic_class": self.traffic_class,
            "arrival_time": round(self.arrival_time, 6),
            "size_bytes": self.size_bytes,
            "queue_entry_time": round(self.queue_entry_time, 6) if self.queue_entry_time is not None else None,
            "tx_start_time": round(self.tx_start_time, 6) if self.tx_start_time is not None else None,
            "tx_completion_time": round(self.tx_completion_time, 6) if self.tx_completion_time is not None else None,
            "dropped": self.dropped,
            "drop_reason": self.drop_reason,
            "queuing_delay_ms": round(self.queuing_delay * 1000.0, 3) if self.queuing_delay is not None else None,
            "total_delay_ms": round(self.total_delay * 1000.0, 3) if self.total_delay is not None else None,
        }
