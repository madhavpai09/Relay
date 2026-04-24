const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const { database, databaseFilePath } = require('./database');

const allowedStatuses = ['queued', 'running', 'passed', 'failed'];
const legacyJobsFilePath = path.join(path.dirname(databaseFilePath), 'jobs.json');

function ensureJobColumns() {
  const columnDefinitions = [
    ['workspace_path', 'TEXT'],
    ['pipeline_file', 'TEXT'],
  ];

  for (const [columnName, columnType] of columnDefinitions) {
    try {
      database.exec(`ALTER TABLE jobs ADD COLUMN ${columnName} ${columnType}`);
    } catch (error) {
      if (!String(error.message).includes(`duplicate column name: ${columnName}`)) {
        throw error;
      }
    }
  }
}

database.exec(`
  CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    event TEXT NOT NULL,
    delivery_id TEXT NOT NULL UNIQUE,
    repository TEXT,
    trigger_type TEXT,
    ref TEXT,
    commit_sha TEXT,
    pull_request_number INTEGER,
    action TEXT,
    base_ref TEXT,
    head_ref TEXT,
    workspace_path TEXT,
    pipeline_file TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    payload_json TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS job_logs (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
  );

  CREATE INDEX IF NOT EXISTS idx_job_logs_job_id ON job_logs(job_id);
  CREATE INDEX IF NOT EXISTS idx_jobs_delivery_id ON jobs(delivery_id);
`);

ensureJobColumns();

const insertJobStatement = database.prepare(`
  INSERT INTO jobs (
    id,
    event,
    delivery_id,
    repository,
    trigger_type,
    ref,
    commit_sha,
    pull_request_number,
    action,
    base_ref,
    head_ref,
    workspace_path,
    pipeline_file,
    status,
    created_at,
    started_at,
    completed_at,
    payload_json
  ) VALUES (
    @id,
    @event,
    @delivery_id,
    @repository,
    @trigger_type,
    @ref,
    @commit_sha,
    @pull_request_number,
    @action,
    @base_ref,
    @head_ref,
    @workspace_path,
    @pipeline_file,
    @status,
    @created_at,
    @started_at,
    @completed_at,
    @payload_json
  )
`);

const insertLogStatement = database.prepare(`
  INSERT INTO job_logs (
    id,
    job_id,
    timestamp,
    level,
    message
  ) VALUES (
    @id,
    @job_id,
    @timestamp,
    @level,
    @message
  )
`);

const selectAllJobsStatement = database.prepare(`
  SELECT
    id,
    event,
    delivery_id,
    repository,
    trigger_type,
    ref,
    commit_sha,
    pull_request_number,
    action,
    base_ref,
    head_ref,
    workspace_path,
    pipeline_file,
    status,
    created_at,
    started_at,
    completed_at,
    payload_json
  FROM jobs
  ORDER BY created_at DESC
`);

const selectJobByIdStatement = database.prepare(`
  SELECT
    id,
    event,
    delivery_id,
    repository,
    trigger_type,
    ref,
    commit_sha,
    pull_request_number,
    action,
    base_ref,
    head_ref,
    workspace_path,
    pipeline_file,
    status,
    created_at,
    started_at,
    completed_at,
    payload_json
  FROM jobs
  WHERE id = ?
`);

const selectJobByDeliveryIdStatement = database.prepare(`
  SELECT
    id,
    event,
    delivery_id,
    repository,
    trigger_type,
    ref,
    commit_sha,
    pull_request_number,
    action,
    base_ref,
    head_ref,
    workspace_path,
    pipeline_file,
    status,
    created_at,
    started_at,
    completed_at,
    payload_json
  FROM jobs
  WHERE delivery_id = ?
`);

const selectLogsByJobIdStatement = database.prepare(`
  SELECT
    id,
    timestamp,
    level,
    message
  FROM job_logs
  WHERE job_id = ?
  ORDER BY timestamp ASC
`);

const updateJobStatusStatement = database.prepare(`
  UPDATE jobs
  SET
    status = @status,
    started_at = @started_at,
    completed_at = @completed_at
  WHERE id = @id
`);

const countJobsStatement = database.prepare(`
  SELECT COUNT(*) AS count
  FROM jobs
`);

function mapJobRow(row, logs = []) {
  if (!row) {
    return null;
  }

  return {
    id: row.id,
    event: row.event,
    deliveryId: row.delivery_id,
    repository: row.repository,
    triggerType: row.trigger_type,
    ref: row.ref,
    commitSha: row.commit_sha,
    pullRequestNumber: row.pull_request_number,
    action: row.action,
    baseRef: row.base_ref,
    headRef: row.head_ref,
    workspacePath: row.workspace_path,
    pipelineFile: row.pipeline_file,
    status: row.status,
    createdAt: row.created_at,
    startedAt: row.started_at,
    completedAt: row.completed_at,
    logs,
    payload: JSON.parse(row.payload_json),
  };
}

function getLogsForJob(jobId) {
  return selectLogsByJobIdStatement.all(jobId).map((row) => ({
    id: row.id,
    timestamp: row.timestamp,
    level: row.level,
    message: row.message,
  }));
}

function getJobById(id) {
  const row = selectJobByIdStatement.get(id);
  return mapJobRow(row, row ? getLogsForJob(id) : []);
}

function getJobByDeliveryId(deliveryId) {
  const row = selectJobByDeliveryIdStatement.get(deliveryId);
  return mapJobRow(row, row ? getLogsForJob(row.id) : []);
}

function listJobs() {
  return selectAllJobsStatement.all().map((row) => mapJobRow(row, getLogsForJob(row.id)));
}

