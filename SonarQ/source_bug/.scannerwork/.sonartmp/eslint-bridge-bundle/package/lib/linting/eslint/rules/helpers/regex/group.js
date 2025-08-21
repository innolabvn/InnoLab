"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.extractReferences = void 0;
const helpers_1 = require("linting/eslint/rules/helpers");
function extractReferences(node) {
    const references = [];
    if ((0, helpers_1.isStringLiteral)(node)) {
        const str = node.value;
        const reg = /\$(\d+)|\$\<([a-zA-Z][a-zA-Z0-9_]*)\>/g;
        let match;
        while ((match = reg.exec(str)) !== null) {
            const [raw, index, name] = match;
            const value = index || name;
            references.push({ raw, value });
        }
    }
    return references;
}
exports.extractReferences = extractReferences;
//# sourceMappingURL=group.js.map