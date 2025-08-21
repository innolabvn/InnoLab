"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const program_1 = require("services/program");
/**
 * Handles TypeScript Program creation requests
 */
async function default_1(request, response, next) {
    try {
        const { tsConfig } = request.body;
        response.json(await (0, program_1.createProgram)(tsConfig));
    }
    catch (error) {
        next(error);
    }
}
exports.default = default_1;
//# sourceMappingURL=on-create-program.js.map