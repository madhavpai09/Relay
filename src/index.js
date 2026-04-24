const dotenv = require('dotenv');
const { createApp } = require('./app');
const { recoverQueueOnStartup } = require('./services/scheduler');

dotenv.config();

const app = createApp();
const PORT = process.env.PORT || 8000;

recoverQueueOnStartup();

app.listen(PORT, () => {
  console.log(`Relay master running on port ${PORT}`);
});
