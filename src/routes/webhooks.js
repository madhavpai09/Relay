const crypto = require('crypto');
const express = require('express');
const { createJob, getJobByDeliveryId } = require('../services/jobs');
const { shouldCreateJob } = require('../services/eventDecider');
const { buildGithubJobContext } = require('../services/githubContext');
const { getRepositoryByFullName } = require('../services/repositories');
const { scheduleJob } = require('../services/scheduler');


const router = express.Router();

function verifySignature(rawBody, signatureHeader) {
  const secret = process.env.GITHUB_WEBHOOK_SECRET;

  if (!secret) {
    return {
      ok: false,
      reason: 'Missing webhook secret on server',
    };
  }

  if (!signatureHeader) {
    return {
      ok: false,
      reason: 'Missing x-hub-signature-256 header',
    };
  }

  const expectedSignature = `sha256=${crypto
    .createHmac('sha256', secret)
    .update(rawBody)
    .digest('hex')}`;

  const actualBuffer = Buffer.from(signatureHeader);
  const expectedBuffer = Buffer.from(expectedSignature);

  if (actualBuffer.length !== expectedBuffer.length) {
    return {
      ok: false,
      reason: 'Signature length mismatch',
    };
  }

  const isValid = crypto.timingSafeEqual(actualBuffer, expectedBuffer);

  if (!isValid) {
    return {
      ok: false,
      reason: 'Invalid signature',
    };
  }

  return { ok: true };
}

router.post('/', (req, res) => {
    const rawBody = req.body;
    const signatureHeader = req.get('x-hub-signature-256');
    const event = req.get('x-github-event');
    const deliveryId = req.get('x-github-delivery');

    const verification = verifySignature(rawBody, signatureHeader);
    


    if (!verification.ok) {
        return res.status(401).json({
            status: 'rejected',
            reason: verification.reason,
        });
    }

    let payload;

    try {
        payload = JSON.parse(rawBody.toString('utf8'));

        const decision = shouldCreateJob(event, payload);
        if (!decision.shouldCreate) {
            return res.status(202).json({
                status: 'ignored',
                event,
                deliveryId,
                repository: payload.repository?.full_name || null,
                reason: decision.reason,
            });
        }
    } catch (error) {
        return res.status(400).json({
            status: 'rejected',
            reason: 'Invalid JSON payload',
        });
    }

    console.log('Verified GitHub webhook received');
    console.log('Event:', event);
    console.log('Delivery ID:', deliveryId);
    console.log('Repository:', payload.repository?.full_name);

    const existingJob = getJobByDeliveryId(deliveryId);
    const githubContext = buildGithubJobContext(event, payload);
    const registeredRepository = getRepositoryByFullName(githubContext.repository);
    const workspacePath = registeredRepository?.localPath || process.cwd();
    const pipelineFile = registeredRepository?.pipelineFile || '.relay.yml';

    if (existingJob) {
      return res.status(200).json({
        status: 'duplicate',
        event,
        deliveryId,
        repository: githubContext.repository,
        jobId: existingJob.id,
        jobStatus: existingJob.status,
        workspacePath: existingJob.workspacePath || workspacePath,
        reason: 'This webhook delivery was already processed',
      });
    }

    const job = createJob({
        event,
        deliveryId,
        repository: githubContext.repository,
        triggerType: githubContext.triggerType,
        ref: githubContext.ref,
        commitSha: githubContext.commitSha,
        pullRequestNumber: githubContext.pullRequestNumber,
        action: githubContext.action,
        baseRef: githubContext.baseRef,
        headRef: githubContext.headRef,
        workspacePath,
        pipelineFile,
        payload,
    });

    scheduleJob(job.id);

    return res.status(202).json({
        status: 'accepted',
        event,
        deliveryId,
        repository: job.repository,
        jobId: job.id,
        jobStatus: job.status,
        triggerType: job.triggerType,
        ref: job.ref,
        commitSha: job.commitSha,
        pullRequestNumber: job.pullRequestNumber,
        workspacePath: job.workspacePath,
        queueStatus: 'scheduled',
    });

});

module.exports = router;
