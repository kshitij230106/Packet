"""Unit tests for FCFS, Strict Priority, and WFQ scheduling algorithms.
"""

import pytest
from backend.models import SimulationConfig
from backend.packet import Packet
from backend.schedulers.fcfs import FCFSScheduler
from backend.schedulers.strict_priority import StrictPriorityScheduler
from backend.schedulers.wfq import WFQScheduler
from backend.traffic_generator import DEFAULT_CLASSES


@pytest.fixture
def base_config():
    return SimulationConfig(
        link_capacity_mbps=10.0,
        simulation_duration_sec=5.0,
        random_seed=42,
        scheduler_type="fcfs",
        classes=DEFAULT_CLASSES,
    )


def test_fcfs_preserves_arrival_order(base_config):
    """FCFS must dequeue packets in the exact order they arrived, regardless of traffic class."""
    scheduler = FCFSScheduler(base_config)

    p1 = Packet(packet_id="p1", traffic_class="file", arrival_time=1.0, size_bytes=1000)
    p2 = Packet(packet_id="p2", traffic_class="emergency", arrival_time=1.1, size_bytes=100)
    p3 = Packet(packet_id="p3", traffic_class="video", arrival_time=1.2, size_bytes=800)

    assert scheduler.enqueue(p1, 1.0) is True
    assert scheduler.enqueue(p2, 1.1) is True
    assert scheduler.enqueue(p3, 1.2) is True

    assert scheduler.dequeue(1.3).packet_id == "p1"
    assert scheduler.dequeue(1.4).packet_id == "p2"
    assert scheduler.dequeue(1.5).packet_id == "p3"
    assert scheduler.dequeue(1.6) is None


def test_strict_priority_dispatches_highest_priority_first(base_config):
    """Strict Priority must always serve the highest priority queue first (Emergency:1 > Video:2 > Gaming:3 > File:4)."""
    scheduler = StrictPriorityScheduler(base_config)

    # Arriving in reverse priority order: File arrived first, then Gaming, Video, Emergency
    p_file = Packet(packet_id="p_file", traffic_class="file", arrival_time=0.1, size_bytes=1000)
    p_game = Packet(packet_id="p_game", traffic_class="gaming", arrival_time=0.2, size_bytes=100)
    p_vid = Packet(packet_id="p_vid", traffic_class="video", arrival_time=0.3, size_bytes=800)
    p_em = Packet(packet_id="p_em", traffic_class="emergency", arrival_time=0.4, size_bytes=120)

    scheduler.enqueue(p_file, 0.1)
    scheduler.enqueue(p_game, 0.2)
    scheduler.enqueue(p_vid, 0.3)
    scheduler.enqueue(p_em, 0.4)

    # Dequeue must yield emergency (priority 1), then video (2), gaming (3), file (4)
    assert scheduler.dequeue(0.5).packet_id == "p_em"
    assert scheduler.dequeue(0.5).packet_id == "p_vid"
    assert scheduler.dequeue(0.5).packet_id == "p_game"
    assert scheduler.dequeue(0.5).packet_id == "p_file"
    assert scheduler.dequeue(0.5) is None


def test_strict_priority_starvation(base_config):
    """Continuous high-priority arrivals prevent lower-priority queue from being served."""
    scheduler = StrictPriorityScheduler(base_config)

    p_file = Packet(packet_id="p_file", traffic_class="file", arrival_time=0.1, size_bytes=1400)
    scheduler.enqueue(p_file, 0.1)

    # Now continuously arrive high-priority emergency packets
    p_em1 = Packet(packet_id="p_em1", traffic_class="emergency", arrival_time=0.2, size_bytes=100)
    p_em2 = Packet(packet_id="p_em2", traffic_class="emergency", arrival_time=0.3, size_bytes=100)
    scheduler.enqueue(p_em1, 0.2)
    scheduler.enqueue(p_em2, 0.3)

    first_served = scheduler.dequeue(0.4)
    second_served = scheduler.dequeue(0.4)

    assert first_served.packet_id == "p_em1"
    assert second_served.packet_id == "p_em2"
    # File is still waiting in queue (starved)
    assert scheduler.get_queue_lengths()["file"] == 1


