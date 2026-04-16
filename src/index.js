const dotenv = require('dotenv');
const { createApp } = require('./app');

dotenv.config();

const app = createApp();
const PORT = process.env.PORT || 8000;

app.listen(PORT, () => {
  console.log(`Relay master running on port ${PORT}`);
});
