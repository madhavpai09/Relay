function buildGithubJobContext(event, payload) {
  const repository = payload.repository?.full_name || null;

  if (event === 'push') {
    return {
      triggerType: 'push',
      repository,
      ref: payload.ref || null,
      commitSha: payload.after || null,
      pullRequestNumber: null,
      action: null,
      baseRef: null,
      headRef: null,
    };
  }

  if (event === 'pull_request') {
    return {
      triggerType: 'pull_request',
      repository,
      ref: payload.pull_request?.head?.ref || null,
      commitSha: payload.pull_request?.head?.sha || null,
      pullRequestNumber: payload.number || payload.pull_request?.number || null,
      action: payload.action || null,
      baseRef: payload.pull_request?.base?.ref || null,
      headRef: payload.pull_request?.head?.ref || null,
    };
  }

  return {
    triggerType: event || 'unknown',
    repository,
    ref: null,
    commitSha: null,
    pullRequestNumber: null,
    action: payload.action || null,
    baseRef: null,
    headRef: null,
  };
}

module.exports = {
  buildGithubJobContext,
};
