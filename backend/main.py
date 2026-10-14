"""FastAPI backend application for Bandwidth Court.
"""

import os
from typing import Dict, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.metrics import compute_simulation_metrics
from backend.models import (
    AlgorithmInfo,
    ComparisonResult,
    SimulationConfig,
    SimulationResult,
)
from backend.schedulers import SCHEDULER_REGISTRY, create_scheduler
from backend.simulator import SimulationEngine
from backend.traffic_generator import DEFAULT_CLASSES, TrafficGenerator

app = FastAPI(
    title="Bandwidth Court API",
    description="Interactive Quality-of-Service (QoS) and Fair Bandwidth Allocation Simulator API",
    version="1.0.0",
)

# Enable CORS for local web development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Bandwidth Court Simulator",
        "version": "1.0.0",
    }


@app.get("/defaults")
def get_defaults() -> SimulationConfig:
    """Return default simulation parameters."""
    return SimulationConfig(
        link_capacity_mbps=10.0,
        simulation_duration_sec=5.0,
        random_seed=42,
        scheduler_type="fcfs",
        global_queue_capacity=None,
        classes=DEFAULT_CLASSES,
    )


@app.get("/algorithms", response_model=List[AlgorithmInfo])
def list_algorithms() -> List[AlgorithmInfo]:
    """Return list of available scheduling algorithms and their characteristics."""
    return [
        AlgorithmInfo(
            id="fcfs",
            name="First-Come First-Served (FCFS)",
            category="Non-prioritized FIFO",
            summary="All incoming packets enter a single shared queue and are served in exact order of arrival.",
            pros=[
                "O(1) algorithmic complexity with zero state tracking per flow.",
                "Zero starvation when total load is within capacity.",
                "Simple, universally supported hardware buffer implementation.",
            ],
            cons=[
                "No flow isolation; bulky file transfers create bufferbloat.",
                "High latency for small interactive packets (gaming, voice).",
                "Completely ignores packet priority or service level agreements (SLAs).",
            ],
            ideal_use_case="Best effort traffic where all packets have identical importance and latency tolerance.",
            formula="Queue Order: t_arrival(p_1) <= t_arrival(p_2) <= ...",
        ),
        AlgorithmInfo(
            id="strict_priority",
            name="Strict Priority Scheduling",
            category="Class-Based Priority",
            summary="Separate queues for each traffic class. Always dispatches packets from highest-priority non-empty queue.",
            pros=[
                "Absolute lowest possible queuing delay for top-priority traffic (Emergency, Voice).",
                "Deterministic priority guarantee for critical control messages.",
                "Simple queue partitioning mechanism.",
            ],
            cons=[
                "Severe starvation of lower-priority classes when higher classes are sustained.",
                "No fairness between flows within different tiers.",
                "Prone to denial-of-service if high-priority streams are misbehaved or malicious.",
            ],
            ideal_use_case="Mission-critical networks where emergency and network control signaling must preempt everything else.",
            formula="Serve queue q_i where i = min(j : queue_j is not empty)",
        ),
        AlgorithmInfo(
            id="wfq",
            name="Weighted Fair Queuing (WFQ / PGPS)",
            category="Fair Queuing & Flow Isolation",
            summary="Packetized Generalized Processor Sharing scheduler that allocates bandwidth proportional to assigned weights while normalizing for packet sizes.",
            pros=[
                "Guaranteed minimum bandwidth share: flow i receives at least w_i / (sum w_k) of link capacity.",
                "Flow isolation protects responsive traffic against aggressive bulk senders.",
                "Accounts for variable packet sizes through virtual finish times.",
                "Bounded worst-case delay for conforming sessions.",
            ],
            cons=[
                "Higher computational complexity O(log N) per packet to compute finish times and extract minimum.",
                "Requires maintaining per-flow queue state in router memory.",
            ],
            ideal_use_case="Modern multi-tenant core routers and differentiated services (DiffServ) where diverse applications must coexist fairly.",
            formula="F_i^k = max(F_i^{k-1}, V(a_i^k)) + (L_i^k / w_i), where dV/dt = 1 / sum_{j in B(t)} w_j",
        ),
    ]


