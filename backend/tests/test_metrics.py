"""Unit tests for metrics computation and Jain's Fairness Index.
"""

import pytest
from backend.metrics import calculate_jains_fairness_index, compute_simulation_metrics
from backend.models import SimulationConfig
from backend.packet import Packet
from backend.schedulers.fcfs import FCFSScheduler
from backend.traffic_generator import DEFAULT_CLASSES


def test_jains_fairness_equal_allocation():
    """Equal throughput allocation across all flows must yield Jain's Index of 1.0."""
    values = [5.0, 5.0, 5.0, 5.0]
    fairness = calculate_jains_fairness_index(values)
    assert pytest.approx(fairness, rel=1e-5) == 1.0


def test_jains_fairness_extreme_unfairness():
    """Single flow receiving everything while 3 receive nothing yields 1 / n = 0.25."""
    values = [10.0, 0.0, 0.0, 0.0]
    fairness = calculate_jains_fairness_index(values)
    assert pytest.approx(fairness, rel=1e-5) == 0.25


def test_jains_fairness_zero_safety():
    """Empty list or all-zero allocations must safely return 1.0 without dividing by zero."""
    assert calculate_jains_fairness_index([]) == 1.0
    assert calculate_jains_fairness_index([0.0, 0.0]) == 1.0


def test_metrics_computation_empty_traffic():
    """Zero traffic should produce zero throughput and not throw divide-by-zero exceptions."""
    cfg = SimulationConfig(
        link_capacity_mbps=10.0,
        simulation_duration_sec=5.0,
        random_seed=42,
        scheduler_type="fcfs",
        classes=DEFAULT_CLASSES,
    )
    scheduler = FCFSScheduler(cfg)
    result = compute_simulation_metrics(
        config=cfg,
        scheduler=scheduler,
        all_packets=[],
        transmitted_packets=[],
        dropped_packets=[],
        time_series=[],
        total_busy_time=0.0,
    )
    assert result.total_packets_generated == 0
    assert result.total_packets_transmitted == 0
    assert result.total_throughput_mbps == 0.0
    assert result.packet_loss_rate_pct == 0.0
    assert result.avg_packet_delay_ms == 0.0
