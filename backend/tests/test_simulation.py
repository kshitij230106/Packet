"""Unit tests for the discrete-event simulation engine.
"""

import pytest
from backend.models import SimulationConfig, TrafficClassConfig
from backend.packet import Packet
from backend.schedulers.fcfs import FCFSScheduler
from backend.simulator import SimulationEngine
from backend.traffic_generator import DEFAULT_CLASSES, TrafficGenerator


def test_serialization_delay_formula():
    """Serialization delay must be exactly L (bits) / C (bps)."""
    cfg = SimulationConfig(
        link_capacity_mbps=10.0,  # 10,000,000 bps
        simulation_duration_sec=2.0,
        random_seed=123,
        scheduler_type="fcfs",
        classes=DEFAULT_CLASSES,
    )
    scheduler = FCFSScheduler(cfg)
    engine = SimulationEngine(cfg, scheduler)

    # 1250 bytes = 10,000 bits. Over a 10,000,000 bps link, delay = 10,000 / 10,000,000 = 0.001 s (1 ms)
    p = Packet(packet_id="p1", traffic_class="video", arrival_time=0.1, size_bytes=1250)
    engine.run([p])

    assert len(engine.transmitted_packets) == 1
    tx_pkt = engine.transmitted_packets[0]
    expected_serialization = (1250 * 8.0) / 10_000_000.0  # 0.001 s
    assert pytest.approx(tx_pkt.serialization_delay, rel=1e-5) == expected_serialization
    assert pytest.approx(tx_pkt.tx_start_time, rel=1e-5) == 0.1
    assert pytest.approx(tx_pkt.tx_completion_time, rel=1e-5) == 0.101


def test_queue_overflow_drops():
    """Packets exceeding queue capacity must be marked as dropped."""
    classes = dict(DEFAULT_CLASSES)
    # Set tiny queue capacity of 2
    classes["file"] = TrafficClassConfig(
        name="file",
        display_name="File Downloads",
        enabled=True,
        arrival_rate_pps=50.0,
        packet_size_bytes=1000,
        priority=4,
        wfq_weight=1.0,
        queue_capacity=2,
    )
    cfg = SimulationConfig(
        link_capacity_mbps=1.0,  # Slow link (1 Mbps), transmission takes ~8ms
        simulation_duration_sec=2.0,
        random_seed=42,
        scheduler_type="fcfs",
        global_queue_capacity=2,
        classes=classes,
    )
    scheduler = FCFSScheduler(cfg)
    engine = SimulationEngine(cfg, scheduler)

    # 5 packets arriving within 4ms while packet 0 takes 8ms to transmit
    packets = [
        Packet(packet_id=f"p_{i}", traffic_class="file", arrival_time=0.001 * i, size_bytes=1000)
        for i in range(5)
    ]
    engine.run(packets)

    # First packet starts transmitting immediately, 2 buffer slots take p_1 and p_2, p_3 and p_4 drop!
    assert len(engine.dropped_packets) > 0
    for dropped in engine.dropped_packets:
        assert dropped.dropped is True
        assert dropped.drop_reason == "queue_overflow"


def test_reproducible_traffic_generation():
    """Same random seed must produce identical packet traces and timestamps."""
    cfg1 = SimulationConfig(
        link_capacity_mbps=10.0,
        simulation_duration_sec=3.0,
        random_seed=999,
        scheduler_type="fcfs",
        classes=DEFAULT_CLASSES,
    )
    cfg2 = SimulationConfig(
        link_capacity_mbps=10.0,
        simulation_duration_sec=3.0,
        random_seed=999,
        scheduler_type="fcfs",
        classes=DEFAULT_CLASSES,
    )

    gen1 = TrafficGenerator(cfg1)
    gen2 = TrafficGenerator(cfg2)

    trace1 = gen1.generate_trace()
    trace2 = gen2.generate_trace()

    assert len(trace1) == len(trace2)
    for p1, p2 in zip(trace1, trace2):
        assert p1.packet_id == p2.packet_id
        assert p1.traffic_class == p2.traffic_class
        assert pytest.approx(p1.arrival_time, abs=1e-8) == p2.arrival_time
        assert p1.size_bytes == p2.size_bytes


def test_higher_offered_load_produces_congestion():
    """Higher offered load relative to link capacity must increase queuing delay and buffer buildup."""
    # Low offered load on fast link
    cfg_low = SimulationConfig(
        link_capacity_mbps=50.0,
        simulation_duration_sec=3.0,
        random_seed=42,
        scheduler_type="fcfs",
        classes=DEFAULT_CLASSES,
    )
    # High offered load on congested bottleneck link
    cfg_high = SimulationConfig(
        link_capacity_mbps=2.0,
        simulation_duration_sec=3.0,
        random_seed=42,
        scheduler_type="fcfs",
        classes=DEFAULT_CLASSES,
    )

    gen = TrafficGenerator(cfg_low)
    trace = gen.generate_trace()

    sched_low = FCFSScheduler(cfg_low)
    eng_low = SimulationEngine(cfg_low, sched_low)
    eng_low.run(gen.clone_trace(trace))

    sched_high = FCFSScheduler(cfg_high)
    eng_high = SimulationEngine(cfg_high, sched_high)
    eng_high.run(gen.clone_trace(trace))

    avg_delay_low = sum(p.total_delay for p in eng_low.transmitted_packets) / len(eng_low.transmitted_packets)
    avg_delay_high = sum(p.total_delay for p in eng_high.transmitted_packets) / len(eng_high.transmitted_packets)

    # Congested link must exhibit noticeably higher average delay
    assert avg_delay_high > avg_delay_low * 2.0


def test_packet_accounting_integrity():
    """Every generated packet must be accounted for as transmitted or dropped, with no silent loss."""
    cfg = SimulationConfig(
        link_capacity_mbps=5.0,
        simulation_duration_sec=3.0,
        random_seed=77,
        scheduler_type="fcfs",
        classes=DEFAULT_CLASSES,
    )
    gen = TrafficGenerator(cfg)
    trace = gen.generate_trace()

    sched = FCFSScheduler(cfg)
    engine = SimulationEngine(cfg, sched)
    engine.run(trace)

    # All generated packets must either be transmitted or dropped
    assert len(engine.transmitted_packets) + len(engine.dropped_packets) == len(engine.all_packets)

    # Every transmitted packet must have tx_start_time < tx_completion_time
    for p in engine.transmitted_packets:
        assert p.tx_start_time is not None
        assert p.tx_completion_time is not None
        assert p.tx_completion_time > p.tx_start_time
        assert p.dropped is False

