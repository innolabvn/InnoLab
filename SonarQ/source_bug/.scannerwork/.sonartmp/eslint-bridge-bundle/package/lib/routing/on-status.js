"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
/**
 * Handles status requests
 *
 * This endpoint handler allows the sensor to make sure that the bridge is alive
 * and can continue handle analysis requests or any other kind of request.
 */
function default_1(_request, response) {
    response.send('OK!');
}
exports.default = default_1;
//# sourceMappingURL=on-status.js.map