# Relay Master

Relay Master is a FastAPI-based simulated Jenkins system.

It now covers:

- GitHub webhook intake
- SQLite-backed job persistence
- repository registration
- pipeline validation through `.relay.yml`
- queueing and scheduling
- simulated multi-worker execution
- language-aware worker assignment
- random traffic simulation for demo workloads

## Run

```bash
uvicorn main:app --reload --port 8000
```

Then open:

```txt
http://localhost:8000
```

## Worker model

Relay starts with four simulated workers:

- `Python Worker 1`
- `Python Worker 2`
- `Node Worker 1`
- `Universal Worker 1`

Workers are chosen based on:

- repository/job language
- current worker availability
- light randomness to mimic real scheduling pressure

Queued jobs are also selected with a small amount of randomness from the front of the queue so the system feels less perfectly deterministic.

## Repository setup

Register a repository first:

```bash
curl -X POST http://localhost:8000/repositories \
  -H "Content-Type: application/json" \
  -d '{
    "fullName": "owner/repo",
    "provider": "github",
    "localPath": "/absolute/path/to/local/clone",
    "defaultBranch": "main",
    "pipelineFile": ".relay.yml",
    "active": true
  }'
```

Then validate it:

```bash
curl -X POST http://localhost:8000/repositories/REPOSITORY_ID/validate
```

## Pipeline file

Each registered repository should contain a `.relay.yml` file like:

```yaml
language: python
steps:
  - name: install
    command: pip install -r requirements.txt
  - name: test
    command: pytest
  - name: build
    command: python -m compileall .
```

`language` is optional. If omitted, Relay tries to infer it from files like `requirements.txt`, `pyproject.toml`, `package.json`, `pom.xml`, or `go.mod`.

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
- `GET /workers`
- `GET /simulation`
- `POST /simulation/start`
- `POST /simulation/stop`
- `POST /simulation/generate`

## Demo paths

### Real GitHub flow

1. Register the local repository clone.
2. Add `.relay.yml`.
3. Expose Relay with ngrok.
4. Create the GitHub webhook pointing to `/webhooks/github`.
5. Push code.
6. Watch `GET /jobs`, `GET /jobs/{id}/logs`, and `GET /workers`.

### Pure simulation flow

1. Register one or more local repositories.
2. Start the simulation:

```bash
curl -X POST http://localhost:8000/simulation/start \
  -H "Content-Type: application/json" \
  -d '{"minDelaySeconds": 2, "maxDelaySeconds": 5}'
```

3. Or generate a burst immediately:

```bash
curl -X POST http://localhost:8000/simulation/generate \
  -H "Content-Type: application/json" \
  -d '{"count": 4}'
```

4. Inspect queue and workers:

```bash
curl http://localhost:8000/queue
curl http://localhost:8000/workers
curl http://localhost:8000/jobs
```

## Data

- SQLite database: `data/relay.sqlite`
- legacy migration source: `data/jobs.json`
