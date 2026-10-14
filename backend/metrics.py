"""Metrics calculation and dynamic insights engine for Bandwidth Court simulation.
"""

from typing import Dict, List, Optional
from backend.models import (
    SimulationConfig,
    SimulationResult,
    TimeSeriesSample,
    TrafficClassMetrics,
)
from backend.packet import Packet
from backend.schedulers.base import BaseScheduler


def calculate_jains_fairness_index(values: List[float]) -> float:
    """Calculate Jain's Fairness Index:

    J = (sum(x_i))^2 / (n * sum(x_i^2))

    Returns:
        float between 0.0 and 1.0 (1.0 indicates perfect fairness).
    """
    if not values:
        return 1.0

    # Filter out non-positive values if all zero
    sum_val = sum(values)
    sum_sq = sum(x * x for x in values)
    n = len(values)

    if sum_sq <= 0.0 or n == 0:
        return 1.0

    fairness = (sum_val ** 2) / (n * sum_sq)
    return max(0.0, min(1.0, fairness))


def compute_simulation_metrics(
    config: SimulationConfig,
    scheduler: BaseScheduler,
    all_packets: List[Packet],
    transmitted_packets: List[Packet],
    dropped_packets: List[Packet],
    time_series: List[TimeSeriesSample],
    total_busy_time: float,
) -> SimulationResult:
    """Compute aggregate and per-class performance metrics from simulation results."""
    duration = max(0.001, config.simulation_duration_sec)
    last_tx_time = max([p.tx_completion_time for p in transmitted_packets if p.tx_completion_time is not None] or [duration])
    effective_duration = max(duration, last_tx_time)

    total_generated = len(all_packets)
    total_transmitted = len(transmitted_packets)
    total_dropped = len(dropped_packets)

    loss_pct = (total_dropped / total_generated * 100.0) if total_generated > 0 else 0.0

    # Total bytes and throughput
    total_bytes_transmitted = sum(p.size_bytes for p in transmitted_packets)
    raw_throughput = (total_bytes_transmitted * 8.0) / (effective_duration * 1_000_000.0)
    total_throughput_mbps = min(config.link_capacity_mbps, raw_throughput)

    # Link utilization
    link_utilization_pct = min(100.0, (total_busy_time / effective_duration) * 100.0)

    # Delays for transmitted packets
    delays_ms = [p.total_delay * 1000.0 for p in transmitted_packets if p.total_delay is not None]
    queuing_delays_ms = [p.queuing_delay * 1000.0 for p in transmitted_packets if p.queuing_delay is not None]
    serialization_delays_ms = [p.serialization_delay * 1000.0 for p in transmitted_packets if p.serialization_delay is not None]

    avg_packet_delay_ms = (sum(delays_ms) / len(delays_ms)) if delays_ms else 0.0
    avg_queuing_delay_ms = (sum(queuing_delays_ms) / len(queuing_delays_ms)) if queuing_delays_ms else 0.0
    avg_serialization_delay_ms = (sum(serialization_delays_ms) / len(serialization_delays_ms)) if serialization_delays_ms else 0.0

    # Queue statistics
    total_queue_lengths = [sample.total_queue_length for sample in time_series]
    avg_queue_len = (sum(total_queue_lengths) / len(total_queue_lengths)) if total_queue_lengths else 0.0
    max_queue_len = max(total_queue_lengths) if total_queue_lengths else 0

    # Per-class breakdowns
    class_metrics: Dict[str, TrafficClassMetrics] = {}
    throughput_list: List[float] = []
    weighted_throughput_list: List[float] = []

    for cls_name, cls_cfg in config.classes.items():
        if not cls_cfg.enabled:
            class_metrics[cls_name] = TrafficClassMetrics(
                class_name=cls_name,
                display_name=cls_cfg.display_name,
                enabled=False,
                packets_generated=0,
                packets_transmitted=0,
                packets_dropped=0,
                packet_loss_rate_pct=0.0,
                bytes_transmitted=0,
                offered_load_mbps=0.0,
                throughput_mbps=0.0,
                avg_delay_ms=0.0,
                min_delay_ms=0.0,
                max_delay_ms=0.0,
                avg_queuing_delay_ms=0.0,
                avg_serialization_delay_ms=0.0,
                configured_priority=cls_cfg.priority,
                configured_wfq_weight=cls_cfg.wfq_weight,
                wfq_bandwidth_share_pct=0.0,
            )
            continue

        c_gen = [p for p in all_packets if p.traffic_class == cls_name]
        c_tx = [p for p in transmitted_packets if p.traffic_class == cls_name]
        c_drop = [p for p in dropped_packets if p.traffic_class == cls_name]

        n_gen = len(c_gen)
        n_tx = len(c_tx)
        n_drop = len(c_drop)

        c_loss_pct = (n_drop / n_gen * 100.0) if n_gen > 0 else 0.0
        c_bytes = sum(p.size_bytes for p in c_tx)
        c_raw_tp = (c_bytes * 8.0) / (effective_duration * 1_000_000.0)
        c_throughput = min(config.link_capacity_mbps, c_raw_tp)
        c_offered = (sum(p.size_bytes for p in c_gen) * 8.0) / (duration * 1_000_000.0)

        c_delays = [p.total_delay * 1000.0 for p in c_tx if p.total_delay is not None]
        c_q_delays = [p.queuing_delay * 1000.0 for p in c_tx if p.queuing_delay is not None]
        c_tx_delays = [p.serialization_delay * 1000.0 for p in c_tx if p.serialization_delay is not None]

        c_avg_delay = (sum(c_delays) / len(c_delays)) if c_delays else 0.0
        c_min_delay = min(c_delays) if c_delays else 0.0
        c_max_delay = max(c_delays) if c_delays else 0.0
        c_avg_q_delay = (sum(c_q_delays) / len(c_q_delays)) if c_q_delays else 0.0
        c_avg_tx_delay = (sum(c_tx_delays) / len(c_tx_delays)) if c_tx_delays else 0.0

        throughput_list.append(c_throughput)
        # Weighted throughput normalization: throughput / weight
        w = max(0.001, cls_cfg.wfq_weight)
        weighted_throughput_list.append(c_throughput / w)

        class_metrics[cls_name] = TrafficClassMetrics(
            class_name=cls_name,
            display_name=cls_cfg.display_name,
            enabled=True,
            packets_generated=n_gen,
            packets_transmitted=n_tx,
            packets_dropped=n_drop,
            packet_loss_rate_pct=round(c_loss_pct, 2),
            bytes_transmitted=c_bytes,
            offered_load_mbps=round(c_offered, 3),
            throughput_mbps=round(c_throughput, 3),
            avg_delay_ms=round(c_avg_delay, 2),
            min_delay_ms=round(c_min_delay, 2),
            max_delay_ms=round(c_max_delay, 2),
            avg_queuing_delay_ms=round(c_avg_q_delay, 2),
            avg_serialization_delay_ms=round(c_avg_tx_delay, 2),
            configured_priority=cls_cfg.priority,
            configured_wfq_weight=cls_cfg.wfq_weight,
            wfq_bandwidth_share_pct=0.0,  # Computed below
        )

    # Compute actual bandwidth share percentages
    if total_throughput_mbps > 0:
        for m in class_metrics.values():
            if m.enabled:
                m.wfq_bandwidth_share_pct = round((m.throughput_mbps / total_throughput_mbps) * 100.0, 1)

    jains_raw = calculate_jains_fairness_index(throughput_list)
    jains_weighted = calculate_jains_fairness_index(weighted_throughput_list)

    insights = generate_simulation_insights(
        scheduler_type=config.scheduler_type,
        class_metrics=class_metrics,
        total_throughput_mbps=total_throughput_mbps,
        link_capacity_mbps=config.link_capacity_mbps,
        link_utilization_pct=link_utilization_pct,
        avg_packet_delay_ms=avg_packet_delay_ms,
        total_dropped=total_dropped,
        jains_raw=jains_raw,
        jains_weighted=jains_weighted,
    )

    return SimulationResult(
        scheduler_type=config.scheduler_type,
        scheduler_name=scheduler.name,
        scheduler_description=scheduler.description,
        simulation_duration_sec=duration,
        link_capacity_mbps=config.link_capacity_mbps,
        total_packets_generated=total_generated,
        total_packets_transmitted=total_transmitted,
        total_packets_dropped=total_dropped,
        packet_loss_rate_pct=round(loss_pct, 2),
        total_throughput_mbps=round(total_throughput_mbps, 3),
        link_utilization_pct=round(link_utilization_pct, 2),
        avg_packet_delay_ms=round(avg_packet_delay_ms, 2),
        avg_queuing_delay_ms=round(avg_queuing_delay_ms, 2),
        avg_serialization_delay_ms=round(avg_serialization_delay_ms, 2),
        avg_queue_length=round(avg_queue_len, 2),
        max_queue_length=max_queue_len,
        jains_fairness_index_raw=round(jains_raw, 4),
        jains_fairness_index_weighted=round(jains_weighted, 4),
        class_metrics=class_metrics,
        time_series=time_series,
        packet_events=[],  # Added in simulator run
        insights=insights,
        config=config,
    )


