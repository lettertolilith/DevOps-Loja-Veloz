"""Serviço Estoque — Loja Veloz"""
import os
import json
import logging
import threading
import time
from typing import Any

import pika
import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from prometheus_fastapi_instrumentator import Instrumentator
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://app:app@postgres:5432/estoque")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "estoque")

logging.basicConfig(level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","svc":"' + SERVICE_NAME + '","msg":"%(message)s"}')
log = logging.getLogger(SERVICE_NAME)

app = FastAPI(title="Loja Veloz — Estoque", version="1.0.0")
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
FastAPIInstrumentor.instrument_app(app)
tracer = trace.get_tracer(SERVICE_NAME)


def get_db() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL, autocommit=True)


def init_schema() -> None:
    try:
        with get_db() as conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS estoque (
                    sku TEXT PRIMARY KEY,
                    quantidade INT NOT NULL CHECK (quantidade >= 0),
                    reservado INT NOT NULL DEFAULT 0
                );
                INSERT INTO estoque (sku, quantidade) VALUES
                    ('SKU-001', 100), ('SKU-002', 50), ('SKU-003', 200)
                ON CONFLICT (sku) DO NOTHING;
            """)
        log.info("schema inicializado")
    except Exception as e:
        log.error(f"falha schema: {e}")


def reservar_itens(itens: list[dict[str, Any]]) -> bool:
    with get_db() as conn, conn.cursor() as cur:
        for it in itens:
            cur.execute(
                "UPDATE estoque SET reservado = reservado + %s WHERE sku = %s AND quantidade - reservado >= %s",
                (it["quantidade"], it["sku"], it["quantidade"])
            )
            if cur.rowcount == 0:
                return False
    return True


def consumir_pedidos() -> None:
    while True:
        try:
            params = pika.URLParameters(RABBITMQ_URL)
            conn = pika.BlockingConnection(params)
            ch = conn.channel()
            ch.exchange_declare(exchange="pedidos.events", exchange_type="topic", durable=True)
            q = ch.queue_declare(queue="estoque.pedido_criado", durable=True)
            ch.queue_bind(exchange="pedidos.events", queue=q.method.queue, routing_key="pedido.criado")

            def callback(c, method, properties, body):
                try:
                    pedido = json.loads(body)
                    with tracer.start_as_current_span("estoque.reservar"):
                        ok = reservar_itens(pedido["itens"])
                        if ok:
                            log.info(f"estoque reservado pedido={pedido['id']}")
                        else:
                            log.warning(f"estoque insuficiente pedido={pedido['id']}")
                    c.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as e:
                    log.error(f"falha processamento: {e}")
                    c.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

            ch.basic_qos(prefetch_count=10)
            ch.basic_consume(queue=q.method.queue, on_message_callback=callback)
            log.info("consumer estoque iniciado")
            ch.start_consuming()
        except Exception as e:
            log.error(f"consumer caiu, reconectando em 5s: {e}")
            time.sleep(5)


def _start_background_consumer() -> None:
    """Inicia o consumer RabbitMQ em background (exceto em testes)."""
    if os.getenv("TESTING"):
        log.info("TESTING mode — skipping consumer startup")
        return
    threading.Thread(target=consumir_pedidos, daemon=True).start()


def _startup() -> None:
    if not os.getenv("TESTING"):
        init_schema()
    _start_background_consumer()


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


@app.get("/estoque/{sku}")
def consultar(sku: str) -> dict[str, Any]:
    with get_db() as conn, conn.cursor() as cur:
        cur.execute("SELECT sku, quantidade, reservado FROM estoque WHERE sku = %s", (sku,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="sku não encontrado")
    return {"sku": row[0], "disponivel": row[1] - row[2], "reservado": row[2]}
