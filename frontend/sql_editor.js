/**
 * Editor de Código SQL Profesional para SGBD-Smart.
 * Incluye numeración de líneas, resaltado de sintaxis SQL en tiempo real,
 * reglas de indentación automática (Tab, Enter, auto-cierre) y autocompletado inteligente
 * basado en palabras clave SQL, tipos de datos, snippets y tablas/columnas del esquema activo.
 */

class SQLCodeEditorController {
    constructor(options = {}) {
        this.textarea = document.getElementById(options.textareaId || "sql-code-textarea");
        this.highlightLayer = document.getElementById(options.highlightId || "sql-highlight-layer");
        this.gutter = document.getElementById(options.gutterId || "sql-line-gutter");
        this.popup = document.getElementById(options.popupId || "sql-autocomplete-popup");

        this.onChange = options.onChange || (() => {});
        this.onExecuteShortcut = options.onExecuteShortcut || (() => {});
        this.onSaveShortcut = options.onSaveShortcut || (() => {});
        this.getSchemaContract = options.getSchemaContract || (() => null);

        this.suggestions = [];
        this.activeIndex = 0;
        this.currentTokenRange = { start: 0, end: 0 };
        this.ghostText = "";
        this.errorLine = null;

        this.SQL_KEYWORDS = [
            "SELECT", "FROM", "WHERE", "INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "JOIN", "ON",
            "GROUP BY", "HAVING", "ORDER BY", "ASC", "DESC", "LIMIT", "OFFSET", "DISTINCT",
            "INSERT INTO", "VALUES", "UPDATE", "SET", "DELETE FROM",
            "CREATE DATABASE", "USE", "CREATE TABLE", "CREATE INDEX", "ALTER TABLE", "ADD COLUMN",
            "DROP TABLE", "DROP DATABASE", "IF NOT EXISTS", "IF EXISTS",
            "CONSTRAINT", "PRIMARY KEY", "FOREIGN KEY", "REFERENCES", "ON DELETE RESTRICT",
            "ON DELETE CASCADE", "ON DELETE SET NULL", "ON UPDATE CASCADE",
            "NOT NULL", "NULL", "UNIQUE", "DEFAULT", "CHECK", "AUTO_INCREMENT", "AUTOINCREMENT",
            "CHARACTER SET utf8mb4", "COLLATE utf8mb4_spanish_ci",
            "SHOW TABLES", "SHOW DATABASES", "DESCRIBE", "EXPLAIN QUERY PLAN",
            "AND", "OR", "NOT", "IN", "LIKE", "BETWEEN", "IS NULL", "IS NOT NULL", "AS",
            "COUNT(*)", "SUM(", "AVG(", "MIN(", "MAX(", "CURRENT_TIMESTAMP", "CURRENT_DATE"
        ];

        this.SQL_TYPES = [
            "INTEGER", "INT", "SMALLINT", "BIGINT", "TINYINT",
            "VARCHAR(50)", "VARCHAR(120)", "VARCHAR(150)", "CHAR(10)", "TEXT",
            "DECIMAL(10,2)", "NUMERIC(10,2)", "FLOAT", "REAL",
            "DATE", "DATETIME", "TIMESTAMP", "BOOLEAN"
        ];

        this.SQL_SNIPPETS = [
            {
                label: "CREATE DATABASE ... CHARACTER SET utf8mb4",
                insert: "CREATE DATABASE MiBaseDatos CHARACTER SET utf8mb4 COLLATE utf8mb4_spanish_ci;\nUSE MiBaseDatos;\n",
                kind: "SNIPPET",
            },
            {
                label: "CREATE TABLE (estructura completa con PK)",
                insert: "CREATE TABLE nombre_tabla (\n    id          INTEGER PRIMARY KEY AUTOINCREMENT,\n    nombre      VARCHAR(100) NOT NULL,\n    fecha_alta  DATE\n);",
                kind: "SNIPPET",
            },
            {
                label: "CONSTRAINT PK_tabla PRIMARY KEY (...)",
                insert: "CONSTRAINT PK_tabla PRIMARY KEY (id)",
                kind: "SNIPPET",
            },
            {
                label: "CONSTRAINT FK_tabla FOREIGN KEY (...) REFERENCES ...",
                insert: "CONSTRAINT FK_tabla FOREIGN KEY (padre_id) REFERENCES tabla_padre(id) ON DELETE RESTRICT",
                kind: "SNIPPET",
            },
            {
                label: "SELECT ... FROM ... WHERE ... ORDER BY ...",
                insert: "SELECT *\nFROM tabla\nWHERE id > 0\nORDER BY id DESC\nLIMIT 25;",
                kind: "SNIPPET",
            },
        ];

        if (this.textarea) {
            this._bindEvents();
            this.refreshHighlight();
        }
    }

