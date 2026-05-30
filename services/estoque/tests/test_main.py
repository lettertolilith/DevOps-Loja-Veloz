"""Testes do serviço Estoque."""
from unittest.mock import patch, MagicMock


@patch("threading.Thread", MagicMock())
@patch("psycopg.connect", MagicMock())
def test_live_probe():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.get("/health/live")
    assert r.status_code == 200
