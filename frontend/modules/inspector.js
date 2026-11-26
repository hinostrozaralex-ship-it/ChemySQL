/**
 * Módulo de Inspector Profesional para ChemySQL.
 * Integra 4 vistas contextuales bilingües (ES/EN):
 *   1. Inspector de Proyecto / Base de Datos (cuando no hay elemento seleccionado): propiedades globales y COLLATE.
 *   2. Inspector de Tabla enriquecido: resumen de PK/FK/índices, lista clicable de columnas, Ver Datos, Copiar CREATE TABLE.
 *   3. Inspector de Columna completo: todos los tipos SQL, longitud, DEFAULT, CHECK, GENERATED ALWAYS AS, PK, UNIQUE, NULL e INDEX.
 *   4. Pre-análisis SQL en tiempo real (Live Script Inspector): detecta paréntesis/comillas sin cerrar, comas sobrantes,
 *      puntos y comas faltantes y tablas inexistentes antes de ejecutar, con salto directo a la línea exacta.
 */

import { escapeHtml, showToast } from "./core.js";

const SQL_COLUMN_TYPES = [
    "INTEGER",
    "INT",
    "SMALLINT",
    "TINYINT",
    "BIGINT",
    "VARCHAR",
    "CHAR",
    "DECIMAL(10,2)",
    "DECIMAL(5,2)",
    "DECIMAL(4,1)",
    "DATE",
    "TIME",
    "DATETIME",
    "BOOLEAN",
    "TEXT",
    "FLOAT",
];

const COLLATIONS = [
    { value: "", labelEs: "Sin cotejamiento específico", labelEn: "Default / None" },
    { value: "utf8mb4_0900_ai_ci", labelEs: "utf8mb4_0900_ai_ci (Insensible mayús. y tildes)", labelEn: "utf8mb4_0900_ai_ci (Case & Accent Insensitive)" },
    { value: "utf8mb4_spanish_ci", labelEs: "utf8mb4_spanish_ci (Español CI)", labelEn: "utf8mb4_spanish_ci (Spanish CI)" },
    { value: "Modern_Spanish_CI_AI", labelEs: "Modern_Spanish_CI_AI (SQL Server CI/AI)", labelEn: "Modern_Spanish_CI_AI (SQL Server CI/AI)" },
    { value: "NOCASE", labelEs: "NOCASE (SQLite insensible mayús.)", labelEn: "NOCASE (SQLite Case Insensitive)" },
];

/**
 * Analizador estático determinista en vivo del código SQL (< 1 ms).
 * Detecta incidencias antes de pulsar Ejecutar SQL y devuelve su número de línea exacto.
 */
