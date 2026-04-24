# Relay Master

Relay Master is a lightweight Jenkins-master-style CI controller built with Node.js and Express.

## What it does

- receives GitHub webhooks
- verifies webhook signatures
- filters which events should trigger CI
- deduplicates webhook deliveries
- creates persistent jobs in SQLite
- stores per-job logs
- runs a single local execution queue
- loads pipeline steps from `.relay.yml`
- executes pipeline commands in the registered repository workspace

## Pipeline file

Each registered repository should contain a `.relay.yml` file like this:

```yaml
steps:
  - name: install
    command: npm install
  - name: test
    command: npm test
  - name: build
    command: npm run build
```

## Main endpoints

- `GET /health`
- `GET /repositories`
- `POST /repositories`
- `POST /repositories/:id/validate`
- `DELETE /repositories/:id`
- `POST /webhooks/github`
- `GET /jobs`
- `GET /jobs/:id`
- `GET /jobs/:id/logs`
- `GET /queue`

## Runtime behavior

When a valid GitHub webhook arrives:

1. Relay verifies the webhook signature.
2. Relay decides whether the event should trigger CI.
3. Relay creates a persistent job in SQLite.
4. Relay schedules the job on the local single-runner queue.
5. Relay loads the repo pipeline from `.relay.yml`.
6. Relay executes each command and writes stdout/stderr into job logs.

## Data storage

Runtime data is stored in:

- `data/relay.sqlite`

Legacy JSON migration is supported from:

- `data/jobs.json`
