const { listJobs, getJobById, addJobLog, updateJobStatus } = require('./jobs');
const { runJob } = require('./executor');

let currentJobId = null;

function getQueuedJobs() {
  return listJobs()
    .filter((job) => job.status === 'queued')
    .sort((left, right) => left.createdAt.localeCompare(right.createdAt));
}

function getQueueSnapshot() {
  const jobs = listJobs();

  return {
    currentJobId,
    queuedJobs: jobs
      .filter((job) => job.status === 'queued')
      .sort((left, right) => left.createdAt.localeCompare(right.createdAt))
      .map((job) => ({
        id: job.id,
        repository: job.repository,
        triggerType: job.triggerType,
        createdAt: job.createdAt,
        ref: job.ref,
      })),
    runningJobs: jobs
      .filter((job) => job.status === 'running')
      .map((job) => ({
        id: job.id,
        repository: job.repository,
        triggerType: job.triggerType,
        startedAt: job.startedAt,
      })),
  };
}

async function processQueue() {
  if (currentJobId) {
    return;
  }

  const nextJob = getQueuedJobs()[0];

  if (!nextJob) {
    return;
  }

  currentJobId = nextJob.id;

  try {
    await runJob(nextJob.id);
  } catch (error) {
    addJobLog(nextJob.id, {
      level: 'error',
      message: `Scheduler crashed while running job: ${error.message}`,
    });

    updateJobStatus(nextJob.id, 'failed');
  } finally {
    currentJobId = null;

    if (getQueuedJobs().length > 0) {
      setImmediate(() => {
        processQueue();
      });
    }
  }
}

function scheduleJob(id) {
  const job = getJobById(id);

  if (!job) {
    return {
      ok: false,
      reason: 'Job not found',
    };
  }

  if (job.status !== 'queued') {
    return {
      ok: false,
      reason: `Job must be queued before scheduling, current status is ${job.status}`,
    };
  }

  setImmediate(() => {
    processQueue();
  });

  return {
    ok: true,
    job,
  };
}

function recoverQueueOnStartup() {
  const runningJobs = listJobs().filter((job) => job.status === 'running');

  for (const job of runningJobs) {
    addJobLog(job.id, {
      level: 'error',
      message: 'Master restarted while this job was running',
    });

    updateJobStatus(job.id, 'failed');
  }

  if (getQueuedJobs().length > 0) {
    setImmediate(() => {
      processQueue();
    });
  }
}

module.exports = {
  getQueueSnapshot,
  scheduleJob,
  recoverQueueOnStartup,
};
