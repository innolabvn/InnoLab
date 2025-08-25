"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.decorateJsxKey = void 0;
const helpers_1 = require("./helpers");
function decorateJsxKey(rule) {
    return (0, helpers_1.interceptReportForReact)(rule, reportExempting(hasSpreadOperator));
}
exports.decorateJsxKey = decorateJsxKey;
function reportExempting(exemptionCondition) {
    return (context, reportDescriptor) => {
        // check if node has attribute containing spread operator
        if ('node' in reportDescriptor) {
            const { node, ...rest } = reportDescriptor;
            if (exemptionCondition(node)) {
                return;
            }
            context.report({
                node,
                ...rest,
            });
        }
    };
}
function hasSpreadOperator(node) {
    return (node.type === 'JSXElement' &&
        node.openingElement.attributes.some(attribute => attribute.type === 'JSXSpreadAttribute'));
}
//# sourceMappingURL=jsx-key-decorator.js.map