function insertLog(jobId, { id = crypto.randomUUID(), timestamp = new Date().toISOString(), level = 'info', message }) {
  insertLogStatement.run({
    id,
    job_id: jobId,
    timestamp,
    level,
    message,
  });

  return {
    id,
    timestamp,
    level,
    message,
  };
}

function createJob({
  event,
  deliveryId,
  repository,
  triggerType = event,
  ref = null,
  commitSha = null,
  pullRequestNumber = null,
  action = null,
  baseRef = null,
  headRef = null,
  workspacePath = process.cwd(),
  pipelineFile = '.relay.yml',
  payload,
}) {
  const jobId = crypto.randomUUID();
  const createdAt = new Date().toISOString();

  database.exec('BEGIN');

  try {
    insertJobStatement.run({
      id: jobId,
      event,
      delivery_id: deliveryId,
      repository,
      trigger_type: triggerType,
      ref,
      commit_sha: commitSha,
      pull_request_number: pullRequestNumber,
      action,
      base_ref: baseRef,
      head_ref: headRef,
      workspace_path: workspacePath,
      pipeline_file: pipelineFile,
      status: 'queued',
      created_at: createdAt,
      started_at: null,
      completed_at: null,
      payload_json: JSON.stringify(payload),
    });

    insertLog(jobId, {
      timestamp: createdAt,
      level: 'info',
      message: `Job created for ${triggerType} event`,
    });

    database.exec('COMMIT');
  } catch (error) {
    database.exec('ROLLBACK');
    throw error;
  }

  return getJobById(jobId);
}

function updateJobStatus(id, nextStatus) {
  const job = getJobById(id);

  if (!job) {
    return {
      ok: false,
      reason: 'Job not found',
    };
  }

  if (!allowedStatuses.includes(nextStatus)) {
    return {
      ok: false,
      reason: `Invalid status "${nextStatus}"`,
    };
  }

  const startedAt = nextStatus === 'running' && !job.startedAt ? new Date().toISOString() : job.startedAt;
  const completedAt =
    (nextStatus === 'passed' || nextStatus === 'failed') && !job.completedAt
      ? new Date().toISOString()
      : job.completedAt;

  database.exec('BEGIN');

  try {
    updateJobStatusStatement.run({
      id,
      status: nextStatus,
      started_at: startedAt,
      completed_at: completedAt,
    });

    insertLog(id, {
      level: nextStatus === 'failed' ? 'error' : 'info',
      message: `Job status changed to ${nextStatus}`,
    });

    database.exec('COMMIT');
  } catch (error) {
    database.exec('ROLLBACK');
    throw error;
  }

  return {
    ok: true,
    job: getJobById(id),
  };
}

function canRunJob(id) {
  const job = getJobById(id);

  if (!job) {
    return {
      ok: false,
      reason: 'Job not found',
    };
  }

  if (job.status === 'running') {
    return {
      ok: false,
      reason: 'Job is already running',
    };
  }

  return {
    ok: true,
    job,
  };
}

function addJobLog(id, { level = 'info', message }) {
  const job = getJobById(id);

  if (!job) {
    return {
      ok: false,
      reason: 'Job not found',
    };
  }

  if (!message) {
    return {
      ok: false,
      reason: 'Log message is required',
    };
  }

  const entry = insertLog(id, { level, message });

  return {
    ok: true,
    entry,
    job: getJobById(id),
  };
}

function getJobLogs(id) {
  const job = getJobById(id);

  if (!job) {
    return {
      ok: false,
      reason: 'Job not found',
    };
  }

  return {
    ok: true,
    logs: getLogsForJob(id),
  };
}

function migrateLegacyJsonIfNeeded() {
  const existingJobCount = countJobsStatement.get().count;

  if (existingJobCount > 0 || !fs.existsSync(legacyJobsFilePath)) {
    return;
  }

  const raw = fs.readFileSync(legacyJobsFilePath, 'utf8');
  const parsed = JSON.parse(raw);

  if (!Array.isArray(parsed)) {
    throw new Error('Legacy jobs.json must contain a JSON array');
  }

  for (const legacyJob of parsed) {
    database.exec('BEGIN');

    try {
      const jobId = legacyJob.id || crypto.randomUUID();

      insertJobStatement.run({
        id: jobId,
        event: legacyJob.event,
        delivery_id: legacyJob.deliveryId,
        repository: legacyJob.repository || null,
        trigger_type: legacyJob.triggerType || legacyJob.event || null,
        ref: legacyJob.ref || null,
        commit_sha: legacyJob.commitSha || null,
        pull_request_number: legacyJob.pullRequestNumber || null,
        action: legacyJob.action || null,
        base_ref: legacyJob.baseRef || null,
        head_ref: legacyJob.headRef || null,
        workspace_path: legacyJob.workspacePath || process.cwd(),
        pipeline_file: legacyJob.pipelineFile || '.relay.yml',
        status: legacyJob.status || 'queued',
        created_at: legacyJob.createdAt || new Date().toISOString(),
        started_at: legacyJob.startedAt || null,
        completed_at: legacyJob.completedAt || null,
        payload_json: JSON.stringify(legacyJob.payload || {}),
      });

      for (const legacyLog of legacyJob.logs || []) {
        insertLog(jobId, {
          id: legacyLog.id || crypto.randomUUID(),
          timestamp: legacyLog.timestamp || new Date().toISOString(),
          level: legacyLog.level || 'info',
          message: legacyLog.message || '',
        });
      }

      database.exec('COMMIT');
    } catch (error) {
      database.exec('ROLLBACK');
      throw error;
    }
  }
}

migrateLegacyJsonIfNeeded();

module.exports = {
  createJob,
  listJobs,
  getJobById,
  getJobByDeliveryId,
  updateJobStatus,
  canRunJob,
  addJobLog,
  getJobLogs,
  databaseFilePath,
};
