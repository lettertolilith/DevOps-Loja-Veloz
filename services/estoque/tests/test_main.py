"""Testes do serviço Estoque."""
import os
from unittest.mock import patch, MagicMock

os.environ["TESTING"] = "1"


@patch("app.main.psycopg.connect", MagicMock())
def test_live_probe():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "alive"}
