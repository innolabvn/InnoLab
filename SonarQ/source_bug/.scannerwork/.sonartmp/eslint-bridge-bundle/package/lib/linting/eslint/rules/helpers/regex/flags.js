"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getFlags = void 0;
function getFlags(callExpr) {
    if (callExpr.arguments.length < 2) {
        return '';
    }
    const flags = callExpr.arguments[1];
    if (flags.type === 'Literal' && typeof flags.value === 'string') {
        return flags.value;
    }
    return null;
}
exports.getFlags = getFlags;
//# sourceMappingURL=flags.js.map