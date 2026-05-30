"""Testes do serviço Pagamentos."""
import os

os.environ["TESTING"] = "1"


def get_client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def test_autorizar_pagamento_ok():
    c = get_client()
    r = c.post("/pagamentos", json={"pedido_id": "abc", "valor": 100.0, "metodo": "pix"})
    assert r.status_code == 201
    assert r.json()["status"] == "AUTORIZADO"


def test_autorizar_pagamento_acima_do_limite():
    c = get_client()
    r = c.post("/pagamentos", json={"pedido_id": "abc", "valor": 200000.0, "metodo": "cartao"})
    assert r.status_code == 402
