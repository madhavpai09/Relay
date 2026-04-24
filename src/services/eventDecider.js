function shouldCreateJob(event, payload) {
  if (event === 'push') {
    return {
      shouldCreate: true,
      reason: 'Push events should trigger CI',
    };
  }

  if (event === 'pull_request') {
    const action = payload.action;

    const allowedActions = ['opened', 'synchronize', 'reopened'];

    if (allowedActions.includes(action)) {
      return {
        shouldCreate: true,
        reason: `Pull request action "${action}" should trigger CI`,
      };
    }

    return {
      shouldCreate: false,
      reason: `Pull request action "${action}" does not trigger CI`,
    };
  }

  return {
    shouldCreate: false,
    reason: `Event "${event}" does not trigger CI jobs`,
  };
}

module.exports = { shouldCreateJob };
