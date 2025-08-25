"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getRegexpLocation = void 0;
const helpers_1 = require("linting/eslint/rules/helpers");
const range_1 = require("./range");
/**
 * Gets the regexp node location in the ESLint referential
 * @param node the ESLint regex node
 * @param regexpNode the regexp regex node
 * @param context the rule context
 * @param offset an offset to apply on the location
 * @returns the regexp node location in the ESLint referential
 */
function getRegexpLocation(node, regexpNode, context, offset = [0, 0]) {
    let loc;
    if ((0, helpers_1.isRegexLiteral)(node) || (0, helpers_1.isStringLiteral)(node)) {
        const source = context.getSourceCode();
        const [start] = node.range;
        const [reStart, reEnd] = (0, range_1.getRegexpRange)(node, regexpNode);
        loc = {
            start: source.getLocFromIndex(start + reStart + offset[0]),
            end: source.getLocFromIndex(start + reEnd + offset[1]),
        };
    }
    else {
        loc = node.loc;
    }
    return loc;
}
exports.getRegexpLocation = getRegexpLocation;
//# sourceMappingURL=location.js.map