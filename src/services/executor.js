const { spawn } = require('child_process');
const { addJobLog, updateJobStatus, getJobById } = require('./jobs');
const { loadPipelineDefinition } = require('./pipeline');

function writeCommandOutput(id, level, chunk) {
  const text = chunk.toString().trim();

  if (!text) {
    return;
  }

  for (const line of text.split(/\r?\n/)) {
    const message = line.trim();

    if (!message) {
      continue;
    }

    addJobLog(id, {
      level,
      message,
    });
  }
}

function runCommand(id, command, cwd) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, {
      cwd,
      env: process.env,
      shell: true,
    });

    child.stdout.on('data', (chunk) => {
      writeCommandOutput(id, 'info', chunk);
    });

    child.stderr.on('data', (chunk) => {
      writeCommandOutput(id, 'error', chunk);
    });

    child.on('error', (error) => {
      reject(error);
    });

    child.on('close', (code, signal) => {
      resolve({
        code,
        signal,
      });
    });
  });
}

async function runJob(id) {
  const runningResult = updateJobStatus(id, 'running');

  if (!runningResult.ok) {
    return runningResult;
  }

  addJobLog(id, {
    level: 'info',
    message: 'Executor picked up job from queue',
  });

  const currentJob = getJobById(id);
  const workspacePath = currentJob?.workspacePath || process.cwd();
  const pipelineFile = currentJob?.pipelineFile || '.relay.yml';

  addJobLog(id, {
    level: 'info',
    message: `Using workspace ${workspacePath}`,
  });

  const pipelineResult = loadPipelineDefinition(workspacePath, pipelineFile);

  if (!pipelineResult.ok) {
    addJobLog(id, {
      level: 'error',
      message: `Failed to load pipeline: ${pipelineResult.reason}`,
    });

    return updateJobStatus(id, 'failed');
  }

  addJobLog(id, {
    level: 'info',
      message: `Loaded pipeline from ${pipelineResult.pipelinePath}`,
    });

  for (const step of pipelineResult.pipeline.steps) {
    addJobLog(id, {
      level: 'info',
      message: `Starting step "${step.name}"`,
    });

    addJobLog(id, {
      level: 'info',
      message: `Command: ${step.command}`,
    });

    let result;

    try {
      result = await runCommand(id, step.command, workspacePath);
    } catch (error) {
      addJobLog(id, {
        level: 'error',
        message: `Step "${step.name}" crashed before completion: ${error.message}`,
      });

      return updateJobStatus(id, 'failed');
    }

    if (result.code !== 0) {
      addJobLog(id, {
        level: 'error',
        message: `Step "${step.name}" failed with exit code ${result.code}${
          result.signal ? ` and signal ${result.signal}` : ''
        }`,
      });

      return updateJobStatus(id, 'failed');
    }

    addJobLog(id, {
      level: 'info',
      message: `Step "${step.name}" completed successfully`,
    });
  }

  addJobLog(id, {
    level: 'info',
    message: 'Executor finished all pipeline steps',
  });

  return updateJobStatus(id, 'passed');
}

module.exports = {
  runJob,
};
