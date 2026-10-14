/**
 * BANDWIDTH COURT — SIMPLE PLAYGROUND CONTROLLER
 * Minimal, Fast, Crystal-Clear Network Simulation UI
 */

const API_BASE = window.location.origin.includes(':8000') || window.location.protocol === 'http:'
  ? (window.location.port === '8000' ? '' : 'http://127.0.0.1:8000')
  : 'http://127.0.0.1:8000';

const state = {
  currentAlgo: 'compare', // 'fcfs' | 'strict_priority' | 'wfq' | 'compare'
  latestData: null,
  activeEvents: [],
  eventIndex: 0,
  isPlaying: false,
  animSpeed: 1.0,
  animIntervalId: null,
  chart: null,
  queueState: { emergency: [], video: [], gaming: [], file: [] },
  txCount: 0,
  dropCount: 0,
};

document.addEventListener('DOMContentLoaded', () => {
  initHealthCheck();
  bindAlgoPicker();
  bindSlider();
  bindScenarios();
  bindRunButton();
  bindAnimator();

  // Run on page load
  runSimulation();
});

// ==========================================================================
// 1. HEALTH CHECK
// ==========================================================================
async function initHealthCheck() {
  const dot = document.getElementById('backend-status-dot');
  const txt = document.getElementById('backend-status-text');
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (res.ok) {
      dot.className = 'dot green';
      txt.textContent = 'Engine Online';
    } else {
      throw new Error();
    }
  } catch (e) {
    dot.className = 'dot red';
    txt.textContent = 'Engine Offline';
  }
}

// ==========================================================================
// 2. CONTROLS BINDING
// ==========================================================================
function bindAlgoPicker() {
  const btns = document.querySelectorAll('.algo-btn');
  btns.forEach((btn) => {
    btn.addEventListener('click', () => {
      btns.forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      state.currentAlgo = btn.dataset.algo;

      const compareSection = document.getElementById('compare-section');
      if (state.currentAlgo === 'compare') {
        compareSection.style.display = 'block';
        document.getElementById('run-btn-label').textContent = 'Compare All 3';
      } else {
        compareSection.style.display = 'none';
        const labels = {
          fcfs: 'Simulate FCFS',
          strict_priority: 'Simulate Strict Priority',
          wfq: 'Simulate WFQ',
        };
        document.getElementById('run-btn-label').textContent = labels[state.currentAlgo] || 'Simulate';
      }

      runSimulation();
    });
  });
}

function bindSlider() {
  const slider = document.getElementById('input-link-capacity');
  const valLabel = document.getElementById('lbl-link-speed');
  const pipeLabel = document.getElementById('lbl-pipe-cap');

  slider.addEventListener('input', (e) => {
    const val = `${e.target.value} Mbps`;
    valLabel.textContent = val;
    pipeLabel.textContent = `Capacity: ${val}`;
  });
}

function bindScenarios() {
  document.querySelectorAll('.btn-scenario').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.btn-scenario').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');

      const preset = btn.dataset.preset;
      const slider = document.getElementById('input-link-capacity');

      if (preset === 'normal') {
        slider.value = 10;
        document.getElementById('rate-emergency').value = 8;
        document.getElementById('rate-video').value = 100;
        document.getElementById('rate-gaming').value = 140;
        document.getElementById('rate-file').value = 220;
      } else if (preset === 'congestion') {
        slider.value = 4;
        document.getElementById('rate-emergency').value = 10;
        document.getElementById('rate-video').value = 140;
        document.getElementById('rate-gaming').value = 160;
        document.getElementById('rate-file').value = 280;
      } else if (preset === 'starvation') {
        slider.value = 6;
        document.getElementById('rate-emergency').value = 35;
        document.getElementById('rate-video').value = 180;
        document.getElementById('rate-gaming').value = 120;
        document.getElementById('rate-file').value = 300;
      }

      document.getElementById('lbl-link-speed').textContent = `${slider.value} Mbps`;
      document.getElementById('lbl-pipe-cap').textContent = `Capacity: ${slider.value} Mbps`;
      runSimulation();
    });
  });
}

function bindRunButton() {
  document.getElementById('btn-run-sim').addEventListener('click', () => {
    runSimulation();
  });
}

