"""Testes do serviço Estoque."""
import os

os.environ["TESTING"] = "1"


def test_live_probe():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "alive"}
