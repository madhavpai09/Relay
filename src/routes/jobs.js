const express = require('express');
const { listJobs, getJobById } = require('../services/jobs');

const router = express.Router();

router.get('/jobs', (req, res) => {
  res.json({
    jobs: listJobs(),
  });
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

module.exports = router;
