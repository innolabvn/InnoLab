"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const eslint_1 = require("linting/eslint");
/**
 * Handles initialization requests of the global ESLint linter wrappers
 *
 * The bridge relies on a global ESLint linter wrapper for JavaScript
 * and TypeScript analysis. Before any analysis, the linter wrapper
 * must be initialized explicitly, which includes the rules from the
 * active quality profile the linter must consider as well as global
 * variables ann JavaScript execution environments.
 */
function default_1(request, response) {
    const { rules, environments, globals, linterId } = request.body;
    (0, eslint_1.initializeLinter)(rules, environments, globals, linterId);
    response.send('OK!');
}
exports.default = default_1;
//# sourceMappingURL=on-init-linter.js.map