def test_wfq_considers_weights_and_sizes(base_config):
    """WFQ must serve packets according to virtual finish times based on size and weight."""
    scheduler = WFQScheduler(base_config)

    # Emergency: weight 4.0; Gaming: weight 2.0; File: weight 1.0
    # Two identical size packets (e.g. 400 bytes): Emergency should finish before File
    p_em = Packet(packet_id="p_em", traffic_class="emergency", arrival_time=0.0, size_bytes=400)
    p_file = Packet(packet_id="p_file", traffic_class="file", arrival_time=0.0, size_bytes=400)

    scheduler.enqueue(p_file, 0.0)
    scheduler.enqueue(p_em, 0.0)

    # Emergency: virtual finish = 0 + 400 / 4 = 100
    # File: virtual finish = 0 + 400 / 1 = 400
    # So Emergency should be dequeued first!
    served1 = scheduler.dequeue(0.0)
    served2 = scheduler.dequeue(0.0)

    assert served1.packet_id == "p_em"
    assert served2.packet_id == "p_file"


def test_wfq_packet_size_normalization(base_config):
    """A smaller packet with equal weight should finish before a much larger packet."""
    scheduler = WFQScheduler(base_config)

    # Both file class (weight 1.0): small packet (100B) vs large packet (1000B) in separate queues or arrivals
    # Let's test Video (weight 3) with 1500B vs Gaming (weight 2) with 100B
    # Video finish: 0 + 1500 / 3 = 500
    # Gaming finish: 0 + 100 / 2 = 50
    # Gaming finishes first!
    p_vid = Packet(packet_id="p_vid", traffic_class="video", arrival_time=0.0, size_bytes=1500)
    p_game = Packet(packet_id="p_game", traffic_class="gaming", arrival_time=0.0, size_bytes=100)

    scheduler.enqueue(p_vid, 0.0)
    scheduler.enqueue(p_game, 0.0)

    assert scheduler.dequeue(0.0).packet_id == "p_game"
    assert scheduler.dequeue(0.0).packet_id == "p_vid"


def test_strict_priority_capacity_overflow(base_config):
    """Strict Priority must reject packets when a class queue reaches its configured capacity."""
    scheduler = StrictPriorityScheduler(base_config)
    cap = base_config.classes["emergency"].queue_capacity  # 30

    # Fill queue to capacity
    for i in range(cap):
        p = Packet(packet_id=f"p_{i}", traffic_class="emergency", arrival_time=0.1, size_bytes=100)
        assert scheduler.enqueue(p, 0.1) is True

    # Next packet must be rejected and marked dropped
    overflow_p = Packet(packet_id="overflow", traffic_class="emergency", arrival_time=0.2, size_bytes=100)
    assert scheduler.enqueue(overflow_p, 0.2) is False
    assert overflow_p.dropped is True
    assert overflow_p.drop_reason == "queue_overflow"


def test_wfq_capacity_overflow(base_config):
    """WFQ must drop packets when an individual flow queue exceeds its queue limit."""
    scheduler = WFQScheduler(base_config)
    cap = base_config.classes["video"].queue_capacity  # 60

    for i in range(cap):
        p = Packet(packet_id=f"v_{i}", traffic_class="video", arrival_time=0.1, size_bytes=500)
        assert scheduler.enqueue(p, 0.1) is True

    overflow_p = Packet(packet_id="v_overflow", traffic_class="video", arrival_time=0.2, size_bytes=500)
    assert scheduler.enqueue(overflow_p, 0.2) is False
    assert overflow_p.dropped is True
    assert overflow_p.drop_reason == "queue_overflow"


def test_scheduler_reset_clears_state(base_config):
    """Calling reset() on any scheduler must clear all buffers and restore clean state."""
    for SchedClass in [FCFSScheduler, StrictPriorityScheduler, WFQScheduler]:
        sched = SchedClass(base_config)
        p = Packet(packet_id="p1", traffic_class="gaming", arrival_time=0.1, size_bytes=100)
        sched.enqueue(p, 0.1)
        assert sched.has_packets() is True
        assert sched.get_total_queue_length() == 1

        sched.reset()
        assert sched.has_packets() is False
        assert sched.get_total_queue_length() == 0
        assert sched.dequeue(0.2) is None

