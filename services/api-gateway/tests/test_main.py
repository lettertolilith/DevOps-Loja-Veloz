"""Testes unitários do API Gateway."""
import os

os.environ["TESTING"] = "1"

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_live_probe_responde_200():
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "alive"}


def test_metrics_endpoint_exposto():
    r = client.get("/metrics")
    assert r.status_code == 200
    # Prometheus exposition format começa com '# HELP' ou métrica
    assert "http_requests_total" in r.text or "# HELP" in r.text
