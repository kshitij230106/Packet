"""Pydantic data models for configuration, requests, responses, and metrics.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class TrafficClassConfig(BaseModel):
    """Configuration for an individual traffic class."""
    name: str = Field(..., description="Machine-readable name: emergency, video, gaming, file")
    display_name: str = Field(..., description="Human-readable title")
    enabled: bool = Field(True, description="Whether this traffic flow is active")
    arrival_rate_pps: float = Field(..., gt=0.0, description="Packet arrival rate (packets per second)")
    packet_size_bytes: int = Field(..., ge=40, le=9000, description="Base packet size in bytes")
    packet_size_jitter_bytes: int = Field(0, ge=0, description="Uniform random jitter range (+/- bytes)")
    priority: int = Field(..., ge=1, le=10, description="Strict priority order: 1 is highest priority")
    wfq_weight: float = Field(..., gt=0.0, description="Relative scheduling weight in Weighted Fair Queuing")
    queue_capacity: int = Field(50, ge=1, le=1000, description="Max packet queue capacity for this class")


class SimulationConfig(BaseModel):
    """Complete simulation run configuration."""
    link_capacity_mbps: float = Field(10.0, gt=0.1, le=1000.0, description="Bottleneck link capacity in Mbps")
    simulation_duration_sec: float = Field(5.0, gt=0.5, le=30.0, description="Simulated duration in seconds")
    random_seed: Optional[int] = Field(42, description="Random seed for reproducible traffic traces")
    scheduler_type: str = Field("fcfs", description="Scheduling algorithm: 'fcfs', 'strict_priority', or 'wfq'")
    global_queue_capacity: Optional[int] = Field(None, ge=1, le=2000, description="Optional shared buffer capacity limit")
    classes: Dict[str, TrafficClassConfig] = Field(..., description="Configuration per traffic class")

    @field_validator("scheduler_type")
    def validate_scheduler_type(cls, v: str) -> str:
        valid = ["fcfs", "strict_priority", "wfq"]
        if v.lower() not in valid:
            raise ValueError(f"scheduler_type must be one of {valid}")
        return v.lower()


class TrafficClassMetrics(BaseModel):
    """Computed metrics for a single traffic class."""
    class_name: str
    display_name: str
    enabled: bool
    packets_generated: int
    packets_transmitted: int
    packets_dropped: int
    packet_loss_rate_pct: float
    bytes_transmitted: int
    offered_load_mbps: float
    throughput_mbps: float
    avg_delay_ms: float
    min_delay_ms: float
    max_delay_ms: float
    avg_queuing_delay_ms: float
    avg_serialization_delay_ms: float
    configured_priority: int
    configured_wfq_weight: float
    wfq_bandwidth_share_pct: float


class TimeSeriesSample(BaseModel):
    """Point-in-time snapshot of the simulation state."""
    time_sec: float
    queue_lengths: Dict[str, int]
    total_queue_length: int
    link_busy: bool
    current_tx_class: Optional[str] = None


class PacketEvent(BaseModel):
    """Discrete packet event emitted for frontend step-by-step playback."""
    time_sec: float
    event_type: str  # "arrival", "enqueued", "dropped", "tx_start", "tx_complete"
    packet_id: str
    traffic_class: str
    size_bytes: int
    queue_lengths: Dict[str, int]
    detail: Optional[str] = None


class SimulationResult(BaseModel):
    """Complete results from a single simulation run."""
    scheduler_type: str
    scheduler_name: str
    scheduler_description: str
    simulation_duration_sec: float
    link_capacity_mbps: float
    total_packets_generated: int
    total_packets_transmitted: int
    total_packets_dropped: int
    packet_loss_rate_pct: float
    total_throughput_mbps: float
    link_utilization_pct: float
    avg_packet_delay_ms: float
    avg_queuing_delay_ms: float
    avg_serialization_delay_ms: float
    avg_queue_length: float
    max_queue_length: int
    jains_fairness_index_raw: float
    jains_fairness_index_weighted: float
    class_metrics: Dict[str, TrafficClassMetrics]
    time_series: List[TimeSeriesSample]
    packet_events: List[PacketEvent]
    insights: List[str]
    config: SimulationConfig


class ComparisonResult(BaseModel):
    """Side-by-side comparison of FCFS, Strict Priority, and WFQ under identical traffic traces."""
    traffic_trace_summary: Dict[str, int]
    simulation_duration_sec: float
    link_capacity_mbps: float
    fcfs: SimulationResult
    strict_priority: SimulationResult
    wfq: SimulationResult
    comparison_summary: List[Dict[str, Any]]
    synthesis_insights: List[str]


class AlgorithmInfo(BaseModel):
    """Metadata describing an algorithm."""
    id: str
    name: str
    category: str
    summary: str
    pros: List[str]
    cons: List[str]
    ideal_use_case: str
    formula: Optional[str] = None
