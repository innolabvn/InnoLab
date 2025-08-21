"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.decorators = void 0;
const accessor_pairs_decorator_1 = require("./accessor-pairs-decorator");
const brace_style_decorator_1 = require("./brace-style-decorator");
const default_param_last_decorator_1 = require("./default-param-last-decorator");
const jsx_key_decorator_1 = require("./jsx-key-decorator");
const jsx_no_constructed_context_values_1 = require("./jsx-no-constructed-context-values");
const no_dupe_keys_decorator_1 = require("./no-dupe-keys-decorator");
const no_duplicate_imports_decorator_1 = require("./no-duplicate-imports-decorator");
const no_empty_decorator_1 = require("./no-empty-decorator");
const no_empty_function_decorator_1 = require("./no-empty-function-decorator");
const no_extra_semi_decorator_1 = require("./no-extra-semi-decorator");
const no_redeclare_decorator_1 = require("./no-redeclare-decorator");
const no_this_alias_decorator_1 = require("./no-this-alias-decorator");
const no_throw_literal_decorator_1 = require("./no-throw-literal-decorator");
const no_unreachable_decorator_1 = require("./no-unreachable-decorator");
const no_unstable_nested_components_1 = require("./no-unstable-nested-components");
const no_unused_expressions_decorator_1 = require("./no-unused-expressions-decorator");
const object_shorthand_decorator_1 = require("./object-shorthand-decorator");
const prefer_for_of_decorator_1 = require("./prefer-for-of-decorator");
const prefer_template_decorator_1 = require("./prefer-template-decorator");
const semi_decorator_1 = require("./semi-decorator");
const use_isnan_decorator_1 = require("./use-isnan-decorator");
const no_var_decorator_1 = require("./no-var-decorator");
/**
 * The set of internal ESLint rule decorators
 *
 * Once declared here, these decorators are automatically applied
 * to the corresponding rule definitions by the linter's wrapper.
 * There is no further setup required to enable them, except when
 * one needs to test them using ESLint's rule tester.
 */
exports.decorators = {
    'accessor-pairs': accessor_pairs_decorator_1.decorateAccessorPairs,
    'brace-style': brace_style_decorator_1.decorateBraceStyle,
    'default-param-last': default_param_last_decorator_1.decorateDefaultParamLast,
    'jsx-key': jsx_key_decorator_1.decorateJsxKey,
    'jsx-no-constructed-context-values': jsx_no_constructed_context_values_1.decorateJsxNoConstructedContextValues,
    'no-dupe-keys': no_dupe_keys_decorator_1.decorateNoDupeKeys,
    'no-duplicate-imports': no_duplicate_imports_decorator_1.decorateNoDuplicateImports,
    'no-empty': no_empty_decorator_1.decorateNoEmpty,
    'no-empty-function': no_empty_function_decorator_1.decorateNoEmptyFunction,
    'no-extra-semi': no_extra_semi_decorator_1.decorateNoExtraSemi,
    'no-redeclare': no_redeclare_decorator_1.decorateNoRedeclare,
    'no-this-alias': no_this_alias_decorator_1.decorateNoThisAlias,
    'no-throw-literal': no_throw_literal_decorator_1.decorateNoThrowLiteral,
    'no-unreachable': no_unreachable_decorator_1.decorateNoUnreachable,
    'no-unstable-nested-components': no_unstable_nested_components_1.decorateNoUnstableNestedComponents,
    'no-unused-expressions': no_unused_expressions_decorator_1.decorateNoUnusedExpressions,
    'no-var': no_var_decorator_1.decorateNoVar,
    'object-shorthand': object_shorthand_decorator_1.decorateObjectShorthand,
    'prefer-for-of': prefer_for_of_decorator_1.decoratePreferForOf,
    'prefer-template': prefer_template_decorator_1.decoratePreferTemplate,
    semi: semi_decorator_1.decorateSemi,
    'use-isnan': use_isnan_decorator_1.decorateUseIsNan,
};
//# sourceMappingURL=index.js.map