@app.post("/simulate", response_model=SimulationResult)
def run_simulation(config: SimulationConfig) -> SimulationResult:
    """Execute a single simulation run for the specified scheduler."""
    try:
        generator = TrafficGenerator(config)
        trace = generator.generate_trace()

        scheduler = create_scheduler(config.scheduler_type, config)
        engine = SimulationEngine(config, scheduler)
        engine.run(trace)

        result = compute_simulation_metrics(
            config=config,
            scheduler=scheduler,
            all_packets=engine.all_packets,
            transmitted_packets=engine.transmitted_packets,
            dropped_packets=engine.dropped_packets,
            time_series=engine.time_series,
            total_busy_time=engine.total_busy_time,
        )
        result.packet_events = engine.packet_events
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/compare", response_model=ComparisonResult)
def run_comparison(config: SimulationConfig) -> ComparisonResult:
    """Execute all three schedulers (FCFS, Strict Priority, WFQ) on the EXACT same packet trace

    to ensure a scientifically fair comparison.
    """
    try:
        # 1. Generate master packet trace once
        generator = TrafficGenerator(config)
        master_trace = generator.generate_trace()

        trace_counts: Dict[str, int] = {}
        for p in master_trace:
            trace_counts[p.traffic_class] = trace_counts.get(p.traffic_class, 0) + 1

        results: Dict[str, SimulationResult] = {}
        algorithms = ["fcfs", "strict_priority", "wfq"]

        for alg in algorithms:
            # Replay identical packet trace by deep-cloning
            trace_copy = generator.clone_trace(master_trace)
            alg_config = config.model_copy(update={"scheduler_type": alg})

            scheduler = create_scheduler(alg, alg_config)
            engine = SimulationEngine(alg_config, scheduler)
            engine.run(trace_copy)

            sim_result = compute_simulation_metrics(
                config=alg_config,
                scheduler=scheduler,
                all_packets=engine.all_packets,
                transmitted_packets=engine.transmitted_packets,
                dropped_packets=engine.dropped_packets,
                time_series=engine.time_series,
                total_busy_time=engine.total_busy_time,
            )
            sim_result.packet_events = engine.packet_events
            results[alg] = sim_result

        fcfs_res = results["fcfs"]
        sp_res = results["strict_priority"]
        wfq_res = results["wfq"]

        # Build comparative summary metrics table
        comparison_summary = [
            {
                "metric": "Overall Throughput",
                "unit": "Mbps",
                "fcfs": fcfs_res.total_throughput_mbps,
                "strict_priority": sp_res.total_throughput_mbps,
                "wfq": wfq_res.total_throughput_mbps,
            },
            {
                "metric": "Average End-to-End Delay",
                "unit": "ms",
                "fcfs": fcfs_res.avg_packet_delay_ms,
                "strict_priority": sp_res.avg_packet_delay_ms,
                "wfq": wfq_res.avg_packet_delay_ms,
            },
            {
                "metric": "Average Queuing Delay",
                "unit": "ms",
                "fcfs": fcfs_res.avg_queuing_delay_ms,
                "strict_priority": sp_res.avg_queuing_delay_ms,
                "wfq": wfq_res.avg_queuing_delay_ms,
            },
            {
                "metric": "Packet Loss Rate",
                "unit": "%",
                "fcfs": fcfs_res.packet_loss_rate_pct,
                "strict_priority": sp_res.packet_loss_rate_pct,
                "wfq": wfq_res.packet_loss_rate_pct,
            },
            {
                "metric": "Link Utilization",
                "unit": "%",
                "fcfs": fcfs_res.link_utilization_pct,
                "strict_priority": sp_res.link_utilization_pct,
                "wfq": wfq_res.link_utilization_pct,
            },
            {
                "metric": "Jain's Fairness (Raw)",
                "unit": "0.0 - 1.0",
                "fcfs": fcfs_res.jains_fairness_index_raw,
                "strict_priority": sp_res.jains_fairness_index_raw,
                "wfq": wfq_res.jains_fairness_index_raw,
            },
            {
                "metric": "Jain's Fairness (Weighted)",
                "unit": "0.0 - 1.0",
                "fcfs": fcfs_res.jains_fairness_index_weighted,
                "strict_priority": sp_res.jains_fairness_index_weighted,
                "wfq": wfq_res.jains_fairness_index_weighted,
            },
        ]

        # Multi-algorithm synthesis insights
        synthesis_insights = []
        # Emergency delay comparison
        em_sp = sp_res.class_metrics.get("emergency")
        em_fcfs = fcfs_res.class_metrics.get("emergency")
        em_wfq = wfq_res.class_metrics.get("emergency")
        if em_sp and em_fcfs and em_sp.enabled and em_sp.avg_delay_ms < em_fcfs.avg_delay_ms:
            diff = round(em_fcfs.avg_delay_ms - em_sp.avg_delay_ms, 1)
            synthesis_insights.append(
                f"Emergency Priority Advantage: Strict Priority provided {diff} ms lower delay for Emergency Messages "
                f"compared to FCFS ({em_sp.avg_delay_ms} ms vs {em_fcfs.avg_delay_ms} ms)."
            )

        # Starvation check on lower priority
        file_sp = sp_res.class_metrics.get("file")
        file_wfq = wfq_res.class_metrics.get("file")
        if file_sp and file_wfq and file_sp.enabled:
            if file_sp.packet_loss_rate_pct > file_wfq.packet_loss_rate_pct + 10.0:
                synthesis_insights.append(
                    f"Starvation in Strict Priority: File Downloads experienced {file_sp.packet_loss_rate_pct}% drop rate "
                    f"under Strict Priority compared to only {file_wfq.packet_loss_rate_pct}% under WFQ, demonstrating flow isolation."
                )

        # Bufferbloat in FCFS
        game_fcfs = fcfs_res.class_metrics.get("gaming")
        game_wfq = wfq_res.class_metrics.get("gaming")
        if game_fcfs and game_wfq and game_fcfs.enabled and game_fcfs.avg_delay_ms > game_wfq.avg_delay_ms:
            synthesis_insights.append(
                f"Head-of-Line Blocking Mitigation: WFQ reduced Gaming delay from {game_fcfs.avg_delay_ms} ms (FCFS) "
                f"to {game_wfq.avg_delay_ms} ms by accounting for smaller packet sizes."
            )

        # Weighted fairness comparison
        if wfq_res.jains_fairness_index_weighted >= sp_res.jains_fairness_index_weighted:
            synthesis_insights.append(
                f"Weighted Fairness Superiority: WFQ scored {wfq_res.jains_fairness_index_weighted} on Weighted Jain's Index, "
                f"successfully honoring configured QoS weight ratios."
            )

        return ComparisonResult(
            traffic_trace_summary=trace_counts,
            simulation_duration_sec=config.simulation_duration_sec,
            link_capacity_mbps=config.link_capacity_mbps,
            fcfs=fcfs_res,
            strict_priority=sp_res,
            wfq=wfq_res,
            comparison_summary=comparison_summary,
            synthesis_insights=synthesis_insights,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Serve static frontend files if directory exists
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_path):
    # Mount StaticFiles at root so index.html, style.css, and app.js resolve directly
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
else:
    @app.get("/")
    def root_info() -> Dict[str, str]:
        return {
            "name": "Bandwidth Court",
            "message": "Backend API is online. Frontend directory will be served once present.",
            "health": "/health",
            "defaults": "/defaults",
            "algorithms": "/algorithms",
        }
