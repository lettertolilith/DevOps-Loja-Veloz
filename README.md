# Loja Veloz — Pedidos Veloz 🚀

**Trabalho acadêmico — Cloud DevOps: Orchestrating Containers and Microservices**
**Aluno:** Renan Gomes Mendes De Castro
**RA:** 103686
**Instituição:** Centro Universitário UniFECAF

> Entrega contínua de uma plataforma de pedidos em microsserviços: do Docker Compose ao Kubernetes com observabilidade e CI/CD.

---

## 📑 Sumário

- [Arquitetura](#arquitetura)
- [Stack](#stack)
- [Pré-requisitos](#pré-requisitos)
- [Subir o ambiente local (1 comando)](#subir-o-ambiente-local-1-comando)
- [Smoke test](#smoke-test)
- [Deploy em Kubernetes (Minikube/Kind)](#deploy-em-kubernetes-minikubekind)
- [Estrutura do repositório](#estrutura-do-repositório)
- [CI/CD](#cicd)
- [Observabilidade](#observabilidade)
- [Documentação técnica](#documentação-técnica)

---

## Arquitetura

```
                     ┌──────────────────────┐
        Cliente ───▶ │  Istio Ingress GW    │ ──┐
                     └──────────────────────┘   │
                                                ▼
                                      ┌──────────────────┐
                                      │   API Gateway    │ (FastAPI)
                                      └────────┬─────────┘
                              ┌────────────────┼────────────────┐
                              ▼                ▼                ▼
                       ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
                       │  Pedidos    │  │ Pagamentos  │  │   Estoque   │
                       │  (FastAPI)  │  │  (FastAPI)  │  │  (FastAPI)  │
                       └──────┬──────┘  └──────▲──────┘  └──────▲──────┘
                              │                │                │
                              │ publica        │ consome        │ consome
                              ▼                │                │
                       ┌─────────────────────────────────────────┐
                       │            RabbitMQ (events)            │
                       │     exchange: pedidos.events            │
                       │     routing-key: pedido.criado          │
                       └─────────────────────────────────────────┘
                              ▲                                  ▲
                              │                                  │
                       ┌──────┴──────────────────────────────────┴──────┐
                       │              PostgreSQL                        │
                       │     databases: pedidos, estoque                │
                       └────────────────────────────────────────────────┘

   Observabilidade: serviços → OTel Collector → Prometheus (métricas) + Jaeger (traces)
   Malha (prod):    mTLS STRICT + canary 95/5 v1/v2 em Pagamentos via Istio
```

Detalhes em [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Stack

| Camada              | Tecnologia                                                    |
| ------------------- | ------------------------------------------------------------- |
| Linguagem           | Python 3.12 + FastAPI                                         |
| Banco de dados      | PostgreSQL 16                                                 |
| Mensageria          | RabbitMQ 3.13 (exchange topic, durable queues)                |
| Conteinerização     | Docker (multi-stage, non-root, healthcheck)                   |
| Orquestração local  | Docker Compose                                                |
| Orquestração prod   | Kubernetes (Minikube/Kind local, EKS em produção)             |
| Service Mesh        | Istio 1.23 (mTLS STRICT, canary deployment, retries)          |
| Observabilidade     | OpenTelemetry + Prometheus + Jaeger + Grafana                 |
| CI/CD               | GitHub Actions (matrix por serviço, Trivy scan, OIDC para AWS)|
| IaC                 | Terraform (VPC + EKS + Node Groups)                           |

---

## Pré-requisitos

- Docker 24+ e Docker Compose v2
- (Opcional para K8s) `kubectl`, `kustomize`, e Minikube **ou** Kind
- (Opcional para IaC) Terraform 1.6+ e AWS CLI configurado

---

## Subir o ambiente local (1 comando)

```bash
# 1. Copie as variáveis de ambiente
cp .env.example .env

# 2. Suba TODA a stack (4 serviços + Postgres + RabbitMQ + OTel + Jaeger + Prometheus + Grafana)
docker compose up --build -d

# 3. Acompanhe os logs
docker compose logs -f api-gateway pedidos
```

**Portas expostas:**

| Serviço          | URL                        | Descrição                  |
| ---------------- | -------------------------- | -------------------------- |
| API Gateway      | http://localhost:8080      | Entrada HTTP da aplicação  |
| RabbitMQ UI      | http://localhost:15672     | guest / guest              |
| Jaeger UI        | http://localhost:16686     | Tracing distribuído        |
| Prometheus       | http://localhost:9090      | Métricas                   |
| Grafana          | http://localhost:3000      | admin / admin              |
| Postgres         | localhost:5432             | app / app                  |

---

## Smoke test

```bash
# Criar um pedido
curl -X POST http://localhost:8080/api/v1/pedidos \
  -H "Content-Type: application/json" \
  -d '{
    "cliente_id": "cliente-001",
    "itens": [
      {"sku": "SKU-001", "quantidade": 2, "preco_unitario": 49.90},
      {"sku": "SKU-002", "quantidade": 1, "preco_unitario": 129.00}
    ]
  }'

# Consultar (use o id retornado acima)
curl http://localhost:8080/api/v1/pedidos/<UUID>

# Ver o evento sendo consumido por Pagamentos e Estoque
docker compose logs pagamentos estoque | grep -i "pedido"
```

---

## Deploy em Kubernetes (Minikube/Kind)

```bash
# 1. Subir cluster local
minikube start --cpus=4 --memory=6g --kubernetes-version=v1.30.0
# OU
kind create cluster --name loja-veloz

# 2. (Opcional) Instalar Istio
istioctl install --set profile=demo -y

# 3. Aplicar manifests (overlay dev)
kubectl apply -k k8s/overlays/dev

# 4. Acompanhar rollout
kubectl -n loja-veloz get pods -w

# 5. Port-forward do API Gateway
kubectl -n loja-veloz port-forward svc/api-gateway 8080:8000

# 6. Aplicar configs Istio (canary + mTLS)
kubectl apply -f k8s/istio/

# 7. Testar HPA — gerar carga
kubectl run -it --rm load --image=busybox --restart=Never -- \
  sh -c "while true; do wget -q -O- http://api-gateway.loja-veloz.svc:8000/health/ready; done"

kubectl -n loja-veloz get hpa -w
```

---

## Estrutura do repositório

```
loja-veloz/
├── README.md                       ← este arquivo
├── docker-compose.yml              ← stack completa local
├── .env.example                    ← variáveis de ambiente
├── .gitignore
│
├── services/                       ← 4 microsserviços FastAPI
│   ├── api-gateway/
│   │   ├── Dockerfile              ← multi-stage, non-root
│   │   ├── requirements.txt
│   │   ├── app/main.py
│   │   └── tests/test_main.py
│   ├── pedidos/                    ← publica evento PedidoCriado
│   ├── pagamentos/                 ← consome evento, autoriza
│   └── estoque/                    ← consome evento, reserva itens
│
├── k8s/
│   ├── base/                       ← manifests base (Kustomize)
│   │   ├── 00-namespace.yaml       ← Pod Security Admission restricted
│   │   ├── 01-configmap.yaml
│   │   ├── 02-secret.yaml
│   │   ├── 10-postgres.yaml        ← StatefulSet
│   │   ├── 11-rabbitmq.yaml
│   │   ├── 20-api-gateway.yaml     ← Deployment + Service + SA
│   │   ├── 21-pedidos.yaml
│   │   ├── 22-pagamentos.yaml      ← v1 stable, v2 via canary
│   │   ├── 23-estoque.yaml
│   │   ├── 30-hpa-pdb.yaml         ← HPAs + PodDisruptionBudgets
│   │   ├── 40-network-policy.yaml  ← default-deny + allows
│   │   └── kustomization.yaml
│   ├── overlays/
│   │   ├── dev/                    ← réplicas reduzidas
│   │   └── prod/                   ← réplicas + Istio configs
│   ├── istio/                      ← Gateway, VS, DR, mTLS, canary
│   └── observability/              ← OTel Collector, Prometheus
│
├── .github/workflows/
│   ├── ci.yml                      ← lint + test + build + scan + push (matrix)
│   └── cd.yml                      ← deploy via OIDC + kustomize + rollout
│
├── terraform/                      ← IaC (esqueleto)
│   ├── main.tf, variables.tf, terraform.tfvars.example
│   └── modules/{vpc,eks}/main.tf
│
├── docs/
│   ├── ARCHITECTURE.md             ← decisões + diagramas
│   ├── Relatorio_Teorico.pdf       ← Parte Teórica (entregável 1)
│   └── Relatorio_Tecnico_Pratico.pdf ← Parte Prática (entregável 2)
│
└── scripts/
    └── init-multiple-dbs.sh        ← cria DBs no Postgres (compose)
```

---

## CI/CD

- **Trigger:** push em `main`, tags `v*.*.*` ou pull requests
- **Pipeline (matrix paralela por serviço):**
  1. `ruff` (lint)
  2. `pytest --cov` (testes + cobertura)
  3. `docker buildx` (build multi-stage)
  4. `trivy` (scan de vulnerabilidades CRITICAL/HIGH, SARIF para Security tab)
  5. `docker push` para `ghcr.io/loja-veloz/<service>:<sha|semver>`
  6. `kubeconform` valida manifests K8s
- **CD:** workflow `cd.yml` autentica via OIDC (sem secrets de longo prazo), faz `kustomize edit set image`, aplica e aguarda rollout.

---

## Observabilidade

- **Métricas:** `prometheus-fastapi-instrumentator` expõe `/metrics` em cada serviço (formato Prometheus)
- **Traces:** SDK do OpenTelemetry instrumenta FastAPI e HTTPX → OTel Collector → Jaeger
- **Logs:** stdout em JSON (12-Factor) → coletado pelo runtime do container → agregador (Loki em prod)
- **Dashboards:** Grafana com datasources Prometheus + Jaeger pré-configurados

---

## Documentação técnica

| Documento                              | Conteúdo                                       |
| -------------------------------------- | ---------------------------------------------- |
| [`docs/Relatorio_Teorico.pdf`](docs/Relatorio_Teorico.pdf) | Parte Teórica — fundamentação e decisões |
| [`docs/Relatorio_Tecnico_Pratico.pdf`](docs/Relatorio_Tecnico_Pratico.pdf) | Parte Prática — implementação detalhada |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Diagramas, fluxos e decisões                 |

---

**Referência arquitetural:** [Google Cloud Online Boutique (microservices-demo)](https://github.com/GoogleCloudPlatform/microservices-demo)
