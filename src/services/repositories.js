const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const { database } = require('./database');
const { loadPipelineDefinition } = require('./pipeline');

database.exec(`
  CREATE TABLE IF NOT EXISTS repositories (
    id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL UNIQUE,
    provider TEXT NOT NULL,
    local_path TEXT NOT NULL,
    default_branch TEXT,
    pipeline_file TEXT NOT NULL,
    active INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );

  CREATE INDEX IF NOT EXISTS idx_repositories_full_name ON repositories(full_name);
`);

const upsertRepositoryStatement = database.prepare(`
  INSERT INTO repositories (
    id,
    full_name,
    provider,
    local_path,
    default_branch,
    pipeline_file,
    active,
    created_at,
    updated_at
  ) VALUES (
    @id,
    @full_name,
    @provider,
    @local_path,
    @default_branch,
    @pipeline_file,
    @active,
    @created_at,
    @updated_at
  )
  ON CONFLICT(full_name) DO UPDATE SET
    provider = excluded.provider,
    local_path = excluded.local_path,
    default_branch = excluded.default_branch,
    pipeline_file = excluded.pipeline_file,
    active = excluded.active,
    updated_at = excluded.updated_at
`);

const selectAllRepositoriesStatement = database.prepare(`
  SELECT
    id,
    full_name,
    provider,
    local_path,
    default_branch,
    pipeline_file,
    active,
    created_at,
    updated_at
  FROM repositories
  ORDER BY full_name ASC
`);

const selectRepositoryByIdStatement = database.prepare(`
  SELECT
    id,
    full_name,
    provider,
    local_path,
    default_branch,
    pipeline_file,
    active,
    created_at,
    updated_at
  FROM repositories
  WHERE id = ?
`);

const selectRepositoryByFullNameStatement = database.prepare(`
  SELECT
    id,
    full_name,
    provider,
    local_path,
    default_branch,
    pipeline_file,
    active,
    created_at,
    updated_at
  FROM repositories
  WHERE full_name = ?
`);

const deleteRepositoryByIdStatement = database.prepare(`
  DELETE FROM repositories
  WHERE id = ?
`);

function mapRepositoryRow(row) {
  if (!row) {
    return null;
  }

  return {
    id: row.id,
    fullName: row.full_name,
    provider: row.provider,
    localPath: row.local_path,
    defaultBranch: row.default_branch,
    pipelineFile: row.pipeline_file,
    active: Boolean(row.active),
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

function validateLocalRepositoryPath(localPath) {
  if (!localPath) {
    return {
      ok: false,
      reason: 'localPath is required',
    };
  }

  const absolutePath = path.resolve(localPath);

  if (!fs.existsSync(absolutePath)) {
    return {
      ok: false,
      reason: `Repository path does not exist: ${absolutePath}`,
    };
  }

  if (!fs.statSync(absolutePath).isDirectory()) {
    return {
      ok: false,
      reason: `Repository path is not a directory: ${absolutePath}`,
    };
  }

  return {
    ok: true,
    absolutePath,
  };
}

function createOrUpdateRepository({
  fullName,
  provider = 'github',
  localPath,
  defaultBranch = 'main',
  pipelineFile = '.relay.yml',
  active = true,
}) {
  if (!fullName) {
    return {
      ok: false,
      reason: 'fullName is required',
    };
  }

  const pathValidation = validateLocalRepositoryPath(localPath);

  if (!pathValidation.ok) {
    return pathValidation;
  }

  const existingRepository = getRepositoryByFullName(fullName);
  const now = new Date().toISOString();
  const repositoryId = existingRepository?.id || crypto.randomUUID();
  const createdAt = existingRepository?.createdAt || now;

  upsertRepositoryStatement.run({
    id: repositoryId,
    full_name: fullName,
    provider,
    local_path: pathValidation.absolutePath,
    default_branch: defaultBranch,
    pipeline_file: pipelineFile,
    active: active ? 1 : 0,
    created_at: createdAt,
    updated_at: now,
  });

  return {
    ok: true,
    repository: getRepositoryByFullName(fullName),
  };
}

function listRepositories() {
  return selectAllRepositoriesStatement.all().map(mapRepositoryRow);
}

function getRepositoryById(id) {
  return mapRepositoryRow(selectRepositoryByIdStatement.get(id));
}

function getRepositoryByFullName(fullName) {
  return mapRepositoryRow(selectRepositoryByFullNameStatement.get(fullName));
}

function validateRepository(id) {
  const repository = getRepositoryById(id);

  if (!repository) {
    return {
      ok: false,
      reason: 'Repository not found',
    };
  }

  const pathValidation = validateLocalRepositoryPath(repository.localPath);

  if (!pathValidation.ok) {
    return pathValidation;
  }

  const pipelineResult = loadPipelineDefinition(repository.localPath, repository.pipelineFile);

  if (!pipelineResult.ok) {
    return {
      ok: false,
      reason: pipelineResult.reason,
    };
  }

  return {
    ok: true,
    repository,
    pipeline: pipelineResult.pipeline,
    pipelinePath: pipelineResult.pipelinePath,
  };
}

function deleteRepository(id) {
  const repository = getRepositoryById(id);

  if (!repository) {
    return {
      ok: false,
      reason: 'Repository not found',
    };
  }

  deleteRepositoryByIdStatement.run(id);

  return {
    ok: true,
    repository,
  };
}

module.exports = {
  createOrUpdateRepository,
  listRepositories,
  getRepositoryById,
  getRepositoryByFullName,
  validateRepository,
  deleteRepository,
};
