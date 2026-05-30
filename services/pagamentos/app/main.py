"""
Serviço Pagamentos — Loja Veloz
Consome PedidoCriado do RabbitMQ e simula integração com gateway externo.
Expõe também endpoint síncrono /pagamentos para autorização imediata.
"""
import os
import json
import logging
import threading
import time
from typing import Any

import pika
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from prometheus_fastapi_instrumentator import Instrumentator
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "pagamentos")
APP_VERSION = os.getenv("APP_VERSION", "v1")  # usado para canary

logging.basicConfig(level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","svc":"' + SERVICE_NAME + '","ver":"' + APP_VERSION + '","msg":"%(message)s"}')
log = logging.getLogger(SERVICE_NAME)

app = FastAPI(title="Loja Veloz — Pagamentos", version="1.0.0")
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
FastAPIInstrumentor.instrument_app(app)
tracer = trace.get_tracer(SERVICE_NAME)


class AutorizacaoPagamento(BaseModel):
    pedido_id: str
    valor: float = Field(gt=0)
    metodo: str = Field(pattern="^(cartao|pix|boleto)$")


def consumir_pedidos() -> None:
    """Consumer assíncrono que processa eventos PedidoCriado."""
    while True:
        try:
            params = pika.URLParameters(RABBITMQ_URL)
            conn = pika.BlockingConnection(params)
            ch = conn.channel()
            ch.exchange_declare(exchange="pedidos.events", exchange_type="topic", durable=True)
            q = ch.queue_declare(queue="pagamentos.pedido_criado", durable=True)
            ch.queue_bind(exchange="pedidos.events", queue=q.method.queue, routing_key="pedido.criado")

            def callback(c, method, properties, body):
                try:
                    pedido = json.loads(body)
                    with tracer.start_as_current_span("pagamentos.processar_evento"):
                        log.info(f"processando pagamento pedido={pedido['id']} valor={pedido['total']}")
                        # Simula autorização (em produção, chamaria gateway externo)
                        time.sleep(0.1)
                        log.info(f"pagamento autorizado pedido={pedido['id']}")
                    c.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as e:
                    log.error(f"falha no processamento: {e}")
                    c.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

            ch.basic_qos(prefetch_count=10)
            ch.basic_consume(queue=q.method.queue, on_message_callback=callback)
            log.info("consumer iniciado")
            ch.start_consuming()
        except Exception as e:
            log.error(f"consumer caiu, reconectando em 5s: {e}")
            time.sleep(5)


def _start_background_consumer() -> None:
    if os.getenv("TESTING"):
        log.info("TESTING mode — skipping consumer startup")
        return
    t = threading.Thread(target=consumir_pedidos, daemon=True)
    t.start()


app.add_event_handler("startup", _start_background_consumer)


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "alive", "version": APP_VERSION}


@app.get("/health/ready")
def ready() -> dict[str, str]:
    # Em produção, verificaria conectividade com gateway externo.
    return {"status": "ready"}


@app.post("/pagamentos", status_code=201)
def autorizar(req: AutorizacaoPagamento) -> dict[str, Any]:
    """Autorização síncrona (para fluxos que não dependem do evento)."""
    with tracer.start_as_current_span("pagamentos.autorizar"):
        log.info(f"autorizando pedido={req.pedido_id} valor={req.valor} metodo={req.metodo}")
        if req.valor > 100000:
            raise HTTPException(status_code=402, detail="valor excede limite")
        return {"pedido_id": req.pedido_id, "status": "AUTORIZADO", "version": APP_VERSION}
