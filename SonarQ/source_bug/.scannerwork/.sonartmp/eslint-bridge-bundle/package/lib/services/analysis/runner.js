"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.runner = void 0;
const helpers_1 = require("helpers");
/**
 * Runs an analysis
 *
 * This function is a generic analyzer used for any kind of analysis request,
 * be it a YAML, CSS, JavaScrip or TypeScript analysis request. The point is
 * to centralize the extraction of the analysis input, executes the concrete
 * analysis function, and either return the analysis output or forward back
 * any analysis error to the requester.
 *
 * @param analysis the analysis function to run
 */
function runner(analysis) {
    return async (request, response, next) => {
        try {
            const input = request.body;
            if (input.filePath && !input.fileContent) {
                input.fileContent = await (0, helpers_1.readFile)(input.filePath);
            }
            const output = await analysis(input);
            response.json(output);
        }
        catch (error) {
            next(error);
        }
    };
}
exports.runner = runner;
//# sourceMappingURL=runner.js.map