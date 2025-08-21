"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.addTsConfigIfDirectory = exports.toUnixPath = exports.stripBOM = exports.readFile = void 0;
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
const promises_1 = __importDefault(require("fs/promises"));
const path_1 = __importDefault(require("path"));
/**
 * Byte Order Marker
 */
const BOM_BYTE = 0xfeff;
/**
 * Asynchronous read of file contents from a file path
 *
 * The function gets rid of any Byte Order Marker (BOM)
 * present in the file's header.
 *
 * @param filePath the path of a file
 * @returns Promise which resolves with the content of the file
 */
async function readFile(filePath) {
    const fileContent = await promises_1.default.readFile(filePath, { encoding: 'utf8' });
    return stripBOM(fileContent);
}
exports.readFile = readFile;
/**
 * Removes any Byte Order Marker (BOM) from a string's head
 *
 * A string's head is nothing else but its first character.
 *
 * @param str the input string
 * @returns the stripped string
 */
function stripBOM(str) {
    if (str.charCodeAt(0) === BOM_BYTE) {
        return str.slice(1);
    }
    return str;
}
exports.stripBOM = stripBOM;
/**
 * Converts a path to Unix format
 * @param path the path to convert
 * @returns the converted path
 */
function toUnixPath(path) {
    return path.replace(/[\\/]+/g, '/').replace(/(\.\/)/, '');
}
exports.toUnixPath = toUnixPath;
/**
 * Adds tsconfig.json to a path if it does not exist
 *
 * @param tsConfig
 */
async function addTsConfigIfDirectory(tsConfig) {
    try {
        if ((await promises_1.default.lstat(tsConfig)).isDirectory()) {
            return path_1.default.join(tsConfig, 'tsconfig.json');
        }
        return tsConfig;
    }
    catch (_a) {
        return null;
    }
}
exports.addTsConfigIfDirectory = addTsConfigIfDirectory;
//# sourceMappingURL=files.js.map