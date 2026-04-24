const express = require('express');
const {
  listJobs,
  getJobById,
  updateJobStatus,
  canRunJob,
  addJobLog,
  getJobLogs,
} = require('../services/jobs');
const { runJob } = require('../services/executor');
const { getQueueSnapshot, scheduleJob } = require('../services/scheduler');

const router = express.Router();

router.get('/jobs', (req, res) => {
  res.json({
    jobs: listJobs(),
  });
});

router.get('/queue', (req, res) => {
  res.json(getQueueSnapshot());
});

router.get('/jobs/:id', (req, res) => {
  const job = getJobById(req.params.id);

  if (!job) {
    return res.status(404).json({
      error: 'Job not found',
    });
  }

  return res.json(job);
});

router.get('/jobs/:id/logs', (req, res) => {
  const result = getJobLogs(req.params.id);

  if (!result.ok) {
    return res.status(404).json({
      error: result.reason,
    });
  }

  return res.json({
    logs: result.logs,
  });
});

router.patch('/jobs/:id/status', (req, res) => {
  const { status } = req.body;
  const result = updateJobStatus(req.params.id, status);

  if (!result.ok) {
    const statusCode = result.reason === 'Job not found' ? 404 : 400;

    return res.status(statusCode).json({
      error: result.reason,
    });
  }

  return res.json({
    message: 'Job status updated',
    job: result.job,
  });
});

router.post('/jobs/:id/run', async (req, res) => {
  const runnable = canRunJob(req.params.id);

  if (!runnable.ok) {
    const statusCode = runnable.reason === 'Job not found' ? 404 : 400;

    return res.status(statusCode).json({
      error: runnable.reason,
    });
  }

  const result = await runJob(req.params.id);

  if (!result.ok) {
    const statusCode = result.reason === 'Job not found' ? 404 : 400;

    return res.status(statusCode).json({
      error: result.reason,
    });
  }

  return res.json({
    message: 'Job run completed',
    job: result.job,
  });
});

router.post('/jobs/:id/schedule', (req, res) => {
  const result = scheduleJob(req.params.id);

  if (!result.ok) {
    const statusCode = result.reason === 'Job not found' ? 404 : 400;

    return res.status(statusCode).json({
      error: result.reason,
    });
  }

  return res.status(202).json({
    message: 'Job scheduled',
    job: result.job,
  });
});

router.post('/jobs/:id/logs', (req, res) => {
  const { level, message } = req.body;
  const result = addJobLog(req.params.id, { level, message });

  if (!result.ok) {
    const statusCode = result.reason === 'Job not found' ? 404 : 400;

    return res.status(statusCode).json({
      error: result.reason,
    });
  }

  return res.status(201).json({
    message: 'Job log added',
    log: result.entry,
  });
});

module.exports = router;
