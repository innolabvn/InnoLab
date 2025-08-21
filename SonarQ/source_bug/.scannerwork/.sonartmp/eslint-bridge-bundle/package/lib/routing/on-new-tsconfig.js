"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const jsts_1 = require("parsing/jsts");
/**
 * Handles new TSConfig-based analysis requests
 */
function default_1(_request, response) {
    (0, jsts_1.clearTypeScriptESLintParserCaches)();
    response.send('OK!');
}
exports.default = default_1;
//# sourceMappingURL=on-new-tsconfig.js.map