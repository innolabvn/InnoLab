"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const program_1 = require("services/program");
/**
 * Handles TypeScript Program deletion requests
 */
function default_1(request, response) {
    const { programId } = request.body;
    (0, program_1.deleteProgram)(programId);
    response.send('OK!');
}
exports.default = default_1;
//# sourceMappingURL=on-delete-program.js.map