// ==========================================================================
// 3. EXECUTION WORKFLOW
// ==========================================================================
function getPayload() {
  const cap = parseFloat(document.getElementById('input-link-capacity').value);
  const dur = parseFloat(document.getElementById('input-duration')?.value || 5.0);
  const seed = parseInt(document.getElementById('input-seed')?.value || 42, 10);

  const getRate = (id, def) => parseFloat(document.getElementById(id)?.value || def);

  return {
    link_capacity_mbps: cap,
    simulation_duration_sec: dur,
    random_seed: seed,
    scheduler_type: state.currentAlgo === 'compare' ? 'wfq' : state.currentAlgo,
    global_queue_capacity: null,
    classes: {
      emergency: {
        name: 'emergency',
        display_name: 'Emergency Messages',
        enabled: true,
        arrival_rate_pps: getRate('rate-emergency', 8),
        packet_size_bytes: 128,
        packet_size_jitter_bytes: 20,
        priority: 1,
        wfq_weight: 4.0,
        queue_capacity: 30,
      },
      video: {
        name: 'video',
        display_name: 'Video Calls',
        enabled: true,
        arrival_rate_pps: getRate('rate-video', 100),
        packet_size_bytes: 960,
        packet_size_jitter_bytes: 100,
        priority: 2,
        wfq_weight: 3.0,
        queue_capacity: 60,
      },
      gaming: {
        name: 'gaming',
        display_name: 'Online Gaming',
        enabled: true,
        arrival_rate_pps: getRate('rate-gaming', 140),
        packet_size_bytes: 84,
        packet_size_jitter_bytes: 15,
        priority: 3,
        wfq_weight: 2.0,
        queue_capacity: 50,
      },
      file: {
        name: 'file',
        display_name: 'File Downloads',
        enabled: true,
        arrival_rate_pps: getRate('rate-file', 220),
        packet_size_bytes: 1440,
        packet_size_jitter_bytes: 50,
        priority: 4,
        wfq_weight: 1.0,
        queue_capacity: 80,
      },
    },
  };
}

async function runSimulation() {
  const btnLabel = document.getElementById('run-btn-label');
  const oldText = btnLabel.textContent;
  btnLabel.textContent = 'Simulating...';

  const payload = getPayload();
  const endpoint = state.currentAlgo === 'compare' ? `${API_BASE}/compare` : `${API_BASE}/simulate`;

  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) throw new Error();

    const data = await res.json();
    state.latestData = data;

    if (state.currentAlgo === 'compare') {
      renderCompareMode(data);
      setupAnimation(data.wfq);
    } else {
      renderSingleMode(data);
      setupAnimation(data);
    }
  } catch (err) {
    console.error('Simulation error:', err);
  } finally {
    btnLabel.textContent = oldText;
  }
}

// ==========================================================================
// 4. RENDERING SIMPLE METRICS & TAKEAWAYS
// ==========================================================================
function renderSingleMode(data) {
  updateKPIs(data);
  updateTakeaways(data.insights);
  renderSimpleChart(data);
  document.getElementById('lbl-active-algo').textContent = `${data.scheduler_name}`;
}

function renderCompareMode(data) {
  // Update KPIs based on WFQ
  updateKPIs(data.wfq);
  updateTakeaways(data.synthesis_insights);
  populateCompareCards(data);
  renderSimpleChart(data.wfq);
  document.getElementById('lbl-active-algo').textContent = 'WFQ / 3-Way Replay';
}

function updateKPIs(data) {
  document.getElementById('kpi-tp').innerHTML = `${data.total_throughput_mbps.toFixed(1)} <small>Mbps</small>`;
  document.getElementById('kpi-tp-sub').textContent = `out of ${data.link_capacity_mbps} Mbps (${data.link_utilization_pct.toFixed(0)}% link busy)`;

  document.getElementById('kpi-delay').innerHTML = `${data.avg_packet_delay_ms.toFixed(1)} <small>ms</small>`;
  document.getElementById('kpi-loss').textContent = `${data.packet_loss_rate_pct.toFixed(1)}%`;
  document.getElementById('kpi-loss-sub').textContent = `${data.total_packets_dropped} packets dropped`;

  document.getElementById('kpi-fair').innerHTML = `${data.jains_fairness_index_weighted.toFixed(2)} <small>/ 1.0</small>`;
}

function updateTakeaways(insights) {
  const container = document.getElementById('takeaway-text');
  if (!insights || insights.length === 0) {
    container.innerHTML = '<p>Traffic flowed within service limits.</p>';
    return;
  }

  // Display top 2 cleanest, most direct insights in plain English
  const topInsights = insights.slice(0, 2);
  container.innerHTML = topInsights.map((t) => `<p>• ${t}</p>`).join('');
}