    _bindEvents() {
        this.textarea.addEventListener("input", () => {
            this.errorLine = null;
            this.refreshHighlight();
            this._keepActiveLineCentered();
            this.onChange(this.textarea.value);
            this._updateAutocomplete(false);
        });

        this.textarea.addEventListener("scroll", () => {
            this._syncScroll();
        });

        this.textarea.addEventListener("keydown", (e) => this._handleKeyDown(e));

        this.textarea.addEventListener("blur", () => {
            this.ghostText = "";
            this.refreshHighlight();
            setTimeout(() => this.hidePopup(), 160);
        });

        this.textarea.addEventListener("click", () => {
            this.hidePopup();
            this.refreshHighlight();
        });

        this.textarea.addEventListener("keyup", (e) => {
            if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(e.key)) {
                this.refreshHighlight();
                if (["ArrowUp", "ArrowDown"].includes(e.key)) {
                    this._keepActiveLineCentered();
                }
            }
        });
    }

    setValue(text) {
        if (!this.textarea) return;
        this.textarea.value = text || "";
        this.refreshHighlight();
        this.hidePopup();
    }

    getValue() {
        return this.textarea ? this.textarea.value : "";
    }

    getSelectedOrAllText() {
        if (!this.textarea) return { text: "", isSelection: false, startLineOffset: 0 };
        const start = this.textarea.selectionStart;
        const end = this.textarea.selectionEnd;
        const full = this.textarea.value;
        if (end > start) {
            const selected = full.slice(start, end).trim();
            if (selected) {
                const startLineOffset = full.slice(0, start).split("\n").length - 1;
                return { text: selected, isSelection: true, startLineOffset };
            }
        }
        return { text: full.trim(), isSelection: false, startLineOffset: 0 };
    }

    setErrorLine(lineNumber) {
        const n = Number(lineNumber);
        this.errorLine = Number.isFinite(n) && n >= 1 ? Math.round(n) : null;
        this.refreshHighlight();
    }

    clearErrorLine() {
        if (this.errorLine !== null) {
            this.errorLine = null;
            this.refreshHighlight();
        }
    }

    jumpToLine(lineNumber) {
        if (!this.textarea) return;
        const lines = this.textarea.value.split("\n");
        const idx = Math.max(0, Math.min(lines.length - 1, Number(lineNumber || 1) - 1));
        let start = 0;
        for (let i = 0; i < idx; i++) {
            start += lines[i].length + 1;
        }
        const end = start + lines[idx].length;
        this.textarea.focus();
        this.textarea.setSelectionRange(start, end);
        this._keepActiveLineCentered();
        this.refreshHighlight();
    }

    insertTokenAtCursor(token, smartSpacing = true) {
        if (!this.textarea) return;
        const start = this.textarea.selectionStart;
        const end = this.textarea.selectionEnd;
        const val = this.textarea.value;

        let toInsert = token;
        if (smartSpacing) {
            const prevChar = start > 0 ? val.charAt(start - 1) : "";
            const nextChar = end < val.length ? val.charAt(end) : "";
            const needsLeadingSpace = prevChar !== "" && !/[\s(.,(]/.test(prevChar);
            const needsTrailingSpace = nextChar !== "" && !/[\s).,;]/.test(nextChar);
            toInsert = (needsLeadingSpace ? " " : "") + token + (needsTrailingSpace ? " " : "");
        }

        this.textarea.value = val.slice(0, start) + toInsert + val.slice(end);
        const pos = start + toInsert.length;
        this.textarea.setSelectionRange(pos, pos);
        this.textarea.focus();
        this.refreshHighlight();
        this.onChange(this.textarea.value);
    }

    _handleKeyDown(e) {
        // Ctrl+Enter -> Ejecutar SQL
        if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
            e.preventDefault();
            this.hidePopup();
            this.onExecuteShortcut();
            return;
        }
        // Ctrl+S -> Guardar archivo .sql
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
            e.preventDefault();
            this.hidePopup();
            this.onSaveShortcut();
            return;
        }
        // Ctrl+Space -> Forzar menú de autocompletado
        if (e.ctrlKey && e.code === "Space") {
            e.preventDefault();
            this._updateAutocomplete(true);
            return;
        }

        // ArrowRight al final de la línea acepta el autocompletado inline de línea (Ghost Text)
        if (
            e.key === "ArrowRight" &&
            !e.shiftKey &&
            !e.ctrlKey &&
            !e.altKey &&
            this.ghostText &&
            this.textarea.selectionStart === this.textarea.selectionEnd &&
            (this.textarea.selectionStart === this.textarea.value.length ||
                this.textarea.value.charAt(this.textarea.selectionStart) === "\n")
        ) {
            e.preventDefault();
            this._acceptGhostText();
            return;
        }

        // Navegación dentro del menú de autocompletado si está abierto
        if (this.popup && !this.popup.classList.contains("hidden") && this.suggestions.length > 0) {
            if (e.key === "ArrowDown") {
                e.preventDefault();
                this.activeIndex = (this.activeIndex + 1) % this.suggestions.length;
                this._renderPopupItems();
                return;
            }
            if (e.key === "ArrowUp") {
                e.preventDefault();
                this.activeIndex = (this.activeIndex - 1 + this.suggestions.length) % this.suggestions.length;
                this._renderPopupItems();
                return;
            }
            if (e.key === "Tab" || e.key === "Enter") {
                e.preventDefault();
                this._applySuggestion(this.suggestions[this.activeIndex]);
                return;
            }
            if (e.key === "Escape") {
                e.preventDefault();
                this.ghostText = "";
                this.hidePopup();
                this.refreshHighlight();
                return;
            }
        }

        if (e.key === "Escape" && this.ghostText) {
            e.preventDefault();
            this.ghostText = "";
            this.refreshHighlight();
            return;
        }

        // Tab acepta el autocompletado inline de línea si existe; si no, inserta 4 espacios
        if (e.key === "Tab") {
            e.preventDefault();
            if (this.ghostText) {
                this._acceptGhostText();
            } else {
                this.insertTokenAtCursor("    ", false);
            }
            return;
        }

        // Regla de escritura: Enter mantiene indentación actual (y añade 4 espacios tras '(')
        if (e.key === "Enter") {
            const start = this.textarea.selectionStart;
            const end = this.textarea.selectionEnd;
            const val = this.textarea.value;
            const lineStart = val.lastIndexOf("\n", start - 1) + 1;
            const currentLine = val.slice(lineStart, start);
            const indentMatch = currentLine.match(/^(\s*)/);
            let indent = indentMatch ? indentMatch[1] : "";
            if (currentLine.trim().endsWith("(")) {
                indent += "    ";
            }
            e.preventDefault();
            const insertText = "\n" + indent;
            this.textarea.value = val.slice(0, start) + insertText + val.slice(end);
            const pos = start + insertText.length;
            this.textarea.setSelectionRange(pos, pos);
            this.refreshHighlight();
            this._keepActiveLineCentered();
            this.onChange(this.textarea.value);
            return;
        }

        // Auto-cierre de paréntesis y comillas simples
        if (e.key === "(" || e.key === "'") {
            const start = this.textarea.selectionStart;
            const end = this.textarea.selectionEnd;
            const val = this.textarea.value;
            const nextChar = val.charAt(end);
            if (start === end && (!nextChar || /[\s;,)]/.test(nextChar))) {
                e.preventDefault();
                const pair = e.key === "(" ? "()" : "''";
                this.textarea.value = val.slice(0, start) + pair + val.slice(end);
                this.textarea.setSelectionRange(start + 1, start + 1);
                this.refreshHighlight();
                this.onChange(this.textarea.value);
            }
        }
    }

    _updateAutocomplete(forceOpen) {
        if (!this.textarea || !this.popup) return;
        const pos = this.textarea.selectionStart;
        const textBefore = this.textarea.value.slice(0, pos);

        // Detectar patrón "tabla.prefijo" o palabra simple
        const dotMatch = textBefore.match(/([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]*)$/);
        const wordMatch = textBefore.match(/([a-zA-Z_][a-zA-Z0-9_]*)$/);

        const candidates = [];
        const contract = this.getSchemaContract();
        const tables = (contract && contract.tables) || [];

        if (dotMatch) {
            const tableOrAlias = dotMatch[1].toLowerCase();
            const colPrefix = dotMatch[2].toLowerCase();
            this.currentTokenRange = { start: pos - dotMatch[2].length, end: pos };

            // Buscar tabla por nombre exacto o por inicial de alias (ej. c. -> clientes)
            const matchedTable =
                tables.find((t) => t.name.toLowerCase() === tableOrAlias) ||
                tables.find((t) => t.name.toLowerCase().startsWith(tableOrAlias));

            if (matchedTable) {
                (matchedTable.columns || []).forEach((col) => {
                    if (!colPrefix || col.name.toLowerCase().startsWith(colPrefix)) {
                        candidates.push({
                            label: col.name,
                            insert: col.name,
                            kind: "COL",
                            detail: `${matchedTable.name} · ${col.data_type}`,
                        });
                    }
                });
            }
        } else if (wordMatch && (wordMatch[1].length >= 2 || forceOpen)) {
            const prefix = wordMatch[1].toUpperCase();
            const prefixLow = wordMatch[1].toLowerCase();
            this.currentTokenRange = { start: pos - wordMatch[1].length, end: pos };

            // 1. Tablas del esquema activo
            tables.forEach((t) => {
                if (t.name.toLowerCase().startsWith(prefixLow)) {
                    candidates.push({
                        label: t.name,
                        insert: t.name,
                        kind: "TABLA",
                        detail: `${(t.columns || []).length} cols`,
                    });
                }
            });

            // 2. Columnas del esquema activo
            const seenCols = new Set();
            tables.forEach((t) => {
                (t.columns || []).forEach((c) => {
                    if (c.name.toLowerCase().startsWith(prefixLow) && !seenCols.has(c.name)) {
                        seenCols.add(c.name);
                        candidates.push({
                            label: c.name,
                            insert: c.name,
                            kind: "COL",
                            detail: `${t.name} (${c.data_type})`,
                        });
                    }
                });
            });

            // 3. Palabras clave SQL
            this.SQL_KEYWORDS.forEach((kw) => {
                if (kw.startsWith(prefix)) {
                    candidates.push({
                        label: kw,
                        insert: kw,
                        kind: "SQL",
                        detail: "Palabra clave",
                    });
                }
            });

            // 4. Tipos de datos SQL
            this.SQL_TYPES.forEach((tp) => {
                if (tp.startsWith(prefix)) {
                    candidates.push({
                        label: tp,
                        insert: tp,
                        kind: "TIPO",
                        detail: "Tipo SQL",
                    });
                }
            });

            // 5. Snippets completos de sentencias
            this.SQL_SNIPPETS.forEach((sn) => {
                if (sn.label.toUpperCase().startsWith(prefix)) {
                    candidates.push({
                        label: sn.label,
                        insert: sn.insert,
                        kind: "SNIPPET",
                        detail: "Plantilla",
                    });
                }
            });
        } else if (forceOpen) {
            this.currentTokenRange = { start: pos, end: pos };
            this.SQL_SNIPPETS.forEach((sn) => candidates.push({ ...sn, detail: "Plantilla" }));
            tables.forEach((t) =>
                candidates.push({ label: t.name, insert: t.name, kind: "TABLA", detail: "Tabla activa" })
            );
        }

        this.suggestions = candidates.slice(0, 10);
        this.activeIndex = 0;

        if (this.suggestions.length === 0) {
            this.hidePopup();
            return;
        }

        this._renderPopupItems();
        this._positionPopup();
        this.popup.classList.remove("hidden");
    }

    _renderPopupItems() {
        if (!this.popup) return;
        this.popup.innerHTML = this.suggestions
            .map(
                (item, idx) => `
                <div class="ac-item ${idx === this.activeIndex ? "active" : ""}" data-ac-idx="${idx}">
                    <span class="ac-kind ac-kind-${item.kind.toLowerCase()}">${item.kind}</span>
                    <span class="ac-label">${this._escape(item.label)}</span>
                    <span class="ac-detail">${this._escape(item.detail || "")}</span>
                </div>
            `
            )
            .join("");

        this.popup.querySelectorAll("[data-ac-idx]").forEach((row) => {
            row.addEventListener("mousedown", (e) => {
                e.preventDefault();
                const idx = Number(row.getAttribute("data-ac-idx"));
                if (this.suggestions[idx]) {
                    this._applySuggestion(this.suggestions[idx]);
                }
            });
        });
    }

    _positionPopup() {
        if (!this.popup || !this.textarea) return;
        const pos = this.textarea.selectionStart;
        const lines = this.textarea.value.slice(0, pos).split("\n");
        const lineNum = lines.length;
        const colNum = lines[lines.length - 1].length;
        const lineHeight = 20;
        const rect = this.textarea.getBoundingClientRect();

        // Coordenadas reales en el viewport (position: fixed evita cualquier recorte por overflow: hidden)
        const caretTop = rect.top + 10 + (lineNum - 1) * lineHeight - this.textarea.scrollTop;
        const caretBottom = caretTop + lineHeight;
        const caretLeft = rect.left + 14 + colNum * 7.8 - this.textarea.scrollLeft;

        const popupEstHeight = Math.min(230, Math.max(44, this.suggestions.length * 30 + 12));
        const spaceBelow = window.innerHeight - caretBottom - 16;
        let topPx = caretBottom + 4;
        if (spaceBelow < popupEstHeight && caretTop - popupEstHeight - 8 > 12) {
            // Voltear automáticamente por encima de la línea del cursor si no cabe abajo
            topPx = caretTop - popupEstHeight - 4;
        } else {
            topPx = Math.min(window.innerHeight - popupEstHeight - 12, Math.max(12, topPx));
        }

        const maxLeft = Math.max(12, window.innerWidth - 360);
        const leftPx = Math.min(maxLeft, Math.max(rect.left + 8, caretLeft));

        this.popup.style.top = `${Math.round(topPx)}px`;
        this.popup.style.left = `${Math.round(leftPx)}px`;
    }

    _acceptGhostText() {
        if (!this.textarea || !this.ghostText) return;
        const start = this.textarea.selectionStart;
        const val = this.textarea.value;
        const toInsert = this.ghostText;
        this.ghostText = "";
        this.textarea.value = val.slice(0, start) + toInsert + val.slice(start);
        const newPos = start + toInsert.length;
        this.textarea.setSelectionRange(newPos, newPos);
        this.textarea.focus();
        this.hidePopup();
        this.refreshHighlight();
        this.onChange(this.textarea.value);
    }

    _computeLineSuggestion() {
        if (!this.textarea || document.activeElement !== this.textarea) return "";
        const pos = this.textarea.selectionStart;
        if (pos !== this.textarea.selectionEnd) return "";
        const val = this.textarea.value;
        const nextChar = val.charAt(pos);
        // Solo sugerir completado de línea cuando el cursor está al final de la línea actual
        if (nextChar !== "" && nextChar !== "\n") return "";

        const lineStart = val.lastIndexOf("\n", pos - 1) + 1;
        const lineBefore = val.slice(lineStart, pos);
        const trimmed = lineBefore.trim();
        if (trimmed.length < 2 || trimmed.startsWith("--")) return "";

        const contract = this.getSchemaContract();
        const tables = (contract && contract.tables) || [];
        const relations = (contract && contract.relations) || [];
        const firstTbl = tables[0] ? tables[0].name : "nombre_tabla";
        const firstPk =
            tables[0] && tables[0].columns
                ? (tables[0].columns.find((c) => c.is_pk) || tables[0].columns[0] || { name: "id" }).name
                : "id";

        // Detectar tablas y BD ya escritas arriba en el mismo script
        const textBefore = val.slice(0, pos);
        const dbMatch = textBefore.match(/CREATE\s+DATABASE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)/i);
        const scriptDb = dbMatch ? dbMatch[1] : (contract && contract.db_name) || "mi_base_datos";
        const scriptTables = [...textBefore.matchAll(/CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)/gi)].map(
            (m) => m[1]
        );
        const refParentTable = scriptTables[scriptTables.length - 2] || scriptTables[0] || firstTbl;

        // Comprobar si estamos dentro de un bloque CREATE TABLE (... abierto
        const lastCreateIdx = textBefore.toUpperCase().lastIndexOf("CREATE TABLE");
        let insideCreateTable = false;
        let currentCreateBlock = "";
        if (lastCreateIdx >= 0) {
            currentCreateBlock = textBefore.slice(lastCreateIdx);
            const opens = (currentCreateBlock.match(/\(/g) || []).length;
            const closes = (currentCreateBlock.match(/\)/g) || []).length;
            insideCreateTable = opens > closes;
        }

        const upperTrim = trimmed.toUpperCase();

        // 1. Sugerencias dentro de CREATE TABLE (...)
        if (insideCreateTable) {
            // Definición de columna con tipo completo seguida de espacio: "cod_pista SMALLINT "
            const colTypeMatch = lineBefore.match(
                /^\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+(?:VARCHAR\s*\(\d+\)|CHAR\s*\(\d+\)|DECIMAL\s*\(\d+\s*,\s*\d+\)|NUMERIC\s*\(\d+\s*,\s*\d+\)|SMALLINT|TINYINT|BIGINT|INTEGER|INT|DATE|TIME|DATETIME|BOOLEAN|TEXT)\s+$/i
            );
            if (colTypeMatch) {
                const colName = colTypeMatch[1].toLowerCase();
                const hasPkAlready = /PRIMARY\s+KEY/i.test(currentCreateBlock);
                if (!hasPkAlready && (colName === "id" || colName.startsWith("cod_") || colName.startsWith("num_") || colName.startsWith("id_"))) {
                    return "NOT NULL PRIMARY KEY,";
                }
                if (/(precio|cuota|importe|salario|total|coste)/i.test(colName)) {
                    return `NOT NULL CHECK (${colName} >= 0),`;
                }
                if (/(dni|email|isbn|matricula)/i.test(colName)) {
                    return "NOT NULL UNIQUE,";
                }
                return "NOT NULL,";
            }
            if (/^FOREIGN\s*K?E?Y?$/i.test(upperTrim)) {
                const suffix = "FOREIGN KEY".slice(upperTrim.length);
                return `${suffix} (col_id) REFERENCES ${refParentTable}(id) ON DELETE RESTRICT`;
            }
            if (/^PRIMARY\s*K?E?Y?$/i.test(upperTrim)) {
                const suffix = "PRIMARY KEY".slice(upperTrim.length);
                return `${suffix} (col1, col2)`;
            }
            if (/^CONSTRAINT\s+FK_?$/i.test(upperTrim)) {
                return `tabla_col FOREIGN KEY (col_id) REFERENCES ${refParentTable}(id) ON DELETE RESTRICT`;
            }
            return "";
        }

        // 2. Sugerencias de sentencias DDL / DML a nivel raíz
        const prefixRules = [
            {
                match: /^CREATE\s+DATAB?A?S?E?$/i,
                complete: (m) => "CREATE DATABASE".slice(m.length) + ` ${scriptDb} COLLATE utf8mb4_spanish_ci;`,
            },
            {
                match: /^CREATE\s+TABL?E?$/i,
                complete: (m) => "CREATE TABLE".slice(m.length) + " nombre_tabla (\n    id INT NOT NULL PRIMARY KEY,\n    nombre VARCHAR(50) NOT NULL\n);",
            },
            {
                match: /^CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)$/i,
                complete: () => " (\n    id INT NOT NULL PRIMARY KEY,\n    nombre VARCHAR(50) NOT NULL\n);",
            },
            {
                match: /^CREATE\s+INDE?X?$/i,
                complete: (m) => "CREATE INDEX".slice(m.length) + ` idx_${firstTbl}_${firstPk} ON ${firstTbl} (${firstPk});`,
            },
            {
                match: /^USE$/i,
                complete: () => ` ${scriptDb};`,
            },
            {
                match: /^SELECT\s+\*\s+FR?O?M?$/i,
                complete: (m) => {
                    const tail = m.replace(/^SELECT\s+\*\s+/i, "");
                    return "FROM".slice(tail.length) + ` ${firstTbl}\nLIMIT 25;`;
                },
            },
            {
                match: /^SELECT\s+\*\s+FROM\s+([A-Za-z_][A-Za-z0-9_]*)\s+WH?E?R?E?$/i,
                complete: (m) => {
                    const tblMatch = m.match(/FROM\s+([A-Za-z_][A-Za-z0-9_]*)\s+(WH?E?R?E?)$/i);
                    const tName = tblMatch[1];
                    const tObj = tables.find((t) => t.name.toLowerCase() === tName.toLowerCase());
                    const pk = tObj && tObj.columns ? (tObj.columns.find((c) => c.is_pk) || tObj.columns[0] || { name: "id" }).name : "id";
                    return "WHERE".slice(tblMatch[2].length) + ` ${pk} = 1;`;
                },
            },
            {
                match: /^(INNER|LEFT|RIGHT)\s+JO?I?N?$/i,
                complete: (m) => {
                    const parts = m.split(/\s+/);
                    const rest = "JOIN".slice(parts[1].length);
                    if (relations.length > 0) {
                        const r = relations[0];
                        return `${rest} ${r.target_table} ON ${r.source_table}.${r.source_column} = ${r.target_table}.${r.target_column}`;
                    }
                    return `${rest} tabla_destino ON tabla_a.id = tabla_destino.tabla_a_id`;
                },
            },
            {
                match: /^INSERT\s+IN?T?O?$/i,
                complete: (m) => {
                    const tail = m.replace(/^INSERT\s+/i, "");
                    const cols =
                        tables[0] && tables[0].columns
                            ? tables[0].columns
                                  .filter((c) => !(c.is_pk && c.auto_increment) && !c.computed_expression)
                                  .slice(0, 3)
                                  .map((c) => c.name)
                            : ["nombre"];
                    const vals = cols.map(() => "'valor'").join(", ");
                    return "INTO".slice(tail.length) + ` ${firstTbl} (${cols.join(", ")}) VALUES (${vals});`;
                },
            },
            {
                match: /^UPDATE\s+([A-Za-z_][A-Za-z0-9_]*)\s+SE?T?$/i,
                complete: (m) => {
                    const parts = m.match(/^UPDATE\s+([A-Za-z_][A-Za-z0-9_]*)\s+(SE?T?)$/i);
                    const tName = parts[1];
                    const tObj = tables.find((t) => t.name.toLowerCase() === tName.toLowerCase());
                    const pk = tObj && tObj.columns ? (tObj.columns.find((c) => c.is_pk) || tObj.columns[0] || { name: "id" }).name : "id";
                    const editCol = tObj && tObj.columns ? (tObj.columns.find((c) => !c.is_pk) || { name: "nombre" }).name : "nombre";
                    return "SET".slice(parts[2].length) + ` ${editCol} = 'nuevo_valor' WHERE ${pk} = 1;`;
                },
            },
            {
                match: /^DELETE\s+FR?O?M?$/i,
                complete: (m) => {
                    const tail = m.replace(/^DELETE\s+/i, "");
                    return "FROM".slice(tail.length) + ` ${firstTbl} WHERE ${firstPk} = 1;`;
                },
            },
            {
                match: /^ALTER\s+TABL?E?$/i,
                complete: (m) => "ALTER TABLE".slice(m.length) + ` ${firstTbl} ADD COLUMN nueva_col VARCHAR(100);`,
            },
            {
                match: /^ORDER\s+BY?$/i,
                complete: (m) => "ORDER BY".slice(m.length) + ` ${firstPk} DESC LIMIT 25;`,
            },
            {
                match: /^GROUP\s+BY?$/i,
                complete: (m) => "GROUP BY".slice(m.length) + ` ${firstPk};`,
            },
        ];

        for (const rule of prefixRules) {
            if (rule.match.test(trimmed)) {
                return rule.complete(trimmed);
            }
        }

        // Si el usuario escribió "CREATE" solo (exactamente como en su captura)
        if (upperTrim === "CREATE") {
            return " TABLE nombre_tabla (\n    id INT NOT NULL PRIMARY KEY,\n    nombre VARCHAR(50) NOT NULL\n);";
        }
        if (upperTrim === "SELECT") {
            return ` * FROM ${firstTbl} LIMIT 25;`;
        }
        return "";
    }

    _applySuggestion(item) {
        if (!this.textarea || !item) return;
        const val = this.textarea.value;
        const { start, end } = this.currentTokenRange;
        const suffix = item.kind === "SNIPPET" || item.insert.endsWith("(") ? "" : " ";
        const textToInsert = item.insert + suffix;
        this.textarea.value = val.slice(0, start) + textToInsert + val.slice(end);
        const newPos = start + textToInsert.length;
        this.textarea.setSelectionRange(newPos, newPos);
        this.textarea.focus();
        this.hidePopup();
        this.refreshHighlight();
        this.onChange(this.textarea.value);
    }

    hidePopup() {
        if (this.popup) this.popup.classList.add("hidden");
    }

    refreshHighlight() {
        if (!this.textarea || !this.highlightLayer || !this.gutter) return;
        const code = this.textarea.value;
        this.ghostText = this._computeLineSuggestion();

        const pos = this.textarea.selectionStart;
        const displayCode = this.ghostText ? code.slice(0, pos) + this.ghostText + code.slice(pos) : code;
        const lineCount = Math.max(1, displayCode.split("\n").length);
        let gutterHtml = "";
        for (let i = 1; i <= lineCount; i++) {
            if (this.errorLine === i) {
                gutterHtml += `<div class="gutter-error-line" title="Error SQL en línea ${i}">● ${i}</div>`;
            } else {
                gutterHtml += `<div>${i}</div>`;
            }
        }
        this.gutter.innerHTML = gutterHtml;

        let highlighted = "";
        if (this.ghostText) {
            const beforeHtml = this._highlightSQL(code.slice(0, pos));
            const ghostHtml = `<span class="hl-ghost">${this._escape(this.ghostText)}</span>`;
            const afterHtml = this._highlightSQL(code.slice(pos));
            highlighted = beforeHtml + ghostHtml + afterHtml;
        } else {
            highlighted = this._highlightSQL(code);
        }

        if (this.errorLine && this.errorLine >= 1) {
            const htmlLines = highlighted.split("\n");
            const errIdx = this.errorLine - 1;
            if (errIdx >= 0 && errIdx < htmlLines.length) {
                htmlLines[errIdx] = `<span class="hl-error-line">${htmlLines[errIdx] || " "}</span>`;
            }
            highlighted = htmlLines.join("\n");
        }

        this.highlightLayer.innerHTML = highlighted + "\n";
        this._syncScroll();
    }

    _keepActiveLineCentered() {
        if (!this.textarea) return;
        const pos = this.textarea.selectionStart;
        const lineNum = this.textarea.value.slice(0, pos).split("\n").length;
        const lineHeight = 20;
        const caretY = 10 + (lineNum - 1) * lineHeight;
        const visibleH = this.textarea.clientHeight;
        if (visibleH <= 0) return;

        const relY = caretY - this.textarea.scrollTop;
        // Mantener la línea activa ligeramente centrada (~45% de la altura visible):
        // si baja más allá del 56% del área visible, desliza el código hacia arriba dejando espacio libre abajo
        if (relY > visibleH * 0.56) {
            this.textarea.scrollTop = Math.max(0, Math.round(caretY - visibleH * 0.45));
            this._syncScroll();
        } else if (relY < visibleH * 0.12 && this.textarea.scrollTop > 0) {
            this.textarea.scrollTop = Math.max(0, Math.round(caretY - visibleH * 0.25));
            this._syncScroll();
        }
    }

    _syncScroll() {
        if (!this.textarea || !this.highlightLayer || !this.gutter) return;
        this.highlightLayer.scrollTop = this.textarea.scrollTop;
        this.highlightLayer.scrollLeft = this.textarea.scrollLeft;
        this.gutter.scrollTop = this.textarea.scrollTop;
    }

    _highlightSQL(raw) {
        let escaped = this._escape(raw);

        // Proteger comentarios y cadenas antes de resaltar palabras clave
        const placeholders = [];
        const stash = (html) => {
            const key = `___SQLTOK_${placeholders.length}___`;
            placeholders.push(html);
            return key;
        };

        // Comentarios de bloque /* ... */
        escaped = escaped.replace(/\/\*[\s\S]*?\*\//g, (m) => stash(`<span class="hl-comment">${m}</span>`));
        // Comentarios de línea -- ...
        escaped = escaped.replace(/--[^\n]*/g, (m) => stash(`<span class="hl-comment">${m}</span>`));
        // Cadenas entre comillas simples
        escaped = escaped.replace(/'(?:''|[^'])*'/g, (m) => stash(`<span class="hl-string">${m}</span>`));

        // Tipos de datos SQL
        const typeRegex =
            /\b(INTEGER|INT|SMALLINT|BIGINT|TINYINT|NVARCHAR|VARCHAR|CHAR|TEXT|DECIMAL|NUMERIC|FLOAT|REAL|DOUBLE|DATE|DATETIME2|DATETIME|TIMESTAMP|TIME|BOOLEAN|BIT|SERIAL|BLOB)\b/gi;
        escaped = escaped.replace(typeRegex, '<span class="hl-type">$1</span>');

        // Palabras clave SQL (DML + DDL Multi-Dialecto)
        const kwRegex =
            /\b(SELECT|FROM|WHERE|INNER|LEFT|RIGHT|OUTER|CROSS|JOIN|ON|GROUP|BY|HAVING|ORDER|ASC|DESC|LIMIT|OFFSET|DISTINCT|INSERT|INTO|VALUES|UPDATE|SET|DELETE|CREATE|DATABASE|USE|TABLE|INDEX|ALTER|ADD|COLUMN|DROP|IF|NOT|EXISTS|CONSTRAINT|PRIMARY|FOREIGN|KEY|REFERENCES|RESTRICT|CASCADE|NO|ACTION|NULL|UNIQUE|DEFAULT|CHECK|GENERATED|ALWAYS|STORED|VIRTUAL|AUTO_INCREMENT|AUTOINCREMENT|IDENTITY|CHARACTER|CHARSET|COLLATE|SHOW|TABLES|DATABASES|DESCRIBE|EXPLAIN|QUERY|PLAN|AND|OR|IN|LIKE|BETWEEN|IS|AS|COUNT|SUM|AVG|MIN|MAX|PRAGMA|ENGINE|UNSIGNED|GO|DB_ID|FOREIGN_KEY_CHECKS|NOCASE)\b/gi;
        escaped = escaped.replace(kwRegex, '<span class="hl-keyword">$1</span>');

        // Números
        escaped = escaped.replace(/\b(\d+(?:\.\d+)?)\b/g, '<span class="hl-number">$1</span>');

        // Restaurar comentarios y cadenas
        placeholders.forEach((html, i) => {
            escaped = escaped.replace(`___SQLTOK_${i}___`, html);
        });
        return escaped;
    }

    _escape(str) {
        return String(str || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }
}

window.SQLCodeEditorController = SQLCodeEditorController;
