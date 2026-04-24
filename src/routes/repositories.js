const express = require('express');

const {
  createOrUpdateRepository,
  listRepositories,
  getRepositoryById,
  validateRepository,
  deleteRepository,
} = require('../services/repositories');

const router = express.Router();

router.get('/repositories', (req, res) => {
  res.json({
    repositories: listRepositories(),
  });
});

router.get('/repositories/:id', (req, res) => {
  const repository = getRepositoryById(req.params.id);

  if (!repository) {
    return res.status(404).json({
      error: 'Repository not found',
    });
  }

  return res.json(repository);
});

router.post('/repositories', (req, res) => {
  const {
    fullName,
    provider,
    localPath,
    defaultBranch,
    pipelineFile,
    active,
  } = req.body;

  const result = createOrUpdateRepository({
    fullName,
    provider,
    localPath,
    defaultBranch,
    pipelineFile,
    active,
  });

  if (!result.ok) {
    return res.status(400).json({
      error: result.reason,
    });
  }

  return res.status(201).json({
    message: 'Repository saved',
    repository: result.repository,
  });
});

router.post('/repositories/:id/validate', (req, res) => {
  const result = validateRepository(req.params.id);

  if (!result.ok) {
    const statusCode = result.reason === 'Repository not found' ? 404 : 400;

    return res.status(statusCode).json({
      error: result.reason,
    });
  }

  return res.json({
    message: 'Repository configuration is valid',
    repository: result.repository,
    pipelinePath: result.pipelinePath,
    pipeline: result.pipeline,
  });
});

router.delete('/repositories/:id', (req, res) => {
  const result = deleteRepository(req.params.id);

  if (!result.ok) {
    return res.status(404).json({
      error: result.reason,
    });
  }

  return res.json({
    message: 'Repository deleted',
    repository: result.repository,
  });
});

module.exports = router;
