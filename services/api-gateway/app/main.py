"""API Gateway — Loja Veloz"""
import os
import logging
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

# --- 12-Factor: configuração via ambiente ---
PEDIDOS_URL = os.getenv("PEDIDOS_URL", "http://pedidos:8000")
PAGAMENTOS_URL = os.getenv("PAGAMENTOS_URL", "http://pagamentos:8000")
ESTOQUE_URL = os.getenv("ESTOQUE_URL", "http://estoque:8000")
SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "api-gateway")

# --- Logging estruturado em stdout (12-Factor) ---
logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","svc":"' + SERVICE_NAME + '","msg":"%(message)s"}',
)
log = logging.getLogger(SERVICE_NAME)

app = FastAPI(title="Loja Veloz — API Gateway", version="1.0.0")

# --- Observabilidade ---
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()
tracer = trace.get_tracer(SERVICE_NAME)


@app.get("/health/live")
async def live() -> dict[str, str]:
    """Liveness probe — só responde se o processo está vivo."""
    return {"status": "alive"}


@app.get("/health/ready")
async def ready() -> dict[str, str]:
    """Readiness probe — verifica dependências antes de receber tráfego."""
    async with httpx.AsyncClient(timeout=2.0) as client:
        for name, url in [("pedidos", PEDIDOS_URL), ("estoque", ESTOQUE_URL)]:
            try:
                r = await client.get(f"{url}/health/live")
                if r.status_code != 200:
                    raise HTTPException(status_code=503, detail=f"{name} not ready")
            except httpx.HTTPError as e:
                raise HTTPException(status_code=503, detail=f"{name} unreachable: {e}")
    return {"status": "ready"}


@app.post("/api/v1/pedidos")
async def criar_pedido(payload: dict[str, Any], request: Request) -> JSONResponse:
    """Cria um pedido — encaminha para o serviço Pedidos."""
    with tracer.start_as_current_span("gateway.criar_pedido"):
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{PEDIDOS_URL}/pedidos", json=payload)
        log.info(f"pedido criado status={r.status_code}")
        return JSONResponse(status_code=r.status_code, content=r.json())


@app.get("/api/v1/pedidos/{pedido_id}")
async def obter_pedido(pedido_id: str) -> JSONResponse:
    """Consulta um pedido."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{PEDIDOS_URL}/pedidos/{pedido_id}")
    return JSONResponse(status_code=r.status_code, content=r.json())
