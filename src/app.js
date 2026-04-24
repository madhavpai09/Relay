const express = require('express');
const healthRouter = require('./routes/health');
const webhooksRouter = require('./routes/webhooks');
const jobsRouter = require('./routes/jobs');
const repositoriesRouter = require('./routes/repositories');


function createApp() {
    const app = express();

    app.use('/webhooks/github', express.raw({ type: 'application/json' }), webhooksRouter);
    app.use(express.json());
    app.use(repositoriesRouter);
    app.use(jobsRouter);
    
    app.use(healthRouter);
    

    return app;
}

module.exports = { createApp };
