"""Testes do serviço Pedidos."""
import os
from unittest.mock import patch, MagicMock

os.environ["TESTING"] = "1"


def get_client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def test_live_probe():
    c = get_client()
    r = c.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "alive"}


def test_payload_invalido_retorna_422():
    c = get_client()
    r = c.post("/pedidos", json={"cliente_id": "abc"})  # sem itens
    assert r.status_code == 422
