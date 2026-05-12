# Relay Master

Relay Master is a FastAPI-based simulated Jenkins system.

It now covers:

- GitHub webhook intake
- SQLite-backed job persistence
- repository registration
- pipeline validation through `.relay.yml`
- queueing and scheduling
- deterministic priority-based queue scheduling
- simulated multi-worker execution
- language-aware worker assignment
- branch-aware traffic simulation for demo workloads

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

Queued jobs are selected deterministically by priority score, then by enqueue time.

Priority is computed from webhook facts instead of randomness:

- direct pushes outrank pull request jobs
- pushes to the default branch outrank every other branch
- `release/*` and `hotfix/*` branches are next
- tracked shared branches such as `develop` and `staging` come after that
- larger push batches get a small deterministic bump

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
    "trackedBranches": ["main", "develop"],
    "pipelineFile": ".relay.yml",
    "active": true
  }'
```

Then validate it:

```bash
curl -X POST http://localhost:8000/repositories/REPOSITORY_ID/validate
```

Repository verification now checks all of the following:

- the configured local path exists and is a directory
- the directory is a valid Git repository
- the repository has an `origin` remote
- the `origin` remote matches the registered `owner/repo`
- the default branch and tracked branches exist in local refs or `origin/*`
- the configured `.relay.yml` exists and parses successfully

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
4. In GitHub, open `Repository -> Settings -> Webhooks -> Add webhook` and point the payload URL to `https://YOUR-NGROK-DOMAIN/webhooks/github`.
5. Push code.
6. Watch `GET /jobs`, `GET /jobs/{id}/logs`, and `GET /workers`.

### Pure simulation flow

1. Register at least 3 active repositories, and give each repository at least 2 tracked branches.
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

Relay will only start the simulation when it can cover at least 3 repositories and 6 distinct tracked branches.
When simulation jobs are generated, branch pushes rotate across those tracked branches so each one flows through the CI/CD pipeline.

4. Inspect queue and workers:

```bash
curl http://localhost:8000/queue
curl http://localhost:8000/workers
curl http://localhost:8000/jobs
```

## Data

- SQLite database: `data/relay.sqlite`
- legacy migration source: `data/jobs.json`

## Finals notes

### 1. How to deploy this CI system on cloud

The current app is easiest to deploy as a single FastAPI service behind a public HTTPS endpoint:

1. Containerize the app with Python, the Relay codebase, and any build tools your pipelines need.
2. Deploy it on a VM or container platform such as EC2, Render, Railway, Fly.io, or Kubernetes.
3. Mount persistent storage for `data/relay.sqlite`, or swap SQLite for Postgres if you want safer multi-instance scaling.
4. Set `GITHUB_WEBHOOK_SECRET` in the cloud environment.
5. Put a reverse proxy or load balancer in front of the app so GitHub can reach `POST /webhooks/github`.
6. Register each target repository in Relay with its local checkout or mounted workspace path and `.relay.yml`.

For a serious production version, the next upgrade would be:

- Postgres instead of SQLite
- a durable background queue
- worker processes separated from the web server
- ephemeral per-job workspaces instead of one shared checkout

### 2. When the system can fail

Known failure cases include:

- GitHub cannot reach the webhook endpoint because ngrok/cloud ingress is down.
- `GITHUB_WEBHOOK_SECRET` is missing or does not match the secret configured in GitHub.
- the registered repository `localPath` does not exist on the server.
- the repository is missing `.relay.yml`, or the file contains invalid Relay pipeline syntax.
- pipeline commands fail because dependencies are missing on the worker host.
- SQLite becomes a bottleneck if multiple app instances try to share the same database.
- low-priority jobs can wait a long time if high-priority branch pushes keep arriving.

### 3. Where the GitHub webhook is registered

Relay receives GitHub webhook deliveries at:

- `POST /webhooks/github`

Registration itself is not automated inside this project right now. It is configured manually in GitHub here:

- `Repository -> Settings -> Webhooks`

The exact public payload URL should be:

- `https://YOUR-PUBLIC-HOST/webhooks/github`

When using local development, `YOUR-PUBLIC-HOST` is normally the ngrok HTTPS URL.

### 4. How ngrok works here

ngrok creates a secure public tunnel from the internet to your local FastAPI server. In this project the flow is:

1. Relay runs locally on something like `http://localhost:8000`.
2. ngrok opens a public HTTPS URL and forwards incoming requests to that local port.
3. GitHub sends webhook events to the ngrok URL.
4. ngrok forwards the request to Relay's `/webhooks/github` route.
5. Relay verifies the HMAC signature, computes priority, stores the job, and schedules it.

That means ngrok is only the tunnel. The webhook verification and job creation still happen inside Relay.
