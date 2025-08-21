"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.rules = void 0;
const function_calc_no_invalid_1 = require("./function-calc-no-invalid");
/**
 * The set of internal Stylelint-based rules
 */
const rules = {};
exports.rules = rules;
/**
 * Maps Stylelint rule keys to rule implementations
 */
rules[function_calc_no_invalid_1.rule.ruleName] = function_calc_no_invalid_1.rule.rule;
//# sourceMappingURL=index.js.map