"""Traffic generator for generating reproducible discrete network packet traces.
"""

import math
import random
from typing import Dict, List, Optional
from backend.models import SimulationConfig, TrafficClassConfig
from backend.packet import Packet


DEFAULT_CLASSES: Dict[str, TrafficClassConfig] = {
    "emergency": TrafficClassConfig(
        name="emergency",
        display_name="Emergency Messages",
        enabled=True,
        arrival_rate_pps=8.0,
        packet_size_bytes=128,
        packet_size_jitter_bytes=24,
        priority=1,
        wfq_weight=4.0,
        queue_capacity=30,
    ),
    "video": TrafficClassConfig(
        name="video",
        display_name="Video Calls",
        enabled=True,
        arrival_rate_pps=100.0,
        packet_size_bytes=960,
        packet_size_jitter_bytes=140,
        priority=2,
        wfq_weight=3.0,
        queue_capacity=60,
    ),
    "gaming": TrafficClassConfig(
        name="gaming",
        display_name="Online Gaming",
        enabled=True,
        arrival_rate_pps=140.0,
        packet_size_bytes=84,
        packet_size_jitter_bytes=20,
        priority=3,
        wfq_weight=2.0,
        queue_capacity=50,
    ),
    "file": TrafficClassConfig(
        name="file",
        display_name="File Downloads",
        enabled=True,
        arrival_rate_pps=220.0,
        packet_size_bytes=1440,
        packet_size_jitter_bytes=60,
        priority=4,
        wfq_weight=1.0,
        queue_capacity=80,
    ),
}


class TrafficGenerator:
    """Generates synthetic packet arrivals using Poisson arrival processes

    and configurable packet size distributions.
    """

    def __init__(self, config: SimulationConfig):
        self.config = config
        self.rng = random.Random(config.random_seed)

    def generate_trace(self) -> List[Packet]:
        """Generate a combined, time-ordered packet trace across all enabled classes.

        Returns:
            List[Packet] sorted ascending by arrival_time.
        """
        all_packets: List[Packet] = []

        for class_name, class_cfg in self.config.classes.items():
            if not class_cfg.enabled:
                continue

            current_time = 0.0
            packet_index = 0
            rate = class_cfg.arrival_rate_pps

            while current_time < self.config.simulation_duration_sec:
                # Exponential inter-arrival time: delta_t = -ln(1 - U) / lambda
                # We use random.Random.expovariate(rate)
                inter_arrival = self.rng.expovariate(rate)
                current_time += inter_arrival

                if current_time > self.config.simulation_duration_sec:
                    break

                packet_index += 1
                packet_id = f"pkt_{class_name}_{packet_index}"

                # Calculate packet size with jitter
                size = class_cfg.packet_size_bytes
                if class_cfg.packet_size_jitter_bytes > 0:
                    jitter = self.rng.randint(
                        -class_cfg.packet_size_jitter_bytes,
                        class_cfg.packet_size_jitter_bytes
                    )
                    size += jitter

                # Constrain to realistic network packet boundaries (40B TCP/IP min up to 1500B standard MTU)
                size = max(40, min(1500, size))

                packet = Packet(
                    packet_id=packet_id,
                    traffic_class=class_name,
                    arrival_time=current_time,
                    size_bytes=size,
                )
                all_packets.append(packet)

        # Sort all packets globally by arrival time to emulate physical arrival sequence
        all_packets.sort(key=lambda p: p.arrival_time)
        return all_packets

    @staticmethod
    def clone_trace(trace: List[Packet]) -> List[Packet]:
        """Deep clone a packet trace so it can be replayed identically across multiple schedulers."""
        return [p.clone() for p in trace]
