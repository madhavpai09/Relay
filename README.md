# Relay Master

Relay Master is now a FastAPI-based Jenkins-master-style CI controller.

## Run

```bash
uvicorn main:app --reload --port 8000
```

## What it does

- receives GitHub webhooks
- verifies webhook signatures
- filters CI-relevant events
- deduplicates deliveries
- persists jobs and logs in SQLite
- registers local repositories
- validates `.relay.yml`
- schedules queued jobs automatically
- executes pipeline commands in the registered repo workspace

## Main endpoints

- `GET /health`
- `GET /repositories`
- `POST /repositories`
- `GET /repositories/{id}`
- `POST /repositories/{id}/validate`
- `DELETE /repositories/{id}`
- `POST /webhooks/github`
- `GET /jobs`
- `GET /jobs/{id}`
- `GET /jobs/{id}/logs`
- `PATCH /jobs/{id}/status`
- `POST /jobs/{id}/schedule`
- `POST /jobs/{id}/run`
- `POST /jobs/{id}/logs`
- `GET /queue`

## Pipeline file

Each registered repository should contain a `.relay.yml` file like:

```yaml
steps:
  - name: install
    command: npm install
  - name: test
    command: npm test
  - name: build
    command: npm run build
```

## Data

- SQLite database: `data/relay.sqlite`
- Legacy migration source: `data/jobs.json`

## Note

The older Node/Express implementation is still present in `src/` as legacy reference, but the supported runtime is now FastAPI.
