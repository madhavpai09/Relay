const crypto = require('crypto');

const jobs = [];

function createJob({ event, deliveryId, repository, payload }) {
  const job = {
    id: crypto.randomUUID(),
    event,
    deliveryId,
    repository,
    status: 'queued',
    createdAt: new Date().toISOString(),
    payload,
  };

  jobs.push(job);
  return job;
}

function listJobs() {
  return jobs;
}

function getJobById(id) {
  return jobs.find((job) => job.id === id) || null;
}

module.exports = {
  createJob,
  listJobs,
  getJobById,
};
