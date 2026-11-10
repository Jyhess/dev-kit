// How dependency-cruiser reads the imports. The components and the components
// each may import are in docs/architecture.json, checked by .github/scripts/architecture.py.
const fs = require("fs");

module.exports = {
  options: {
    doNotFollow: { path: "(^|/)node_modules/" },
    exclude: { path: "(^|/)node_modules/" },
    ...(fs.existsSync("tsconfig.json") ? { tsConfig: { fileName: "tsconfig.json" } } : {}),
  },
};
