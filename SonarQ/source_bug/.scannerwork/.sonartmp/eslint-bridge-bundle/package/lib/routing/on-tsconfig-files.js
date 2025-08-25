"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const tsconfig_1 = require("services/tsconfig");
/**
 * Handles TSConfig files resolving requests
 *
 * TSConfig-based analysis either for JavaScript or TypeScript requires first
 * resolving the files to be analyzed based on provided TSConfigs. The logic
 * of the whole resolving lies in the bridge since it includes and bundles
 * TypeScript dependency, which is able to parse and analyze TSConfig files.
 */
function default_1(request, response, next) {
    try {
        const tsconfig = request.body.tsconfig;
        response.json((0, tsconfig_1.getFilesForTsConfig)(tsconfig));
    }
    catch (error) {
        next(error);
    }
}
exports.default = default_1;
//# sourceMappingURL=on-tsconfig-files.js.map