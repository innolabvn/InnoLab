"use strict";
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
// https://sonarsource.github.io/rspec/#/rspec/S6478/javascript
Object.defineProperty(exports, "__esModule", { value: true });
exports.decorateNoUnstableNestedComponents = void 0;
const helpers_1 = require("./helpers");
function decorateNoUnstableNestedComponents(rule) {
    return (0, helpers_1.interceptReportForReact)(rule, changeMessageWith(urlRemover()));
}
exports.decorateNoUnstableNestedComponents = decorateNoUnstableNestedComponents;
function changeMessageWith(messageChanger) {
    return (context, reportDescriptor) => {
        const report = reportDescriptor;
        if (report.message) {
            report.message = messageChanger(report.message);
        }
        context.report(reportDescriptor);
    };
}
function urlRemover() {
    const urlRegexp = / \(https:[^)]+\)/;
    return (message) => message.replace(urlRegexp, '');
}
//# sourceMappingURL=no-unstable-nested-components.js.map