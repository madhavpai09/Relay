const crypto = require('crypto');
const express = require('express');
const { createJob } = require('../services/jobs');

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

    const job = createJob({
        event,
        deliveryId,
        repository: payload.repository?.full_name || null,
        payload,
    });

    return res.status(202).json({
        status: 'accepted',
        event,
        deliveryId,
        repository: payload.repository?.full_name || null,
        jobId: job.id,
        jobStatus: job.status,
    });

});

module.exports = router;
