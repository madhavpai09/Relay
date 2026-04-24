const fs = require('fs');
const path = require('path');

function applyKeyValue(target, line) {
  const separatorIndex = line.indexOf(':');

  if (separatorIndex === -1) {
    throw new Error(`Invalid pipeline line: "${line}"`);
  }

  const key = line.slice(0, separatorIndex).trim();
  let value = line.slice(separatorIndex + 1).trim();

  if (!key) {
    throw new Error(`Missing key in pipeline line: "${line}"`);
  }

  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    value = value.slice(1, -1);
  }

  target[key] = value;
}

function parseRelayYaml(content) {
  const lines = content.split(/\r?\n/);
  const steps = [];
  let inStepsSection = false;
  let currentStep = null;

  for (const rawLine of lines) {
    const trimmed = rawLine.trim();

    if (!trimmed || trimmed.startsWith('#')) {
      continue;
    }

    if (!inStepsSection) {
      if (trimmed !== 'steps:') {
        throw new Error('Pipeline file must start with a steps: section');
      }

      inStepsSection = true;
      continue;
    }

    if (trimmed.startsWith('- ')) {
      if (currentStep) {
        steps.push(currentStep);
      }

      currentStep = {};
      const remainder = trimmed.slice(2).trim();

      if (remainder) {
        applyKeyValue(currentStep, remainder);
      }

      continue;
    }

    if (!currentStep) {
      throw new Error(`Step property found before step declaration: "${trimmed}"`);
    }

    applyKeyValue(currentStep, trimmed);
  }

  if (currentStep) {
    steps.push(currentStep);
  }

  if (steps.length === 0) {
    throw new Error('Pipeline must contain at least one step');
  }

  for (const step of steps) {
    if (!step.name || !step.command) {
      throw new Error('Each pipeline step must contain both name and command');
    }
  }

  return { steps };
}

function loadPipelineDefinition(workspacePath = process.cwd(), pipelineFile = '.relay.yml') {
  const pipelinePath = path.join(workspacePath, pipelineFile);

  if (!fs.existsSync(pipelinePath)) {
    return {
      ok: false,
      reason: `Pipeline file not found at ${pipelinePath}`,
    };
  }

  try {
    const content = fs.readFileSync(pipelinePath, 'utf8');
    const pipeline = parseRelayYaml(content);

    return {
      ok: true,
      pipelinePath,
      pipeline,
    };
  } catch (error) {
    return {
      ok: false,
      reason: error.message,
    };
  }
}

module.exports = {
  loadPipelineDefinition,
};
