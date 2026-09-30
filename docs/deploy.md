# Deploying to a cloud VM

## 1. VM

- Ubuntu 22.04+, at least 4 vCPU / 8 GB RAM (the gaze model is CPU-bound; add cores for more concurrent students).
- A DNS A record for your domain (for example `exam.example.com`) pointing at the VM.
- Firewall: allow 22, 80 and 443 only.
- Install Docker Engine and the Compose plugin.

## 2. Code, secrets and model

```bash
git clone <repo> proctoring && cd proctoring
cp .env.example .env
```

Edit `.env`:

- `ENVIRONMENT=production`
- `SECRET_KEY`: generate with `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`
- strong `POSTGRES_PASSWORD` and `MINIO_SECRET_KEY`
- `DOMAIN`, `ACME_EMAIL`
- `EVIDENCE_RETENTION_DAYS` as agreed with your data-protection officer

Copy the trained model to `backend/models/gaze_model.keras` (scp it; it is not in git).

## 3. Start

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps        # all services should be healthy
curl https://$DOMAIN/api/health                     # {"status":"ok","model_loaded":true}
```

Caddy obtains the TLS certificate automatically. Routing:

| Path | Service |
|---|---|
| `/api/*` | backend (prefix stripped, 4 MB body limit) |
| `/evidence/*` | MinIO (presigned URLs only; the bucket is private) |
| everything else | frontend (nginx, non-root) |

The database and MinIO have no published ports.

## 4. First staff account

Registration is open for students only. Create the first staff user from inside the container:

```bash
docker compose -f docker-compose.prod.yml exec backend python - <<'EOF'
from app.db.session import SessionLocal
from app.core.security import hash_password
from app.models import User, Staff, Role
with SessionLocal() as db:
    u = User(username="admin", email="admin@example.com", full_name="Admin",
             hashed_password=hash_password("CHANGE-ME-NOW"), role=Role.staff)
    db.add(u); db.flush(); db.add(Staff(user_id=u.id)); db.commit()
EOF
```

After that, staff can create other staff through `POST /auth/register` with their token.

## 5. Operations

- **Logs:** `docker compose -f docker-compose.prod.yml logs -f backend`. JSON-file logs are rotated (10 MB × 5).
- **Migrations:** these run automatically on backend start (`alembic upgrade head`).
- **Retention:** the backend purges old evidence daily. To run it manually: `docker compose -f docker-compose.prod.yml exec backend python -m app.services.retention`.
- **Backups:** `docker compose -f docker-compose.prod.yml exec db pg_dump -U $POSTGRES_USER $POSTGRES_DB > backup.sql`. Back up the `miniodata` volume according to your retention policy.
- **Scaling:** raise `UVICORN_WORKERS` and `ML_WORKERS` with the CPU count. Each worker loads its own copy of the model (about 1 GB RAM for EfficientNetV2S). The login rate limiter is per process, so move it to Redis if you run several backend containers.
- **Updates:** `git pull && docker compose -f docker-compose.prod.yml up -d --build`.
