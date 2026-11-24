/**
 * Módulo del Lienzo Visual Entidad-Relación (ER) Interactivo de SGBD-Smart.
 * Renderiza el Contrato Maestro JSON como un plano técnico con nodos de tablas arrastrables,
 * líneas de relación SVG con terminales de cardinalidad (1:1, 1:N, N:M) y selección interactiva.
 */

class ERCanvasController {
    constructor(options) {
        this.viewport = document.getElementById("er-canvas-viewport");
        this.stage = document.getElementById("er-canvas-stage");
        this.edgesSvg = document.getElementById("er-edges-svg");
        this.nodesLayer = document.getElementById("er-nodes-layer");
        this.zoomLabel = document.getElementById("zoom-level-label");

        this.onSelectElement = options.onSelectElement || (() => {});
        this.onSchemaMutated = options.onSchemaMutated || (() => {});
        this.onDeleteTable = options.onDeleteTable || (() => {});

        this.contract = null;
        this.selectedElement = null; // { type: 'table' | 'column' | 'relation', table, column, relation }
        this.zoom = 1.0;
        this.dragState = null;

        this._bindEvents();
    }

    _bindEvents() {
        window.addEventListener("mousemove", (e) => this._onMouseMove(e));
        window.addEventListener("mouseup", () => this._onMouseUp());
        let resizeTimer = null;
        window.addEventListener("resize", () => {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(() => this.fitToViewport(), 160);
        });

        const btnZoomIn = document.getElementById("btn-zoom-in");
        const btnZoomOut = document.getElementById("btn-zoom-out");
        const btnZoomReset = document.getElementById("btn-zoom-reset");
        const btnAutolayout = document.getElementById("btn-canvas-autolayout");

        if (btnZoomIn) btnZoomIn.addEventListener("click", () => this.setZoom(this.zoom + 0.1));
        if (btnZoomOut) btnZoomOut.addEventListener("click", () => this.setZoom(this.zoom - 0.1));
        if (btnZoomReset) btnZoomReset.addEventListener("click", () => this.fitToViewport());
        if (btnAutolayout) btnAutolayout.addEventListener("click", () => this.autoLayout());
    }

    setZoom(newZoom) {
        this.zoom = Math.max(0.55, Math.min(1.5, Math.round(newZoom * 100) / 100));
        this.stage.style.transform = `scale(${this.zoom})`;
        if (this.zoomLabel) {
            this.zoomLabel.textContent = `${Math.round(this.zoom * 100)}%`;
        }
    }

    fitToViewport() {
        if (!this.contract || !this.contract.tables || this.contract.tables.length === 0 || !this.viewport) {
            this.setZoom(1.0);
            return;
        }
        const NODE_W = 236;
        let maxX = 400;
        let maxY = 300;
        this.contract.tables.forEach((tbl) => {
            const xEnd = (tbl.position_x || 20) + NODE_W + 24;
            const yEnd = (tbl.position_y || 20) + 74 + (tbl.columns ? tbl.columns.length : 5) * 28;
            if (xEnd > maxX) maxX = xEnd;
            if (yEnd > maxY) maxY = yEnd;
        });
        const vw = this.viewport.clientWidth || 750;
        const vh = this.viewport.clientHeight || 580;
        const ratioX = (vw - 16) / maxX;
        const ratioY = (vh - 16) / maxY;
        const targetZoom = Math.min(1.0, ratioX, ratioY);
        this.setZoom(targetZoom);
    }

    autoLayout() {
        if (!this.contract || !this.contract.tables) return;
        const tables = this.contract.tables;
        const colsPerRow = tables.length > 4 ? 3 : 2;
        const xGap = 324;
        const yGap = 288;

        tables.forEach((tbl, idx) => {
            const c = idx % colsPerRow;
            const r = Math.floor(idx / colsPerRow);
            tbl.position_x = 20 + c * xGap;
            tbl.position_y = 20 + r * yGap;
        });

        this.render(this.contract);
        this.fitToViewport();
        this.onSchemaMutated(this.contract, false);
    }

