"""Testes do serviço Pedidos."""
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Patch DB e RabbitMQ ANTES de importar app, para evitar conexões reais
@patch("pika.BlockingConnection", MagicMock())
@patch("psycopg.connect", MagicMock())
def get_client():
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
