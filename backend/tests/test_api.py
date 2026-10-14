"""Integration tests for FastAPI endpoints.
"""

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_static_frontend_files_served():
    # Test index.html served at root
    res_index = client.get("/")
    assert res_index.status_code == 200
    assert "Bandwidth Court" in res_index.text

    # Test style.css served directly
    res_css = client.get("/style.css")
    assert res_css.status_code == 200
    assert "BANDWIDTH COURT" in res_css.text

    # Test app.js served directly
    res_js = client.get("/app.js")
    assert res_js.status_code == 200
    assert "BANDWIDTH COURT" in res_js.text


def test_defaults_endpoint():
    response = client.get("/defaults")
    assert response.status_code == 200
    data = response.json()
    assert "link_capacity_mbps" in data
    assert "classes" in data
    assert "emergency" in data["classes"]
    assert "video" in data["classes"]
    assert "gaming" in data["classes"]
    assert "file" in data["classes"]


def test_algorithms_endpoint():
    response = client.get("/algorithms")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    ids = [a["id"] for a in data]
    assert "fcfs" in ids
    assert "strict_priority" in ids
    assert "wfq" in ids


def test_simulate_endpoint():
    defaults = client.get("/defaults").json()
    defaults["simulation_duration_sec"] = 2.0  # short run for quick test
    defaults["scheduler_type"] = "wfq"

    response = client.post("/simulate", json=defaults)
    assert response.status_code == 200
    data = response.json()
    assert data["scheduler_type"] == "wfq"
    assert data["total_packets_generated"] > 0
    assert data["total_packets_transmitted"] > 0
    assert "class_metrics" in data
    assert "jains_fairness_index_weighted" in data
    assert len(data["insights"]) > 0


def test_compare_endpoint():
    defaults = client.get("/defaults").json()
    defaults["simulation_duration_sec"] = 2.0

    response = client.post("/compare", json=defaults)
    assert response.status_code == 200
    data = response.json()
    assert "fcfs" in data
    assert "strict_priority" in data
    assert "wfq" in data
    assert "comparison_summary" in data
    assert "synthesis_insights" in data
    assert len(data["comparison_summary"]) > 0

    # Verify identical workload fed to all three algorithms
    fcfs_gen = data["fcfs"]["total_packets_generated"]
    sp_gen = data["strict_priority"]["total_packets_generated"]
    wfq_gen = data["wfq"]["total_packets_generated"]
    assert fcfs_gen == sp_gen == wfq_gen > 0

    for cls_name in ["emergency", "video", "gaming", "file"]:
        fcfs_c = data["fcfs"]["class_metrics"][cls_name]["packets_generated"]
        sp_c = data["strict_priority"]["class_metrics"][cls_name]["packets_generated"]
        wfq_c = data["wfq"]["class_metrics"][cls_name]["packets_generated"]
        assert fcfs_c == sp_c == wfq_c
