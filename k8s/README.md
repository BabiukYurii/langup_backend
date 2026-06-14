# Kubernetes manifests (placeholder)

Cloud-ready deployment target. Intended contents:

- `deployment-api.yaml` — FastAPI API Deployment + HPA
- `deployment-worker.yaml` — Celery worker Deployment
- `deployment-beat.yaml` — Celery beat (single replica)
- `deployment-consumer.yaml` — Kafka event consumer Deployment
- `service.yaml`, `ingress.yaml` — Service + Ingress (TLS)
- `configmap.yaml`, `secret.yaml` — environment + secrets
- `migrations-job.yaml` — `alembic upgrade head` as a pre-deploy Job

Each component is independently scalable, which keeps the structure
microservice-ready without splitting the codebase prematurely.
