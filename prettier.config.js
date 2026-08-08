// Prettier only auto-discovers config at the CWD it's invoked from (the
// repo root, per the `format` script in package.json) — re-export the
// shared preset from here so that lookup actually finds it.
module.exports = require("./packages/config/prettier.config.js");