function populateCompareCards(data) {
  const fcfs = data.fcfs;
  const sp = data.strict_priority;
  const wfq = data.wfq;

  // FCFS
  document.getElementById('tp-fcfs').textContent = `${fcfs.total_throughput_mbps.toFixed(1)} Mbps`;
  document.getElementById('del-fcfs').textContent = `${fcfs.avg_packet_delay_ms.toFixed(1)} ms`;
  document.getElementById('loss-fcfs').textContent = `${fcfs.class_metrics.file.packet_loss_rate_pct.toFixed(1)}%`;
  document.getElementById('fair-fcfs').textContent = `${fcfs.jains_fairness_index_weighted.toFixed(2)}`;

  // Strict Priority
  document.getElementById('tp-sp').textContent = `${sp.total_throughput_mbps.toFixed(1)} Mbps`;
  document.getElementById('del-sp-em').textContent = `${sp.class_metrics.emergency.avg_delay_ms.toFixed(1)} ms`;
  document.getElementById('loss-sp').textContent = `${sp.class_metrics.file.packet_loss_rate_pct.toFixed(1)}%`;
  document.getElementById('fair-sp').textContent = `${sp.jains_fairness_index_weighted.toFixed(2)}`;

  // WFQ
  document.getElementById('tp-wfq').textContent = `${wfq.total_throughput_mbps.toFixed(1)} Mbps`;
  document.getElementById('del-wfq').textContent = `${wfq.avg_packet_delay_ms.toFixed(1)} ms`;
  document.getElementById('loss-wfq').textContent = `${wfq.class_metrics.file.packet_loss_rate_pct.toFixed(1)}%`;
  document.getElementById('fair-wfq').textContent = `${wfq.jains_fairness_index_weighted.toFixed(2)}`;
}