    render(contract) {
        this.contract = contract;
        if (!contract) return;

        const alertedTables = new Set();
        const alertedColumns = new Set();
        const dangerousRelations = new Set();

        (contract.audit_alerts || []).forEach((al) => {
            if (al.affected_table) alertedTables.add(al.affected_table);
            if (al.affected_table && al.affected_column) {
                alertedColumns.add(`${al.affected_table}.${al.affected_column}`);
            }
            if (al.affected_relation_id) {
                dangerousRelations.add(al.affected_relation_id);
            }
        });

        this.nodesLayer.innerHTML = "";

        (contract.tables || []).forEach((tbl) => {
            const nodeEl = document.createElement("article");
            nodeEl.className = "er-table-node";
            nodeEl.dataset.table = tbl.name;
            if (alertedTables.has(tbl.name)) {
                nodeEl.classList.add("has-alert");
            }
            if (
                this.selectedElement &&
                this.selectedElement.type === "table" &&
                this.selectedElement.table === tbl.name
            ) {
                nodeEl.classList.add("selected");
            }

            nodeEl.style.left = `${tbl.position_x || 60}px`;
            nodeEl.style.top = `${tbl.position_y || 60}px`;

            // Cabecera de la tabla
            const headerEl = document.createElement("div");
            headerEl.className = "er-node-header";
            headerEl.innerHTML = `
                <div class="er-node-title-wrap">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                        <rect x="3" y="3" width="18" height="18" rx="2"></rect>
                        <line x1="3" y1="9" x2="21" y2="9"></line>
                    </svg>
                    <span class="er-node-title">${this._escape(tbl.name)}</span>
                </div>
                <div class="er-col-right">
                    ${tbl.is_associative ? '<span class="badge-nm" title="Tabla asociativa N:M">N:M</span>' : ""}
                    <button type="button" class="btn-delete-inline" data-node-delete="${this._escape(tbl.name)}" title="Eliminar tabla '${this._escape(tbl.name)}'" aria-label="Eliminar tabla ${this._escape(tbl.name)}">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
                            <polyline points="3 6 5 6 21 6"></polyline>
                            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"></path>
                        </svg>
                    </button>
                </div>
            `;

            const delBtn = headerEl.querySelector("[data-node-delete]");
            if (delBtn) {
                delBtn.addEventListener("mousedown", (e) => e.stopPropagation());
                delBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    this.onDeleteTable(tbl.name);
                });
            }

            const titleSpan = headerEl.querySelector(".er-node-title");
            if (titleSpan) {
                titleSpan.title = "Doble clic para renombrar tabla";
                titleSpan.addEventListener("dblclick", (e) => {
                    e.stopPropagation();
                    this._startInlineEdit(titleSpan, tbl.name, (newVal) => {
                        const clean = newVal.trim().replace(/\s+/g, "_");
                        if (!clean || clean === tbl.name) return;
                        const oldName = tbl.name;
                        tbl.name = clean;
                        (this.contract.relations || []).forEach((r) => {
                            if (r.source_table === oldName) r.source_table = clean;
                            if (r.target_table === oldName) r.target_table = clean;
                        });
                        (this.contract.tables || []).forEach((t) => {
                            (t.columns || []).forEach((c) => {
                                if (c.fk_target_table === oldName) c.fk_target_table = clean;
                            });
                        });
                        this.onSchemaMutated(this.contract, true);
                    });
                });
            }

            headerEl.addEventListener("mousedown", (e) => {
                if (e.button !== 0 || e.target.tagName === "INPUT") return;
                e.stopPropagation();
                this.selectElement({ type: "table", table: tbl.name, data: tbl });
                this.dragState = {
                    table: tbl,
                    nodeEl: nodeEl,
                    startX: e.clientX,
                    startY: e.clientY,
                    origX: tbl.position_x || 60,
                    origY: tbl.position_y || 60,
                };
            });

            // Lista de columnas
            const colsContainer = document.createElement("div");
            colsContainer.className = "er-node-columns";

            (tbl.columns || []).forEach((col) => {
                const colRow = document.createElement("div");
                colRow.className = "er-col-item";
                if (alertedColumns.has(`${tbl.name}.${col.name}`)) {
                    colRow.classList.add("col-flagged");
                }

                const badges = [];
                if (col.is_pk) badges.push('<i class="badge-pk" title="Clave Primaria">PK</i>');
                if (col.is_fk) badges.push('<i class="badge-fk" title="Clave Foránea">FK</i>');
                if (col.is_unique && !col.is_pk) badges.push('<i class="badge-uq" title="Restricción UNIQUE">UQ</i>');
                if (col.computed_expression) badges.push('<i class="badge-nm" title="Columna calculada: ' + this._escape(col.computed_expression) + '">FX</i>');

                const typeStr = col.length ? `${col.data_type}(${col.length})` : col.data_type;

                colRow.innerHTML = `
                    <div class="er-col-left">
                        ${badges.join("")}
                        <span class="er-col-name" title="Doble clic para renombrar columna o arrastra para seleccionar y copiar">${this._escape(col.name)}</span>
                    </div>
                    <div class="er-col-right">
                        <span class="er-col-type" title="Doble clic para editar tipo SQL">${this._escape(typeStr)}</span>
                    </div>
                `;

                const nameSpan = colRow.querySelector(".er-col-name");
                const typeSpan = colRow.querySelector(".er-col-type");

                if (nameSpan) {
                    nameSpan.addEventListener("dblclick", (e) => {
                        e.stopPropagation();
                        this._startInlineEdit(nameSpan, col.name, (newVal) => {
                            const clean = newVal.trim().replace(/\s+/g, "_");
                            if (!clean || clean === col.name) return;
                            const oldCol = col.name;
                            col.name = clean;
                            if (Array.isArray(tbl.primary_key)) {
                                tbl.primary_key = tbl.primary_key.map((p) => (p === oldCol ? clean : p));
                            }
                            (this.contract.relations || []).forEach((r) => {
                                if (r.source_table === tbl.name && r.source_column === oldCol) r.source_column = clean;
                                if (r.target_table === tbl.name && r.target_column === oldCol) r.target_column = clean;
                            });
                            this.onSchemaMutated(this.contract, true);
                        });
                    });
                }

                if (typeSpan) {
                    typeSpan.addEventListener("dblclick", (e) => {
                        e.stopPropagation();
                        this._startInlineEdit(typeSpan, typeStr, (newVal) => {
                            const raw = newVal.trim().toUpperCase();
                            if (!raw) return;
                            const mLen = raw.match(/^(VARCHAR|CHAR)\s*\(\s*(\d+)\s*\)$/);
                            if (mLen) {
                                col.data_type = mLen[1];
                                col.length = Number(mLen[2]);
                            } else {
                                col.data_type = raw;
                                col.length = null;
                            }
                            this.onSchemaMutated(this.contract, true);
                        });
                    });
                }

                colRow.addEventListener("click", (e) => {
                    if (window.getSelection && window.getSelection().toString().length > 0) return;
                    if (e.target.tagName === "INPUT") return;
                    e.stopPropagation();
                    this.selectElement({
                        type: "column",
                        table: tbl.name,
                        column: col.name,
                        data: col,
                        tableData: tbl,
                    });
                });

                colsContainer.appendChild(colRow);
            });

            // Pie de nodo con conteo de índices y columnas
            const footerEl = document.createElement("div");
            footerEl.className = "er-node-footer";
            const idxCount = (tbl.indexes || []).length;
            footerEl.innerHTML = `
                <span>${(tbl.columns || []).length} columnas</span>
                <span>${idxCount} índice${idxCount === 1 ? "" : "s"}</span>
            `;

            nodeEl.appendChild(headerEl);
            nodeEl.appendChild(colsContainer);
            nodeEl.appendChild(footerEl);
            this.nodesLayer.appendChild(nodeEl);
        });

        this._renderEdges(dangerousRelations);
    }

    _renderEdges(dangerousRelations = new Set()) {
        if (!this.contract) return;
        this.edgesSvg.innerHTML = `
            <defs>
                <pattern id="cad-blueprint-grid" width="80" height="80" patternUnits="userSpaceOnUse">
                    <path d="M 80 0 L 0 0 0 80" fill="none" stroke="var(--border-subtle)" stroke-width="0.75" opacity="0.65"/>
                    <circle cx="40" cy="40" r="1" fill="var(--border-strong)" opacity="0.7"/>
                </pattern>
            </defs>
            <rect width="100%" height="100%" fill="url(#cad-blueprint-grid)" pointer-events="none"/>
        `;

        const tableMap = {};
        (this.contract.tables || []).forEach((t) => {
            tableMap[t.name] = t;
        });

        const NODE_WIDTH = 236;

        (this.contract.relations || []).forEach((rel) => {
            const srcTbl = tableMap[rel.source_table];
            const tgtTbl = tableMap[rel.target_table];
            if (!srcTbl || !tgtTbl) return;

            const srcColIndex = Math.max(
                0,
                (srcTbl.columns || []).findIndex((c) => c.name === rel.source_column)
            );
            const tgtColIndex = Math.max(
                0,
                (tgtTbl.columns || []).findIndex((c) => c.name === rel.target_column)
            );

            const srcY = (srcTbl.position_y || 60) + 52 + srcColIndex * 27;
            const tgtY = (tgtTbl.position_y || 60) + 52 + tgtColIndex * 27;

            const srcCenterX = (srcTbl.position_x || 60) + NODE_WIDTH / 2;
            const tgtCenterX = (tgtTbl.position_x || 60) + NODE_WIDTH / 2;

            let x1, x2, c1x, c2x;
            if (srcCenterX <= tgtCenterX) {
                x1 = (srcTbl.position_x || 60) + NODE_WIDTH;
                x2 = tgtTbl.position_x || 60;
                const dx = Math.max(55, Math.abs(x2 - x1) * 0.45);
                c1x = x1 + dx;
                c2x = x2 - dx;
            } else {
                x1 = srcTbl.position_x || 60;
                x2 = (tgtTbl.position_x || 60) + NODE_WIDTH;
                const dx = Math.max(55, Math.abs(x2 - x1) * 0.45);
                c1x = x1 - dx;
                c2x = x2 + dx;
            }

            const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
            g.setAttribute("class", "er-edge-group");
            if (
                this.selectedElement &&
                this.selectedElement.type === "relation" &&
                this.selectedElement.relation === rel.id
            ) {
                g.classList.add("selected");
            }

            const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
            const d = `M ${x1} ${srcY} C ${c1x} ${srcY}, ${c2x} ${tgtY}, ${x2} ${tgtY}`;
            path.setAttribute("d", d);
            path.setAttribute(
                "class",
                `er-edge-path ${dangerousRelations.has(rel.id) ? "edge-danger" : ""}`
            );
            g.appendChild(path);

            // Puntos de anclaje en ambos extremos
            const cSrc = document.createElementNS("http://www.w3.org/2000/svg", "circle");
            cSrc.setAttribute("cx", String(x1));
            cSrc.setAttribute("cy", String(srcY));
            cSrc.setAttribute("r", "4");
            cSrc.setAttribute("fill", "var(--accent-indigo)");
            g.appendChild(cSrc);

            const cTgt = document.createElementNS("http://www.w3.org/2000/svg", "circle");
            cTgt.setAttribute("cx", String(x2));
            cTgt.setAttribute("cy", String(tgtY));
            cTgt.setAttribute("r", "4");
            cTgt.setAttribute("fill", "var(--accent-cyan)");
            g.appendChild(cTgt);

            // Etiqueta central de cardinalidad y política ON DELETE
            const midX = (x1 + x2) / 2;
            const midY = (srcY + tgtY) / 2;
            const shortPolicy = rel.on_delete === "CASCADE" ? "CASC" : rel.on_delete === "SET NULL" ? "NULL" : "RESTR";
            const labelText = `${rel.cardinality}·${shortPolicy}`;
            const boxWidth = labelText.length * 6.2 + 12;

            const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
            rect.setAttribute("x", String(midX - boxWidth / 2));
            rect.setAttribute("y", String(midY - 10));
            rect.setAttribute("width", String(boxWidth));
            rect.setAttribute("height", "20");
            rect.setAttribute("class", "er-edge-label-bg");
            g.appendChild(rect);

            const txt = document.createElementNS("http://www.w3.org/2000/svg", "text");
            txt.setAttribute("x", String(midX));
            txt.setAttribute("y", String(midY + 3.5));
            txt.setAttribute("text-anchor", "middle");
            txt.setAttribute("class", "er-edge-label-text");
            txt.textContent = labelText;
            g.appendChild(txt);

            g.addEventListener("click", (e) => {
                e.stopPropagation();
                this.selectElement({ type: "relation", relation: rel.id, data: rel });
            });

            this.edgesSvg.appendChild(g);
        });
    }

    selectElement(selection) {
        this.selectedElement = selection;
        this.render(this.contract);
        this.onSelectElement(selection);
    }

    _onMouseMove(e) {
        if (!this.dragState) return;
        const dx = (e.clientX - this.dragState.startX) / this.zoom;
        const dy = (e.clientY - this.dragState.startY) / this.zoom;

        const newX = Math.max(12, Math.round(this.dragState.origX + dx));
        const newY = Math.max(12, Math.round(this.dragState.origY + dy));

        this.dragState.table.position_x = newX;
        this.dragState.table.position_y = newY;
        this.dragState.nodeEl.style.left = `${newX}px`;
        this.dragState.nodeEl.style.top = `${newY}px`;

        this._renderEdges();
    }

    _onMouseUp() {
        if (!this.dragState) return;
        this.dragState = null;
    }

    _startInlineEdit(spanEl, initialValue, onCommit) {
        const input = document.createElement("input");
        input.type = "text";
        input.className = "er-inline-input";
        input.value = initialValue;
        spanEl.textContent = "";
        spanEl.appendChild(input);
        input.focus();
        input.select();

        let done = false;
        const finish = (save) => {
            if (done) return;
            done = true;
            const val = input.value;
            spanEl.textContent = save && val.trim() ? val.trim() : initialValue;
            if (save) onCommit(val);
        };

        input.addEventListener("blur", () => finish(true));
        input.addEventListener("keydown", (ev) => {
            if (ev.key === "Enter") {
                ev.preventDefault();
                finish(true);
            } else if (ev.key === "Escape") {
                ev.preventDefault();
                finish(false);
            }
        });
    }

    _escape(str) {
        return String(str || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }
}

window.ERCanvasController = ERCanvasController;
