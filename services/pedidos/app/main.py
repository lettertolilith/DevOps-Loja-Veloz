"""Serviço Pedidos — Loja Veloz"""
import os
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Any

import pika
import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from prometheus_fastapi_instrumentator import Instrumentator
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# --- Configuração (12-Factor III) ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://app:app@postgres:5432/pedidos")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "pedidos")
EXCHANGE = "pedidos.events"

logging.basicConfig(level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","svc":"' + SERVICE_NAME + '","msg":"%(message)s"}')
log = logging.getLogger(SERVICE_NAME)

app = FastAPI(title="Loja Veloz — Pedidos", version="1.0.0")
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
FastAPIInstrumentor.instrument_app(app)
tracer = trace.get_tracer(SERVICE_NAME)


class ItemPedido(BaseModel):
    sku: str
    quantidade: int = Field(gt=0)
    preco_unitario: float = Field(gt=0)


class NovoPedido(BaseModel):
    cliente_id: str
    itens: list[ItemPedido]


def get_db() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL, autocommit=True)


def init_schema() -> None:
    """Cria tabela se não existir."""
    try:
        with get_db() as conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pedidos (
                    id UUID PRIMARY KEY,
                    cliente_id TEXT NOT NULL,
                    total NUMERIC(10,2) NOT NULL,
                    status TEXT NOT NULL DEFAULT 'CRIADO',
                    itens JSONB NOT NULL,
                    criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
                );
            """)
        log.info("schema inicializado")
    except Exception as e:
        log.error(f"falha ao inicializar schema: {e}")


def publicar_evento(pedido: dict[str, Any]) -> None:
    """Publica PedidoCriado de forma assíncrona via RabbitMQ."""
    try:
        params = pika.URLParameters(RABBITMQ_URL)
        with pika.BlockingConnection(params) as conn:
            ch = conn.channel()
            ch.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
            ch.basic_publish(
                exchange=EXCHANGE,
                routing_key="pedido.criado",
                body=json.dumps(pedido, default=str).encode(),
                properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
            )
        log.info(f"evento PedidoCriado publicado id={pedido['id']}")
    except Exception as e:
        log.error(f"falha ao publicar evento: {e}")


def _startup() -> None:
    if not os.getenv("TESTING"):
        init_schema()


app.add_event_handler("startup", _startup)


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/health/ready")
def ready() -> dict[str, str]:
    try:
        with get_db() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        return {"status": "ready"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"db unreachable: {e}")


@app.post("/pedidos", status_code=201)
def criar(body: NovoPedido) -> dict[str, Any]:
    with tracer.start_as_current_span("pedidos.criar"):
        pid = str(uuid.uuid4())
        total = sum(i.quantidade * i.preco_unitario for i in body.itens)
        itens_json = json.dumps([i.model_dump() for i in body.itens])
        with get_db() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pedidos (id, cliente_id, total, itens) VALUES (%s,%s,%s,%s)",
                (pid, body.cliente_id, total, itens_json),
            )
        pedido = {
            "id": pid,
            "cliente_id": body.cliente_id,
            "total": total,
            "status": "CRIADO",
            "itens": [i.model_dump() for i in body.itens],
            "criado_em": datetime.now(timezone.utc).isoformat(),
        }
        publicar_evento(pedido)
        return pedido


@app.get("/pedidos/{pedido_id}")
def obter(pedido_id: str) -> dict[str, Any]:
    with get_db() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, cliente_id, total, status, itens, criado_em FROM pedidos WHERE id = %s", (pedido_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="pedido não encontrado")
    return {
        "id": str(row[0]), "cliente_id": row[1], "total": float(row[2]),
        "status": row[3], "itens": row[4], "criado_em": row[5].isoformat(),
    }