def generate_simulation_insights(
    scheduler_type: str,
    class_metrics: Dict[str, TrafficClassMetrics],
    total_throughput_mbps: float,
    link_capacity_mbps: float,
    link_utilization_pct: float,
    avg_packet_delay_ms: float,
    total_dropped: int,
    jains_raw: float,
    jains_weighted: float,
) -> List[str]:
    """Derive educational, data-driven networking insights based on empirical outcomes."""
    insights: List[str] = []

    # Congestion & Utilization insight
    if link_utilization_pct >= 90.0:
        insights.append(
            f"Bottleneck link reached {round(link_utilization_pct, 1)}% utilization, "
            f"indicating high congestion and queue buildup where offered load exceeded service rate."
        )
    elif link_utilization_pct < 50.0:
        insights.append(
            f"Link utilization was low ({round(link_utilization_pct, 1)}%). The bottleneck was under-subscribed, "
            "so queueing delays remained negligible across all algorithms."
        )

    # Drops insight
    if total_dropped > 0:
        insights.append(
            f"Buffer overflow caused {total_dropped} packets to be dropped. Queue limits successfully protected "
            "router memory at the cost of packet loss."
        )

    emergency = class_metrics.get("emergency")
    video = class_metrics.get("video")
    gaming = class_metrics.get("gaming")
    file_dl = class_metrics.get("file")

    # Algorithm specific observations
    if scheduler_type == "strict_priority":
        if emergency and emergency.enabled and emergency.avg_delay_ms < 15.0:
            insights.append(
                f"Strict Priority protected Emergency Messages, achieving ultra-low delay of {emergency.avg_delay_ms} ms "
                "by unconditionally dispatching them ahead of all other traffic."
            )
        if file_dl and file_dl.enabled:
            if file_dl.packet_loss_rate_pct > 25.0 or (video and video.throughput_mbps > 0 and file_dl.throughput_mbps < 0.2):
                insights.append(
                    f"Starvation Detected: File Downloads suffered {file_dl.packet_loss_rate_pct}% loss and degraded service "
                    "because higher-priority flows (Emergency, Video) monopolized the transmission queue."
                )
    elif scheduler_type == "fcfs":
        if file_dl and gaming and file_dl.enabled and gaming.enabled:
            if gaming.avg_delay_ms > 20.0 and file_dl.packets_transmitted > 0:
                insights.append(
                    f"Head-of-Line Blocking (Bufferbloat): In FCFS, small latency-sensitive Gaming packets "
                    f"were delayed ({gaming.avg_delay_ms} ms) behind large File Download packets in the shared FIFO queue."
                )
        insights.append(
            "FCFS treats all packets identically regardless of QoS requirements, failing to guarantee SLA for latency-critical flows."
        )
    elif scheduler_type == "wfq":
        insights.append(
            f"Flow Isolation: Weighted Fair Queuing prevented bulk File Downloads from starving interactive flows, "
            f"achieving weighted fairness of {round(jains_weighted, 3)}."
        )
        if video and gaming and video.enabled and gaming.enabled and video.throughput_mbps > 0:
            ratio = round(video.throughput_mbps / max(0.01, gaming.throughput_mbps), 2)
            expected_ratio = round(video.configured_wfq_weight / max(0.01, gaming.configured_wfq_weight), 2)
            insights.append(
                f"Weight Adherence: Video-to-Gaming throughput ratio was {ratio} (configured WFQ weight ratio: {expected_ratio})."
            )

    return insights