export function analyzeSQLScriptLive(sqlText, contract, lang = "es") {
    const isEn = lang === "en";
    const text = String(sqlText || "");
    const lines = text.split("\n");
    const issues = [];

    // 1. Comprobar comillas simples y paréntesis desbalanceados línea a línea
    let inSingleQuote = false;
    let quoteStartLine = 1;
    const parenStack = [];

    for (let li = 0; li < lines.length; li++) {
        const line = lines[li];
        const lineNum = li + 1;
        for (let ci = 0; ci < line.length; ci++) {
            const ch = line[ci];
            const next = line[ci + 1] || "";
            if (!inSingleQuote && ch === "-" && next === "-") {
                break; // comentario de línea
            }
            if (ch === "'") {
                if (inSingleQuote && next === "'") {
                    ci++; // comilla escapada ''
                    continue;
                }
                if (!inSingleQuote) {
                    inSingleQuote = true;
                    quoteStartLine = lineNum;
                } else {
                    inSingleQuote = false;
                }
                continue;
            }
            if (inSingleQuote) continue;
            if (ch === "(") {
                parenStack.push(lineNum);
            } else if (ch === ")") {
                if (parenStack.length === 0) {
                    issues.push({
                        severity: "error",
                        line: lineNum,
                        message: isEn
                            ? "Extra closing parenthesis ')' with no matching '('."
                            : "Paréntesis de cierre ')' sobrante sin '(' correspondiente.",
                    });
                } else {
                    parenStack.pop();
                }
            }
        }
    }

    if (inSingleQuote) {
        issues.push({
            severity: "error",
            line: quoteStartLine,
            message: isEn
                ? "Unclosed single-quoted string literal (')."
                : "Cadena de texto con comilla simple (') sin cerrar.",
        });
    }
    if (parenStack.length > 0) {
        const openLine = parenStack[parenStack.length - 1];
        issues.push({
            severity: "error",
            line: openLine,
            message: isEn
                ? `Unclosed opening parenthesis '(' (${parenStack.length} pending).`
                : `Paréntesis '(' sin cerrar (${parenStack.length} pendiente${parenStack.length > 1 ? "s" : ""}).`,
        });
    }

    // 2. Coma sobrante justo antes de cierre de paréntesis ', )' (error clásico en CREATE TABLE)
    for (let li = 0; li < lines.length; li++) {
        const stripped = lines[li].replace(/--.*$/, "").trim();
        if (stripped.endsWith(",")) {
            let nxt = li + 1;
            while (nxt < lines.length && !lines[nxt].replace(/--.*$/, "").trim()) nxt++;
            if (nxt < lines.length && lines[nxt].replace(/--.*$/, "").trim().startsWith(")")) {
                issues.push({
                    severity: "error",
                    line: li + 1,
                    message: isEn
                        ? "Trailing comma ',' before closing ')' will cause a syntax error."
                        : "Coma ',' sobrante antes del cierre ')' provocará un error de sintaxis.",
                });
            }
        }
    }

    // 3. Sentencias raíz consecutivas sin punto y coma ';'
    const rootVerbRe = /^(CREATE|USE|SELECT|INSERT|UPDATE|DELETE|ALTER|DROP|SHOW|PRAGMA)\b/i;
    let prevCodeLineIdx = -1;
    let depth = 0;
    for (let li = 0; li < lines.length; li++) {
        const clean = lines[li].replace(/--.*$/, "").trim();
        if (!clean) continue;
        if (depth === 0 && prevCodeLineIdx >= 0 && rootVerbRe.test(clean)) {
            const prevClean = lines[prevCodeLineIdx].replace(/--.*$/, "").trim();
            if (
                prevClean &&
                !prevClean.endsWith(";") &&
                !/^(UNION|INTERSECT|EXCEPT|GO)$/i.test(prevClean) &&
                !/^SELECT\b/i.test(clean) // permitir INSERT INTO ... SELECT
            ) {
                issues.push({
                    severity: "warning",
                    line: prevCodeLineIdx + 1,
                    message: isEn
                        ? "Missing semicolon ';' at the end of this statement before the next command."
                        : "Falta punto y coma ';' al final de esta sentencia antes del siguiente comando.",
                });
            }
        }
        depth += (clean.match(/\(/g) || []).length - (clean.match(/\)/g) || []).length;
        if (depth < 0) depth = 0;
        prevCodeLineIdx = li;
    }

    // 4. Detectar tablas declaradas en el script + tablas conocidas en el contrato
    const knownTables = new Set(
        ((contract && contract.tables) || []).map((t) => String(t.name || "").toLowerCase())
    );
    const createdInScript = new Set();
    for (const m of text.matchAll(/CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`"'\[]?([A-Za-z_][A-Za-z0-9_]*)[`"'\]]?/gi)) {
        createdInScript.add(m[1].toLowerCase());
    }

    // Comprobar tablas referenciadas en FROM / JOIN / UPDATE / DELETE FROM
    const refPatterns = [
        /\bFROM\s+[`"'\[]?([A-Za-z_][A-Za-z0-9_]*)[`"'\]]?/gi,
        /\bJOIN\s+[`"'\[]?([A-Za-z_][A-Za-z0-9_]*)[`"'\]]?/gi,
        /\bUPDATE\s+[`"'\[]?([A-Za-z_][A-Za-z0-9_]*)[`"'\]]?/gi,
    ];
    const seenMissing = new Set();
    for (let li = 0; li < lines.length; li++) {
        const clean = lines[li].replace(/--.*$/, "");
        for (const pat of refPatterns) {
            pat.lastIndex = 0;
            let m;
            while ((m = pat.exec(clean)) !== null) {
                const tbl = m[1];
                const low = tbl.toLowerCase();
                if (
                    low === "sqlite_master" ||
                    knownTables.has(low) ||
                    createdInScript.has(low) ||
                    seenMissing.has(low)
                ) {
                    continue;
                }
                seenMissing.add(low);
                issues.push({
                    severity: "warning",
                    line: li + 1,
                    message: isEn
                        ? `Table '${tbl}' is not in the current schema yet.`
                        : `La tabla '${tbl}' aún no existe en el esquema activo.`,
                });
            }
        }
    }

    const stmtCount = text
        .split(";")
        .map((s) => s.replace(/--.*?$/gm, "").trim())
        .filter(Boolean).length;

    return {
        statementCount: stmtCount,
        lineCount: lines.length,
        createdTables: Array.from(createdInScript),
        issues,
    };
}

/**
 * Renderiza el Pre-Análisis SQL en vivo dentro del Inspector (sin reemplazar errores críticos si se acaba de fallar una ejecución).
 */
export function renderLiveSQLInspector(container, sqlText, contract, callbacks) {
    if (!container) return;
    const lang = callbacks.lang || "es";
    const isEn = lang === "en";
    const report = analyzeSQLScriptLive(sqlText, contract, lang);

    const errCount = report.issues.filter((i) => i.severity === "error").length;
    const warnCount = report.issues.filter((i) => i.severity === "warning").length;

    const statusBadge =
        errCount > 0
            ? `<span class="inspector-error-badge">${errCount} ${isEn ? "syntax error(s)" : "error(es)"}</span>`
            : warnCount > 0
            ? `<span class="tab-badge-amber">${warnCount} ${isEn ? "warning(s)" : "aviso(s)"}</span>`
            : `<span class="inspector-rollback-pill">${isEn ? "Syntax OK" : "Sintaxis limpia"}</span>`;

    const issuesHtml =
        report.issues.length === 0
            ? `<p class="sidebar-helper-text">${
                  isEn
                      ? "No syntax issues detected in the current script. Press Ctrl+Enter to execute (or highlight a statement to run only the selection)."
                      : "No se detectan errores de sintaxis en el script actual. Pulsa Ctrl+Enter para ejecutar (o sombrea una sentencia para ejecutar solo esa selección)."
              }</p>`
            : report.issues
                  .map(
                      (iss) => `
                  <div class="inspector-issue-row ${iss.severity === "error" ? "is-error" : "is-warn"}">
                      <div class="inspector-issue-text">${escapeHtml(iss.message)}</div>
                      <button type="button" class="btn-xs" data-jump-line="${iss.line}">
                          ${isEn ? "Line" : "Línea"} ${iss.line} &rarr;
                      </button>
                  </div>
              `
                  )
                  .join("");

    container.innerHTML = `
        <div class="inspector-card">
            <div class="audit-card-header">
                <h3 class="sidebar-heading">${isEn ? "Live SQL Pre-Check" : "Pre-Análisis SQL en Vivo"}</h3>
                ${statusBadge}
            </div>
            <div class="inspector-kpi-strip">
                <div class="inspector-kpi"><strong>${report.statementCount}</strong><span>${isEn ? "Statements" : "Sentencias"}</span></div>
                <div class="inspector-kpi"><strong>${report.lineCount}</strong><span>${isEn ? "Lines" : "Líneas"}</span></div>
                <div class="inspector-kpi"><strong>${(contract && contract.tables ? contract.tables.length : 0)}</strong><span>${isEn ? "Tables" : "Tablas"}</span></div>
            </div>
            <div class="inspector-issues-list">${issuesHtml}</div>
            <button type="button" id="btn-inspector-show-project" class="btn btn-secondary btn-sm">
                ${isEn ? "View Project & Schema Properties" : "Ver Propiedades del Proyecto"}
            </button>
        </div>
    `;

    container.querySelectorAll("[data-jump-line]").forEach((btn) => {
        btn.addEventListener("click", () => {
            const line = Number(btn.getAttribute("data-jump-line"));
            if (callbacks.onJumpToLine) callbacks.onJumpToLine(line);
        });
    });

    const btnProj = document.getElementById("btn-inspector-show-project");
    if (btnProj && callbacks.onSelectElement) {
        btnProj.addEventListener("click", () => callbacks.onSelectElement(null));
    }
}

/**
 * Renderiza el Inspector principal según el elemento seleccionado (Proyecto, Tabla, Columna o Relación).
 */
export function renderProfessionalInspector(container, state, callbacks) {
    if (!container || !state.contract) return;
    const lang = state.lang || "es";
    const isEn = lang === "en";
    const contract = state.contract;
    const sel = state.selectedElement;

    // 1. INSPECTOR DE PROYECTO / ESQUEMA GLOBAL (cuando no hay selección específica)
    if (!sel) {
        const tables = contract.tables || [];
        const rels = contract.relations || [];
        const totalIndexes = tables.reduce((acc, t) => acc + ((t.indexes || []).length), 0);
        const alertsCount = (contract.audit_alerts || []).length;
        const currentColl = contract.collation || "";

        container.innerHTML = `
            <div class="inspector-card">
                <div class="audit-card-header">
                    <h3 class="sidebar-heading">${isEn ? "Database Properties" : "Propiedades del Proyecto"}</h3>
                    <span class="count-chip">v${contract.version || 1}</span>
                </div>
                <div class="inspector-kpi-strip">
                    <div class="inspector-kpi"><strong>${tables.length}</strong><span>${isEn ? "Tables" : "Tablas"}</span></div>
                    <div class="inspector-kpi"><strong>${rels.length}</strong><span>${isEn ? "Rel." : "Rel."}</span></div>
                    <div class="inspector-kpi"><strong>${totalIndexes}</strong><span>${isEn ? "Indexes" : "Índices"}</span></div>
                    <div class="inspector-kpi"><strong>${alertsCount}</strong><span>${isEn ? "Alerts" : "Alertas"}</span></div>
                </div>
                <div class="form-row">
                    <label for="insp-proj-dbname">${isEn ? "Database identifier (.db)" : "Identificador de archivo (.db)"}</label>
                    <input id="insp-proj-dbname" type="text" class="control-input-sm" value="${escapeHtml(contract.db_name)}" readonly>
                </div>
                <div class="form-row">
                    <label for="insp-proj-title">${isEn ? "Project Title" : "Título del Proyecto"}</label>
                    <input id="insp-proj-title" type="text" class="control-input-sm" value="${escapeHtml(contract.title || "")}">
                </div>
                <div class="form-row">
                    <label for="insp-proj-collation">${isEn ? "Collation (COLLATE)" : "Cotejamiento (COLLATE)"}</label>
                    <select id="insp-proj-collation" class="control-select-sm">
                        ${COLLATIONS.map(
                            (c) =>
                                `<option value="${escapeHtml(c.value)}" ${
                                    currentColl === c.value ? "selected" : ""
                                }>${escapeHtml(isEn ? c.labelEn : c.labelEs)}</option>`
                        ).join("")}
                    </select>
                </div>
                <button type="button" class="btn btn-primary btn-sm" id="btn-save-proj-props">
                    ${isEn ? "Save Project Properties" : "Guardar Propiedades del Proyecto"}
                </button>
            </div>

            <div class="inspector-card">
                <h3 class="sidebar-heading">${isEn ? "Tables in Schema" : "Tablas del Esquema"}</h3>
                ${
                    tables.length === 0
                        ? `<p class="sidebar-helper-text">${isEn ? "No tables yet. Create one in ER Canvas or SQL Editor." : "Aún no hay tablas. Crea una en el Lienzo ER o en el Editor SQL."}</p>`
                        : `<div class="inspector-quick-list">
                              ${tables
                                  .map(
                                      (tbl) => `
                                  <button type="button" class="inspector-quick-row" data-insp-pick-tbl="${escapeHtml(tbl.name)}">
                                      <span class="inspector-quick-name">${escapeHtml(tbl.name)}</span>
                                      <span class="count-chip">${(tbl.columns || []).length} cols</span>
                                  </button>
                              `
                                  )
                                  .join("")}
                          </div>`
                }
            </div>
        `;

        document.getElementById("btn-save-proj-props")?.addEventListener("click", () => {
            const newTitle = document.getElementById("insp-proj-title").value.trim();
            const newColl = document.getElementById("insp-proj-collation").value;
            if (newTitle) contract.title = newTitle;
            contract.collation = newColl || null;
            callbacks.onSchemaMutated(contract, true);
            showToast(isEn ? "Project properties updated." : "Propiedades del proyecto actualizadas.");
        });

        container.querySelectorAll("[data-insp-pick-tbl]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const tName = btn.getAttribute("data-insp-pick-tbl");
                const tbl = tables.find((t) => t.name === tName);
                if (tbl) callbacks.onSelectElement({ type: "table", table: tbl.name, data: tbl });
            });
        });
        return;
    }

    // 2. INSPECTOR DE TABLA ENRIQUECIDO
    if (sel.type === "table") {
        const tbl = (contract.tables || []).find((t) => t.name === sel.table);
        if (!tbl) {
            callbacks.onSelectElement(null);
            return;
        }
        const pkCols = tbl.primary_key && tbl.primary_key.length
            ? tbl.primary_key
            : (tbl.columns || []).filter((c) => c.is_pk).map((c) => c.name);
        const outRels = (contract.relations || []).filter((r) => r.source_table === tbl.name);
        const inRels = (contract.relations || []).filter((r) => r.target_table === tbl.name);

        container.innerHTML = `
            <div class="inspector-card">
                <div class="audit-card-header">
                    <h3 class="sidebar-heading">${isEn ? "Table:" : "Tabla:"} ${escapeHtml(tbl.name)}</h3>
                    <div style="display:flex; gap:4px;">
                        <button type="button" class="btn-xs" id="btn-insp-back-proj" title="${isEn ? "Project properties" : "Ver proyecto"}">${isEn ? "Project" : "Proyecto"}</button>
                        <button type="button" class="btn-xs" id="btn-delete-table" style="color:var(--accent-crimson);">${isEn ? "Delete" : "Eliminar"}</button>
                    </div>
                </div>
                <div class="inspector-kpi-strip">
                    <div class="inspector-kpi"><strong>${(tbl.columns || []).length}</strong><span>Cols</span></div>
                    <div class="inspector-kpi"><strong>${pkCols.length}</strong><span>PK</span></div>
                    <div class="inspector-kpi"><strong>${outRels.length}/${inRels.length}</strong><span>FK</span></div>
                    <div class="inspector-kpi"><strong>${(tbl.indexes || []).length}</strong><span>Idx</span></div>
                </div>
                <div style="display:flex; gap:6px; flex-wrap:wrap;">
                    <button type="button" class="btn-tool" id="btn-insp-open-data" style="flex:1;">${isEn ? "View Data" : "Ver Datos"}</button>
                    <button type="button" class="btn-tool" id="btn-insp-copy-tbl-ddl" style="flex:1;">${isEn ? "Copy CREATE TABLE" : "Copiar CREATE TABLE"}</button>
                </div>
                <div class="form-row">
                    <label for="insp-table-name">${isEn ? "Table name" : "Nombre de la tabla"}</label>
                    <input id="insp-table-name" type="text" class="control-input-sm" value="${escapeHtml(tbl.name)}">
                </div>
                <div class="form-row">
                    <label for="insp-table-desc">${isEn ? "Description" : "Descripción funcional"}</label>
                    <input id="insp-table-desc" type="text" class="control-input-sm" value="${escapeHtml(tbl.description || "")}">
                </div>
                <button type="button" class="btn btn-secondary btn-sm" id="btn-save-table-meta">${isEn ? "Update Table" : "Actualizar Tabla"}</button>
            </div>

            <div class="inspector-card">
                <h3 class="sidebar-heading">${isEn ? "Columns (click to edit)" : "Columnas (clic para editar)"}</h3>
                <div class="inspector-quick-list">
                    ${(tbl.columns || [])
                        .map((c) => {
                            const typeStr = c.length ? `${c.data_type}(${c.length})` : c.data_type;
                            const badges = [
                                c.is_pk ? '<i class="badge-pk">PK</i>' : "",
                                c.is_fk ? '<i class="badge-fk">FK</i>' : "",
                                c.is_unique && !c.is_pk ? '<i class="badge-uq">UQ</i>' : "",
                                c.computed_expression ? '<i class="badge-nm">fx</i>' : "",
                            ].join(" ");
                            return `
                                <button type="button" class="inspector-quick-row" data-insp-pick-col="${escapeHtml(c.name)}">
                                    <span class="inspector-quick-name">${badges} ${escapeHtml(c.name)}</span>
                                    <span class="inspector-quick-type">${escapeHtml(typeStr)}</span>
                                </button>
                            `;
                        })
                        .join("")}
                </div>
            </div>

            <div class="inspector-card">
                <h3 class="sidebar-heading">${isEn ? "Add Column to" : "Añadir Columna a"} '${escapeHtml(tbl.name)}'</h3>
                <div class="form-row">
                    <label for="new-col-name">${isEn ? "Column name" : "Nombre de columna"}</label>
                    <input id="new-col-name" type="text" class="control-input-sm" placeholder="${isEn ? "e.g. phone, discount, price" : "ej. telefono, descuento, precio"}">
                </div>
                <div class="form-row">
                    <label for="new-col-type">${isEn ? "SQL Data Type" : "Tipo de dato SQL"}</label>
                    <select id="new-col-type" class="control-select-sm">
                        ${SQL_COLUMN_TYPES.map((tp) => `<option value="${tp}">${tp}</option>`).join("")}
                    </select>
                </div>
                <button type="button" class="btn btn-primary btn-sm" id="btn-add-column-submit">${isEn ? "+ Add Column & Audit" : "+ Añadir Columna y Auditar"}</button>
            </div>
        `;

        document.getElementById("btn-insp-back-proj")?.addEventListener("click", () => {
            callbacks.onSelectElement(null);
        });
        document.getElementById("btn-delete-table")?.addEventListener("click", () => {
            callbacks.onDeleteTable(tbl.name);
        });
        document.getElementById("btn-insp-open-data")?.addEventListener("click", () => {
            callbacks.onOpenTableInExplorer(tbl.name);
        });
        document.getElementById("btn-insp-copy-tbl-ddl")?.addEventListener("click", () => {
            const fullDdl = (state.ddlPreviews && state.ddlPreviews[state.activeDialect]) || "";
            const regex = new RegExp(`CREATE\\s+TABLE[^;]*\\b${tbl.name}\\b[\\s\\S]*?;`, "i");
            const match = fullDdl.match(regex);
            const snippet = match ? match[0] : fullDdl;
            navigator.clipboard.writeText(snippet).then(() => {
                showToast(isEn ? `CREATE TABLE '${tbl.name}' copied.` : `CREATE TABLE de '${tbl.name}' copiado.`);
            });
        });

        container.querySelectorAll("[data-insp-pick-col]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const cName = btn.getAttribute("data-insp-pick-col");
                const cObj = (tbl.columns || []).find((c) => c.name === cName);
                if (cObj) {
                    callbacks.onSelectElement({ type: "column", table: tbl.name, column: cObj.name, data: cObj });
                }
            });
        });

        document.getElementById("btn-save-table-meta")?.addEventListener("click", () => {
            const newName = document.getElementById("insp-table-name").value.trim().replace(/\s+/g, "_");
            const newDesc = document.getElementById("insp-table-desc").value.trim();
            if (newName && newName !== tbl.name) {
                if ((contract.tables || []).some((t) => t !== tbl && t.name === newName)) {
                    showToast(isEn ? `Table '${newName}' already exists.` : `Ya existe una tabla llamada '${newName}'.`);
                    return;
                }
                const oldName = tbl.name;
                tbl.name = newName;
                (contract.relations || []).forEach((r) => {
                    if (r.source_table === oldName) r.source_table = newName;
                    if (r.target_table === oldName) r.target_table = newName;
                });
                (contract.tables || []).forEach((t) => {
                    (t.columns || []).forEach((c) => {
                        if (c.fk_target_table === oldName) c.fk_target_table = newName;
                    });
                });
                if (state.selectedElement && state.selectedElement.table === oldName) {
                    state.selectedElement.table = newName;
                }
                if (state.explorer && state.explorer.activeTable === oldName) {
                    state.explorer.activeTable = newName;
                }
            }
            tbl.description = newDesc;
            callbacks.onSchemaMutated(contract, true);
        });

        document.getElementById("btn-add-column-submit")?.addEventListener("click", () => {
            const cName = document.getElementById("new-col-name").value.trim().toLowerCase().replace(/\s+/g, "_");
            const cType = document.getElementById("new-col-type").value;
            if (!cName) {
                showToast(isEn ? "Enter a column name." : "Escribe un nombre para la columna.");
                return;
            }
            if ((tbl.columns || []).some((c) => c.name === cName)) {
                showToast(isEn ? `Column '${cName}' already exists.` : `La columna '${cName}' ya existe en '${tbl.name}'.`);
                return;
            }
            tbl.columns.push({
                name: cName,
                data_type: cType,
                length: cType === "VARCHAR" ? 150 : cType === "CHAR" ? 10 : null,
                nullable: true,
                default_value: null,
                is_pk: false,
                is_fk: false,
                is_unique: false,
                auto_increment: false,
                check_constraint: null,
                computed_expression: null,
                description: `Columna añadida en ${tbl.name}`,
                tutor_explanation: `Atributo '${cName}' con tipo ${cType}.`,
            });
            callbacks.onSchemaMutated(contract, true);
        });
        return;
    }

    // 3. INSPECTOR DE COLUMNA COMPLETO (100% FIEL A SQL)
    if (sel.type === "column") {
        const tbl = (contract.tables || []).find((t) => t.name === sel.table);
        const col = tbl ? (tbl.columns || []).find((c) => c.name === sel.column) : null;
        if (!tbl || !col) {
            callbacks.onSelectElement(null);
            return;
        }
        const curTypeUpper = String(col.data_type || "VARCHAR").toUpperCase();
        const typeOptions = SQL_COLUMN_TYPES.includes(curTypeUpper)
            ? SQL_COLUMN_TYPES
            : [curTypeUpper, ...SQL_COLUMN_TYPES];
        const isIndexed = (tbl.indexes || []).includes(col.name);

        container.innerHTML = `
            <div class="inspector-card">
                <div class="audit-card-header">
                    <h3 class="sidebar-heading">${escapeHtml(tbl.name)}.${escapeHtml(col.name)}</h3>
                    <div style="display:flex; gap:4px;">
                        <button type="button" class="btn-xs" id="btn-back-to-tbl">&larr; ${escapeHtml(tbl.name)}</button>
                        <button type="button" class="btn-xs" id="btn-delete-col" style="color:var(--accent-crimson);">${isEn ? "Delete" : "Borrar"}</button>
                    </div>
                </div>
                <div class="form-row">
                    <label for="edit-col-name">${isEn ? "Column Name" : "Nombre"}</label>
                    <input id="edit-col-name" type="text" class="control-input-sm" value="${escapeHtml(col.name)}">
                </div>
                <div class="inline-pair">
                    <div class="form-row">
                        <label for="edit-col-type">${isEn ? "SQL Type" : "Tipo SQL"}</label>
                        <select id="edit-col-type" class="control-select-sm">
                            ${typeOptions
                                .map(
                                    (tp) =>
                                        `<option value="${escapeHtml(tp)}" ${
                                            curTypeUpper === tp ? "selected" : ""
                                        }>${escapeHtml(tp)}</option>`
                                )
                                .join("")}
                        </select>
                    </div>
                    <div class="form-row" style="max-width:92px;">
                        <label for="edit-col-len">${isEn ? "Length" : "Longitud"}</label>
                        <input id="edit-col-len" type="number" min="1" max="4000" class="control-input-sm" value="${
                            col.length || ""
                        }" placeholder="ej. 40">
                    </div>
                </div>
                <div class="form-row">
                    <label for="edit-col-default">${isEn ? "Default value (DEFAULT)" : "Valor por defecto (DEFAULT)"}</label>
                    <input id="edit-col-default" type="text" class="control-input-sm" value="${escapeHtml(
                        col.default_value ?? ""
                    )}" placeholder="ej. 'S', 30, 1, CURRENT_TIMESTAMP">
                </div>
                <div class="form-row">
                    <label for="edit-col-check">${isEn ? "Validation rule (CHECK)" : "Restricción de validación (CHECK)"}</label>
                    <input id="edit-col-check" type="text" class="control-input-sm" value="${escapeHtml(
                        col.check_constraint || ""
                    )}" placeholder="ej. precio_hora > 0">
                </div>
                <div class="form-row">
                    <label for="edit-col-computed">${isEn ? "Computed expression (GENERATED ALWAYS AS)" : "Columna calculada (GENERATED ALWAYS AS)"}</label>
                    <input id="edit-col-computed" type="text" class="control-input-sm" value="${escapeHtml(
                        col.computed_expression || ""
                    )}" placeholder="ej. largo * ancho">
                </div>
                <div class="inspector-check-grid">
                    <label><input id="edit-col-pk" type="checkbox" ${col.is_pk ? "checked" : ""}> PRIMARY KEY (PK)</label>
                    <label><input id="edit-col-unique" type="checkbox" ${col.is_unique ? "checked" : ""}> UNIQUE (UQ)</label>
                    <label><input id="edit-col-nullable" type="checkbox" ${col.nullable ? "checked" : ""}> ${isEn ? "Allow NULL" : "Permitir NULL"}</label>
                    <label><input id="edit-col-index" type="checkbox" ${isIndexed ? "checked" : ""}> ${isEn ? "Search Index (INDEX)" : "Índice (INDEX)"}</label>
                </div>
                <button type="button" class="btn btn-primary btn-sm" id="btn-save-col-changes">
                    ${isEn ? "Apply Column Changes" : "Aplicar Cambios a Columna"}
                </button>
            </div>
        `;

        document.getElementById("btn-back-to-tbl")?.addEventListener("click", () => {
            callbacks.onSelectElement({ type: "table", table: tbl.name, data: tbl });
        });

        document.getElementById("btn-save-col-changes")?.addEventListener("click", () => {
            const oldCol = col.name;
            const newCol =
                document.getElementById("edit-col-name").value.trim().replace(/\s+/g, "_") || oldCol;
            if (newCol !== oldCol) {
                if ((tbl.columns || []).some((c) => c !== col && c.name === newCol)) {
                    showToast(isEn ? `Column '${newCol}' already exists.` : `La columna '${newCol}' ya existe en '${tbl.name}'.`);
                    return;
                }
                col.name = newCol;
                if (Array.isArray(tbl.primary_key)) {
                    tbl.primary_key = tbl.primary_key.map((p) => (p === oldCol ? newCol : p));
                }
                if (Array.isArray(tbl.indexes)) {
                    tbl.indexes = tbl.indexes.map((ix) => (ix === oldCol ? newCol : ix));
                }
                (contract.relations || []).forEach((r) => {
                    if (r.source_table === tbl.name && r.source_column === oldCol) r.source_column = newCol;
                    if (r.target_table === tbl.name && r.target_column === oldCol) r.target_column = newCol;
                });
                (contract.tables || []).forEach((t) => {
                    (t.columns || []).forEach((c) => {
                        if (c.fk_target_table === tbl.name && c.fk_target_column === oldCol) {
                            c.fk_target_column = newCol;
                        }
                    });
                });
                if (state.selectedElement && state.selectedElement.type === "column") {
                    state.selectedElement.column = newCol;
                }
            }

            const newType = document.getElementById("edit-col-type").value;
            const rawLen = document.getElementById("edit-col-len").value.trim();
            const parsedLen = rawLen ? Math.max(1, parseInt(rawLen, 10)) : null;
            col.data_type = newType;
            col.length = newType === "VARCHAR" || newType === "CHAR" ? parsedLen || (newType === "CHAR" ? 10 : 150) : null;

            const defVal = document.getElementById("edit-col-default").value.trim();
            col.default_value = defVal !== "" ? defVal : null;

            const chkVal = document.getElementById("edit-col-check").value.trim();
            col.check_constraint = chkVal !== "" ? chkVal : null;

            const compVal = document.getElementById("edit-col-computed").value.trim();
            col.computed_expression = compVal !== "" ? compVal : null;

            col.is_pk = document.getElementById("edit-col-pk").checked;
            col.is_unique = document.getElementById("edit-col-unique").checked;
            col.nullable = col.is_pk ? false : document.getElementById("edit-col-nullable").checked;

            // Sincronizar primary_key de la tabla (soporta PK compuestas)
            tbl.primary_key = (tbl.columns || []).filter((c) => c.is_pk).map((c) => c.name);

            // Sincronizar índices de la tabla
            const wantIndex = document.getElementById("edit-col-index").checked;
            tbl.indexes = Array.isArray(tbl.indexes) ? tbl.indexes : [];
            if (wantIndex && !tbl.indexes.includes(col.name)) {
                tbl.indexes.push(col.name);
            } else if (!wantIndex) {
                tbl.indexes = tbl.indexes.filter((ix) => ix !== col.name);
            }

            callbacks.onSchemaMutated(contract, true);
            showToast(isEn ? `Column '${tbl.name}.${col.name}' updated.` : `Columna '${tbl.name}.${col.name}' actualizada.`);
        });

        document.getElementById("btn-delete-col")?.addEventListener("click", () => {
            tbl.columns = (tbl.columns || []).filter((c) => c.name !== col.name);
            tbl.primary_key = (tbl.columns || []).filter((c) => c.is_pk).map((c) => c.name);
            tbl.indexes = (tbl.indexes || []).filter((ix) => ix !== col.name);
            callbacks.onSelectElement({ type: "table", table: tbl.name, data: tbl });
            callbacks.onSchemaMutated(contract, true);
        });
        return;
    }

    // 4. INSPECTOR DE RELACIÓN
    if (sel.type === "relation") {
        const rel = (contract.relations || []).find((r) => r.id === sel.relation);
        if (!rel) {
            callbacks.onSelectElement(null);
            return;
        }
        container.innerHTML = `
            <div class="inspector-card">
                <div class="audit-card-header">
                    <h3 class="sidebar-heading">${isEn ? "Relation:" : "Relación:"} ${escapeHtml(rel.source_table)} &rarr; ${escapeHtml(rel.target_table)}</h3>
                    <button type="button" class="btn-xs" id="btn-delete-rel" style="color:var(--accent-crimson);">${isEn ? "Delete" : "Eliminar"}</button>
                </div>
                <p class="sidebar-helper-text">
                    <code>${escapeHtml(rel.source_table)}.${escapeHtml(rel.source_column)}</code> &rarr;
                    <code>${escapeHtml(rel.target_table)}.${escapeHtml(rel.target_column)}</code> (${escapeHtml(rel.cardinality || "1:N")})
                </p>
                <div class="form-row">
                    <label for="edit-rel-ondelete">ON DELETE (${escapeHtml(rel.target_table)})</label>
                    <select id="edit-rel-ondelete" class="control-select-sm">
                        <option value="RESTRICT" ${rel.on_delete === "RESTRICT" ? "selected" : ""}>RESTRICT</option>
                        <option value="CASCADE" ${rel.on_delete === "CASCADE" ? "selected" : ""}>CASCADE</option>
                        <option value="SET NULL" ${rel.on_delete === "SET NULL" ? "selected" : ""}>SET NULL</option>
                    </select>
                </div>
                <div class="form-row">
                    <label for="edit-rel-onupdate">ON UPDATE</label>
                    <select id="edit-rel-onupdate" class="control-select-sm">
                        <option value="CASCADE" ${(rel.on_update || "CASCADE") === "CASCADE" ? "selected" : ""}>CASCADE</option>
                        <option value="RESTRICT" ${rel.on_update === "RESTRICT" ? "selected" : ""}>RESTRICT</option>
                        <option value="NO ACTION" ${rel.on_update === "NO ACTION" ? "selected" : ""}>NO ACTION</option>
                    </select>
                </div>
                <button type="button" class="btn btn-primary btn-sm" id="btn-save-rel-changes">
                    ${isEn ? "Update Policy & Audit" : "Actualizar Política y Auditar"}
                </button>
            </div>
        `;

        document.getElementById("btn-save-rel-changes")?.addEventListener("click", () => {
            rel.on_delete = document.getElementById("edit-rel-ondelete").value;
            rel.on_update = document.getElementById("edit-rel-onupdate").value;
            callbacks.onSchemaMutated(contract, true);
        });

        document.getElementById("btn-delete-rel")?.addEventListener("click", () => {
            contract.relations = (contract.relations || []).filter((r) => r.id !== rel.id);
            const srcTbl = (contract.tables || []).find((t) => t.name === rel.source_table);
            const srcCol = srcTbl ? (srcTbl.columns || []).find((c) => c.name === rel.source_column) : null;
            if (srcCol) {
                srcCol.is_fk = false;
                srcCol.fk_target_table = null;
                srcCol.fk_target_column = null;
            }
            callbacks.onSelectElement(null);
            callbacks.onSchemaMutated(contract, true);
        });
    }
}
