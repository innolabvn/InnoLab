"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || function (mod) {
    if (mod && mod.__esModule) return mod;
    var result = {};
    if (mod != null) for (var k in mod) if (k !== "default" && Object.prototype.hasOwnProperty.call(mod, k)) __createBinding(result, mod, k);
    __setModuleDefault(result, mod);
    return result;
};
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.writeTSConfigFile = exports.getFilesForTsConfig = void 0;
/*
 * SonarQube JavaScript Plugin
 * Copyright (C) 2011-2023 SonarSource SA
 * mailto:info AT sonarsource DOT com
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 3 of the License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public License
 * along with this program; if not, write to the Free Software Foundation,
 * Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
 */
const path = __importStar(require("path"));
const ts = __importStar(require("typescript"));
const tmp_1 = __importDefault(require("tmp"));
const promises_1 = __importDefault(require("fs/promises"));
const util_1 = require("util");
/**
 * Gets the files resolved by a TSConfig
 *
 * The resolving of the files for a given TSConfig file is done
 * by invoking TypeScript compiler.
 *
 * @param tsConfig TSConfig to parse
 * @param parseConfigHost parsing configuration
 * @returns the resolved TSConfig files
 */
function getFilesForTsConfig(tsConfig, parseConfigHost = {
    useCaseSensitiveFileNames: true,
    readDirectory: ts.sys.readDirectory,
    fileExists: ts.sys.fileExists,
    readFile: ts.sys.readFile,
}) {
    const config = ts.readConfigFile(tsConfig, parseConfigHost.readFile);
    if (config.error !== undefined) {
        console.error(`Failed to parse tsconfig: ${tsConfig} (${config.error.messageText})`);
        throw Error(diagnosticToString(config.error));
    }
    const parsed = ts.parseJsonConfigFileContent(config.config, parseConfigHost, path.resolve(path.dirname(tsConfig)), {
        noEmit: true,
    }, undefined, undefined, [
        {
            extension: '.vue',
            scriptKind: ts.ScriptKind.Deferred,
            isMixedContent: true,
        },
    ]);
    if (parsed.errors.length > 0) {
        let error = '';
        parsed.errors.forEach(d => {
            error += diagnosticToString(d);
        });
        throw new Error(error);
    }
    const projectReferences = parsed.projectReferences
        ? parsed.projectReferences.map(p => p.path)
        : [];
    return { files: parsed.fileNames, projectReferences };
}
exports.getFilesForTsConfig = getFilesForTsConfig;
/**
 * Any temporary file created with the `tmp` library will be removed once the Node.js process terminates.
 */
tmp_1.default.setGracefulCleanup();
/**
 * Create the TSConfig file and returns its path.
 *
 * The file is written in a temporary location in the file system and is marked to be removed after Node.js process terminates.
 *
 * @param tsConfig TSConfig to write
 * @returns the resolved TSConfig file path
 */
async function writeTSConfigFile(tsConfig) {
    const filename = await (0, util_1.promisify)(tmp_1.default.file)();
    await promises_1.default.writeFile(filename, JSON.stringify(tsConfig), 'utf-8');
    return { filename };
}
exports.writeTSConfigFile = writeTSConfigFile;
function diagnosticToString(diagnostic) {
    if (typeof diagnostic.messageText === 'string') {
        return diagnostic.messageText;
    }
    else {
        return diagnostic.messageText.messageText;
    }
}
//# sourceMappingURL=tsconfig.js.map