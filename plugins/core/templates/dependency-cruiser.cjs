// How dependency-cruiser reads the imports. The components and the components
// each may import are in docs/architecture.json, checked by .github/scripts/architecture.py.
// node_modules is not followed but kept: the slow packages the tests import are read from it.
const fs = require("fs");

module.exports = {
  options: {
    doNotFollow: { path: "(^|/)node_modules/" },
    ...(fs.existsSync("tsconfig.json") ? { tsConfig: { fileName: "tsconfig.json" } } : {}),
  },
};