// ==========================================================================
// 5. SIMPLE CLEAN CHART
// ==========================================================================
function renderSimpleChart(data) {
  if (state.chart) state.chart.destroy();

  const ctx = document.getElementById('simple-chart').getContext('2d');
  const classes = ['emergency', 'video', 'gaming', 'file'];
  const labels = ['🚨 Emergency', '📹 Video Call', '🎮 Gaming', '📁 File Download'];
  const colors = [
    'rgba(239, 68, 68, 0.85)',
    'rgba(6, 182, 212, 0.85)',
    'rgba(16, 185, 129, 0.85)',
    'rgba(245, 158, 11, 0.85)',
  ];

  const tps = classes.map((c) => data.class_metrics[c]?.throughput_mbps || 0);

  state.chart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Throughput (Mbps)',
        data: tps,
        backgroundColor: colors,
        borderRadius: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.raw.toFixed(2)} Mbps`,
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: '#cbd5e1', font: { family: 'Inter', size: 12, weight: '600' } },
        },
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(51, 65, 85, 0.3)' },
          ticks: { color: '#94a3b8' },
          title: { display: true, text: 'Throughput (Mbps)', color: '#94a3b8' },
        },
      },
    },
  });
}

// ==========================================================================
// 6. ANIMATOR
// ==========================================================================
function setupAnimation(simResult) {
  state.activeEvents = simResult.packet_events || [];
  state.eventIndex = 0;
  resetAnimationDOM();

  if (state.activeEvents.length > 0) {
    startPlayback();
  }
}

function resetAnimationDOM() {
  stopPlayback();
  state.eventIndex = 0;
  state.txCount = 0;
  state.dropCount = 0;
  state.queueState = { emergency: [], video: [], gaming: [], file: [] };

  document.getElementById('sim-clock').textContent = 'Time: 0.00 s';
  document.getElementById('val-delivered-count').textContent = '0';
  document.getElementById('val-dropped-count').textContent = '0';
  document.getElementById('tx-carrier').innerHTML = '<span class="idle-txt">No Packet</span>';
  document.getElementById('pipe-status').textContent = 'LINK IDLE';
  document.getElementById('pipe-status').className = 'link-status-badge';
  document.getElementById('pipe-meter').style.width = '0%';

  ['emergency', 'video', 'gaming', 'file'].forEach((c) => {
    document.getElementById(`buf-${c}`).innerHTML = '<span class="empty-txt">Empty</span>';
    document.getElementById(`cnt-${c}`).textContent = '0';
  });
}

function bindAnimator() {
  const playBtn = document.getElementById('btn-anim-play');
  playBtn.addEventListener('click', () => {
    if (state.isPlaying) {
      stopPlayback();
      playBtn.textContent = '▶ Play';
    } else {
      startPlayback();
      playBtn.textContent = '⏸ Pause';
    }
  });

  document.getElementById('btn-anim-step').addEventListener('click', () => {
    stopPlayback();
    playBtn.textContent = '▶ Play';
    stepEvent();
  });

  document.getElementById('btn-anim-reset').addEventListener('click', () => {
    resetAnimationDOM();
    playBtn.textContent = '▶ Play';
  });

  document.getElementById('select-anim-speed').addEventListener('input', (e) => {
    state.animSpeed = parseFloat(e.target.value);
    if (state.isPlaying) {
      stopPlayback();
      startPlayback();
    }
  });
}

function startPlayback() {
  if (state.animIntervalId) clearInterval(state.animIntervalId);
  state.isPlaying = true;

  if (state.animSpeed >= 999) {
    while (state.eventIndex < state.activeEvents.length) {
      stepEvent();
    }
    stopPlayback();
    document.getElementById('btn-anim-play').textContent = '▶ Play';
    return;
  }

  const interval = Math.max(12, Math.floor(45 / state.animSpeed));
  state.animIntervalId = setInterval(() => {
    if (state.eventIndex >= state.activeEvents.length) {
      stopPlayback();
      document.getElementById('btn-anim-play').textContent = '▶ Play';
      return;
    }
    stepEvent();
  }, interval);
}

function stopPlayback() {
  state.isPlaying = false;
  if (state.animIntervalId) {
    clearInterval(state.animIntervalId);
    state.animIntervalId = null;
  }
}

function stepEvent() {
  if (state.eventIndex >= state.activeEvents.length) return;

  const ev = state.activeEvents[state.eventIndex];
  state.eventIndex++;

  document.getElementById('sim-clock').textContent = `Time: ${ev.time_sec.toFixed(2)} s`;
  const c = ev.traffic_class;

  switch (ev.event_type) {
    case 'enqueued': {
      state.queueState[c].push(ev);
      updateQueueDOM(c);
      break;
    }

    case 'dropped': {
      state.dropCount++;
      document.getElementById('val-dropped-count').textContent = state.dropCount;
      break;
    }

    case 'tx_start': {
      if (state.queueState[c].length > 0) {
        state.queueState[c].shift();
        updateQueueDOM(c);
      }

      document.getElementById('tx-carrier').innerHTML = `<span class="packet-chip pkt-${c}">${ev.packet_id} (${ev.size_bytes}B)</span>`;
      const pipeStatus = document.getElementById('pipe-status');
      pipeStatus.textContent = `TRANSMITTING (${c.toUpperCase()})`;
      pipeStatus.className = 'link-status-badge busy';

      const meter = document.getElementById('pipe-meter');
      meter.style.width = '0%';
      requestAnimationFrame(() => {
        meter.style.width = '100%';
      });
      break;
    }

    case 'tx_complete': {
      state.txCount++;
      document.getElementById('val-delivered-count').textContent = state.txCount;

      document.getElementById('tx-carrier').innerHTML = '<span class="idle-txt">No Packet</span>';
      const pipeStatus = document.getElementById('pipe-status');
      pipeStatus.textContent = 'LINK IDLE';
      pipeStatus.className = 'link-status-badge';
      document.getElementById('pipe-meter').style.width = '0%';
      break;
    }
  }

  // Update counts
  if (ev.queue_lengths) {
    ['emergency', 'video', 'gaming', 'file'].forEach((cls) => {
      const len = ev.queue_lengths[cls] !== undefined ? ev.queue_lengths[cls] : state.queueState[cls].length;
      document.getElementById(`cnt-${cls}`).textContent = len;
    });
  }
}

function updateQueueDOM(cls) {
  const buf = document.getElementById(`buf-${cls}`);
  if (!buf) return;

  const q = state.queueState[cls];
  if (q.length === 0) {
    buf.innerHTML = '<span class="empty-txt">Empty</span>';
    return;
  }

  const visible = q.slice(0, 5);
  let html = visible.map((p) => `<span class="packet-chip pkt-${cls}">${p.size_bytes}B</span>`).join('');
  if (q.length > 5) html += `<span class="packet-chip pkt-${cls}">+${q.length - 5}</span>`;
  buf.innerHTML = html;
}
