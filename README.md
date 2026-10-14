# Bandwidth Court — Interactive QoS & Fair Bandwidth Allocation Simulator

[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![Chart.js](https://img.shields.io/badge/Chart.js-4.4+-FF6384?style=flat&logo=chartdotjs&logoColor=white)](https://www.chartjs.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Bandwidth Court** is an interactive, educational network simulator and laboratory dashboard designed to demonstrate how multiple heterogeneous application flows compete for constrained bottleneck link capacity. It implements and rigorously compares three foundational packet scheduling disciplines:

1. **First-Come First-Served (FCFS / FIFO)**
2. **Strict Priority Scheduling (SP)**
3. **Weighted Fair Queuing (WFQ / Packetized GPS)**

The simulator features a **discrete-event simulation engine** in Python that models discrete packet arrivals, serialization delay, finite queue buffers, queue overflows, and per-flow telemetry. The frontend is a modern dark navy and electric blue dashboard featuring interactive Chart.js visualizations, a live animated network queuing pipeline, KPI cards, analytical insights, and a side-by-side benchmark table.

---

## Table of Contents
- [1. Networking Concepts Demonstrated](#1-networking-concepts-demonstrated)
- [2. Scheduling Algorithms](#2-scheduling-algorithms)
- [3. Mathematical Formulations & Metrics](#3-mathematical-formulations--metrics)
- [4. Traffic Classes & Workload Profiles](#4-traffic-classes--workload-profiles)
- [5. System Architecture & Flow](#5-system-architecture--flow)
- [6. Project Folder Structure](#6-project-folder-structure)
- [7. Installation & Quickstart](#7-installation--quickstart)
- [8. API Reference](#8-api-reference)
- [9. Guided Experiments](#9-guided-experiments)
- [10. Running the Automated Test Suite](#10-running-the-automated-test-suite)
- [11. Assumptions & Limitations](#11-assumptions--limitations)

---

## 1. Networking Concepts Demonstrated

- **Bandwidth Contention & Bottlenecks:** When aggregate offered load from active senders exceeds link transmission capacity ($C$), queues grow and packets experience queuing delay or drops.
- **Serialization (Transmission) Delay:** The physical time required to push packet bits onto the link: $\Delta t = \frac{L}{C}$.
- **Bufferbloat & Head-of-Line Blocking:** How bulky bulk file transfers with large MTUs degrade latency for interactive voice and gaming packets in non-isolated queues.
- **Starvation in Strict Priority:** How sustained high-priority traffic completely denies service to lower-priority flows, driving packet loss to 100%.
- **Flow Isolation in WFQ:** How assigning weights isolates flows, preventing aggressive senders from hogging link bandwidth while normalizing for variable packet lengths.
- **Fairness vs. QoS Compliance:** Distinguishing between raw egalitarian throughput and weighted fairness (Jain's Fairness Index).

---

## 2. Scheduling Algorithms

All schedulers adhere to a common abstract interface (`BaseScheduler`):
- `enqueue(packet, current_time) -> bool`
- `dequeue(current_time) -> Optional[Packet]`
- `has_packets() -> bool`
- `get_queue_lengths() -> Dict[str, int]`

### A. First-Come First-Served (FCFS / FIFO)
- **Mechanism:** Packets are admitted into a single shared FIFO queue and dispatched strictly in the order they arrived.
- **Characteristics:** $O(1)$ constant time complexity. Zero flow isolation. Bulk transfers (1440B File packets) fill up the shared buffer and subject real-time packets (84B Gaming, 960B Video) to excessive queuing delays.

### B. Strict Priority Scheduling (SP)
- **Mechanism:** Maintains distinct FIFO queues per priority tier (Emergency: Priority 1, Video: Priority 2, Gaming: Priority 3, File: Priority 4). The scheduler always serves from the highest-priority non-empty queue.
- **Characteristics:** Guarantees deterministic, near-zero queuing delay for Emergency messages. However, if higher-priority queues are continuously backlogged, lower-priority queues receive **zero transmissions**, causing packet drops and starvation.

### C. Weighted Fair Queuing (WFQ / PGPS)
- **Mechanism:** Emulates Generalized Processor Sharing (GPS). Virtual time $V(t)$ progresses inversely to the sum of active flow weights:
  $$\frac{dV(t)}{dt} = \frac{1}{\sum_{j \in B(t)} w_j}$$
  For packet $k$ of flow $i$ arriving at time $a_i^k$ with size $L_i^k$ bytes and weight $w_i$:
  $$S_i^k = \max(F_i^{k-1}, V(a_i^k))$$
  $$F_i^k = S_i^k + \frac{L_i^k}{w_i}$$
- **Characteristics:** The packet with the smallest virtual finish time $F_i^k$ among all queue heads is dispatched next. This normalizes for packet size differences and guarantees each flow receives at least its fair share of bandwidth $\frac{w_i}{\sum w_j} C$.

---

## 3. Mathematical Formulations & Metrics

### Serialization Delay
For a packet of length $L$ bytes over a bottleneck link of capacity $C$ Mbps:
$$\Delta t_{\text{serialization}} = \frac{L \times 8}{C \times 10^6} \text{ seconds}$$

### End-to-End Simulated Delay
For each transmitted packet $k$:
$$\text{Queuing Delay} = t_{\text{tx\_start}} - t_{\text{queue\_entry}}$$
$$\text{Total Delay} = t_{\text{tx\_complete}} - t_{\text{arrival}} = \text{Queuing Delay} + \text{Serialization Delay}$$

### Link Utilization
$$\text{Utilization} = \frac{\sum \Delta t_{\text{serialization}}}{T_{\text{simulation}}} \times 100\%$$

### Jain's Fairness Index
Quantifies how equitably service is allocated across $n$ active traffic classes:
$$J = \frac{\left(\sum_{i=1}^n x_i\right)^2}{n \sum_{i=1}^n x_i^2}$$
- **Raw Throughput Fairness:** $x_i = \text{Throughput}_i$. Measures equal throughput distribution.
- **Weighted Fairness:** $x_i = \frac{\text{Throughput}_i}{w_i}$. Measures whether flows receive bandwidth proportional to their assigned weights $w_i$. Safe zero-division handling guarantees $J \in [0.0, 1.0]$.

---

## 4. Traffic Classes & Workload Profiles

| Class Name | Default Rate | Default Size | Priority | WFQ Weight | Buffer Capacity | Role |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Emergency Messages** | 8 pps | 128 Bytes | 1 (Highest) | 4.0 | 30 pkts | Mission-critical signaling, ultra-low delay required |
| **Video Calls** | 100 pps | 960 Bytes | 2 | 3.0 | 60 pkts | Latency-sensitive multimedia, moderate packet sizes |
| **Online Gaming** | 140 pps | 84 Bytes | 3 | 2.0 | 50 pkts | Real-time interactive UDP, small packets, jitter sensitive |
| **File Downloads** | 220 pps | 1440 Bytes | 4 (Lowest) | 1.0 | 80 pkts | Bulk TCP throughput, large MTU, delay-tolerant |

Arrivals are generated using **Poisson arrival processes** with exponential inter-arrival times $\Delta t \sim \text{Exp}(\lambda)$ and configurable pseudo-random seeds for reproducible experiment traces.

---

## 5. System Architecture & Flow

```
[Traffic Generator (Poisson)]
            │
            ▼ (Master Packet Trace)
┌────────────────────────────────────────────────────────┐
│             Trace Replay Across Schedulers             │
│                                                        │
│   ┌──────────────┐   ┌─────────────────┐   ┌───────┐   │
│   │     FCFS     │   │ Strict Priority │   │  WFQ  │   │
│   └──────┬───────┘   └────────┬────────┘   └───┬───┘   │
└──────────┼────────────────────┼────────────────┼───────┘
           ▼                    ▼                ▼
┌────────────────────────────────────────────────────────┐
│            Discrete-Event Simulation Engine            │
│  - Arrival Events & Queue Drops (Buffer Overflows)     │
│  - Bottleneck Link Serialization (L / C)               │
│  - Time-series Telemetry & Discrete Packet Event Log   │
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│                     Metrics Engine                     │
│  - Throughput, Delays, Loss Rate, Link Utilization     │
│  - Raw & Weighted Jain's Fairness Indices              │
│  - Dynamic Analytical Insights Generation              │
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│                 FastAPI REST Service                   │
│  - POST /simulate  |  POST /compare  |  GET /defaults  │
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│               Interactive Web Dashboard                │
│  - Live Pipeline Visualizer (Queues, Link, Sinks)      │
│  - KPI Cards, Analytical Insights, Benchmark Table     │
│  - Interactive Chart.js Telemetry Charts               │
└────────────────────────────────────────────────────────┘
```

---

## 6. Project Folder Structure

```
bandwidth-court/
├── backend/
│   ├── main.py                 # FastAPI application, CORS, static routes
│   ├── models.py               # Pydantic schemas for configs, metrics, events
│   ├── packet.py               # Discrete packet entity dataclass
│   ├── traffic_generator.py    # Poisson packet generation and trace cloning
│   ├── simulator.py            # Discrete-event engine (heapq event queue)
│   ├── metrics.py              # Metrics, Jain's fairness, insights generator
│   ├── schedulers/
│   │   ├── __init__.py         # Scheduler registry and factory
│   │   ├── base.py             # BaseScheduler abstract interface
│   │   ├── fcfs.py             # First-Come First-Served scheduler
│   │   ├── strict_priority.py  # Strict Priority scheduler
│   │   └── wfq.py              # Weighted Fair Queuing (PGPS) scheduler
│   └── tests/
│       ├── __init__.py
│       ├── test_schedulers.py  # FCFS, SP, WFQ correctness tests
│       ├── test_simulation.py  # Serialization delay and overflow tests
│       ├── test_metrics.py     # Fairness and metric computation tests
│       └── test_api.py         # FastAPI endpoints integration tests
├── frontend/
│   ├── index.html              # Modern dashboard layout and theory modal
│   ├── style.css               # Professional dark navy and blue design system
│   └── app.js                  # DOM controller, Chart.js, discrete animator
├── requirements.txt            # Python dependencies
└── README.md                   # Comprehensive documentation
```

---

## 7. Installation & Quickstart

### Prerequisites
- Python 3.10 or higher
- Modern web browser (Chrome, Edge, Firefox, Safari)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Start the Backend Server
From the workspace root directory, start the FastAPI server:
```bash
uvicorn backend.main:app --reload --port 8000
```

### 3. Access the Web Dashboard
Open your browser and navigate to:
```
http://localhost:8000
```
FastAPI automatically serves the frontend dashboard at root `http://localhost:8000/`.

*(Alternatively, you may open `frontend/index.html` directly in your browser or serve it via Live Server; CORS is enabled to allow cross-origin requests to `http://127.0.0.1:8000`.)*

---

## 8. API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Serves dashboard web application |
| `GET` | `/health` | Health check endpoint returning service status |
| `GET` | `/defaults` | Returns default simulation configurations and traffic profiles |
| `GET` | `/algorithms` | Returns metadata, formulas, pros/cons for all 3 schedulers |
| `POST` | `/simulate` | Runs discrete-event simulation for a single selected scheduler |
| `POST` | `/compare` | Generates a single master packet trace and replays it across FCFS, Strict Priority, and WFQ |

---

## 9. Guided Experiments

### Experiment 1: Priority Starvation in Strict Priority
1. Click the **"SP Starvation"** preset button (or set Link Capacity to `6.0 Mbps`, Emergency to `30 pps`, Video to `180 pps`, and File to `280 pps`).
2. Click **"Run Comparison Experiment"**.
3. **Observation:**
   - Under **Strict Priority**, Emergency Messages maintain $< 5\text{ ms}$ delay, but **File Downloads experience severe packet loss ($> 70\%$)** because higher-priority queues are continuously non-empty.
   - Under **Weighted Fair Queuing**, File Downloads receive its proportional share ($w = 1.0$), avoiding starvation.

### Experiment 2: Bufferbloat & Head-of-Line Blocking in FCFS
1. In the configuration panel, enable both **File Downloads** (large 1440B packets) and **Online Gaming** (small 84B packets).
2. Set scheduler mode to **"First-Come First-Served"**.
3. Run simulation.
4. **Observation:**
   - Notice that Gaming packets experience high average delays ($> 25\text{ ms}$) even though their packet sizes are tiny, because they are trapped behind 1440-byte file download packets in the common FIFO buffer.
   - Switch to **WFQ**: Gaming delay drops significantly because WFQ calculates virtual finish times proportional to packet size ($L_i / w_i$).

### Experiment 3: Proportional Bandwidth Sharing in WFQ
1. Click the **"WFQ Fair Share"** preset.
2. Note the configured weights: Emergency ($w=4$), Video ($w=3$), Gaming ($w=2$), File ($w=1$).
3. Run simulation.
4. **Observation:**
   - Review the **Bandwidth Allocation Share vs Configured Weights** donut chart and the **Jain's Fairness Index (Weighted)** KPI ($> 0.95$). Bandwidth is divided in close agreement with the ratio $4 : 3 : 2 : 1$.

---

## 10. Running the Automated Test Suite

Bandwidth Court includes an automated test suite verifying algorithm correctness, event timing, packet drops, fairness math, and REST endpoints:

```bash
python -m pytest -v
```

Expected output:
```
backend/tests/test_api.py::test_health_endpoint PASSED
backend/tests/test_api.py::test_defaults_endpoint PASSED
backend/tests/test_api.py::test_algorithms_endpoint PASSED
backend/tests/test_api.py::test_simulate_endpoint PASSED
backend/tests/test_api.py::test_compare_endpoint PASSED
backend/tests/test_metrics.py::test_jains_fairness_equal_allocation PASSED
backend/tests/test_metrics.py::test_jains_fairness_extreme_unfairness PASSED
backend/tests/test_metrics.py::test_jains_fairness_zero_safety PASSED
backend/tests/test_metrics.py::test_metrics_computation_empty_traffic PASSED
backend/tests/test_schedulers.py::test_fcfs_preserves_arrival_order PASSED
backend/tests/test_schedulers.py::test_strict_priority_dispatches_highest_priority_first PASSED
backend/tests/test_schedulers.py::test_strict_priority_starvation PASSED
backend/tests/test_schedulers.py::test_wfq_considers_weights_and_sizes PASSED
backend/tests/test_schedulers.py::test_wfq_packet_size_normalization PASSED
backend/tests/test_simulation.py::test_serialization_delay_formula PASSED
backend/tests/test_simulation.py::test_queue_overflow_drops PASSED
backend/tests/test_simulation.py::test_reproducible_traffic_generation PASSED

======================== 17 passed in 0.62s ========================
```

---

## 11. Assumptions & Limitations

- **Educational Scope:** Bandwidth Court is a discrete-event educational laboratory modeling queuing dynamics on a single shared bottleneck link. It does not replace real hardware ASIC traffic shapers (e.g. Cisco CBWFQ, Linux `tc-htb`).
- **Propagation Delay:** Propagation delay (time across the wire) is assumed to be negligible compared to queueing and serialization delay on the bottleneck hop.
- **Transport Feedback:** The traffic generator models open-loop packet arrival processes (Poisson). It demonstrates router queue behavior independent of TCP congestion control backoff (AIMD / BBR).
