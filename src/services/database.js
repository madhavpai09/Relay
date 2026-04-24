const fs = require('fs');
const path = require('path');
const { DatabaseSync } = require('node:sqlite');

const dataDirectoryPath = path.join(process.cwd(), 'data');
const databaseFilePath = path.join(dataDirectoryPath, 'relay.sqlite');

fs.mkdirSync(dataDirectoryPath, { recursive: true });

const database = new DatabaseSync(databaseFilePath);

module.exports = {
  database,
  dataDirectoryPath,
  databaseFilePath,
};
