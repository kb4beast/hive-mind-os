const { parsePort } = require('./index');

if (parsePort('80') !== 80) throw new Error('fixture sanity check failed');
