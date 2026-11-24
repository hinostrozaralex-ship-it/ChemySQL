/**
 * Motor Interactivo de Diagrama Relacional para SGBD-Smart.
 * Soporta dos notaciones académicas sincronizadas en tiempo real con el Contrato Maestro JSON:
 *   1. Conceptual (Notación de Chen): Entidades (rectángulos), Relaciones (rombos con verbo y cardinalidades),
 *      Atributos (óvalos con subrayado PK, subrayado discontinuo UK, borde punteado para derivados/calculados).
 *   2. Paso a Tablas (Claves): Tablas de dos columnas (atributo | pk, nn, uk, fk, fx) con arcos interactivos
 *      desde cada clave foránea hacia su clave primaria referenciada y marcadores de obligatoriedad (| / ○).
 * Incluye arrastre libre, zoom, plegado de atributos, edición de verbos y exportación a SVG / PNG.
 */

class RelationalDiagramController {
    constructor(options = {}) {
        this.viewport = document.getElementById("reldiag-viewport");
        this.svg = document.getElementById("reldiag-svg");
        this.zoomLabel = document.getElementById("reldiag-zoom-label");
        this.legendEl = document.getElementById("reldiag-legend");

        this.onSelectElement = options.onSelectElement || (() => {});
        this.onNotify = options.onNotify || (() => {});

        this.contract = null;
        this.submode = "chen"; // 'chen' | 'tables'
        this.showAttributes = true;
        this.zoom = 1.0;
        this.panX = 0;
        this.panY = 0;

        // Posiciones personalizadas arrastradas por el usuario (por submodo y db_name)
        this.positions = { chen: {}, tables: {} };
        this.customVerbs = {};
        this.lastDbKey = "";

        this._dragState = null;
        this._bindGlobalInteractions();
    }

    _bindGlobalInteractions() {
        if (!this.viewport || !this.svg) return;

        // Zoom con Ctrl + rueda o rueda normal sobre el lienzo
        this.viewport.addEventListener(
            "wheel",
            (e) => {
                if (!this.contract) return;
                if (e.ctrlKey) {
                    e.preventDefault();
                    const delta = e.deltaY < 0 ? 0.1 : -0.1;
                    this.setZoom(this.zoom + delta);
                }
            },
            { passive: false }
        );

        // Arrastre de nodos SVG o desplazamiento (pan) del fondo
        this.svg.addEventListener("mousedown", (e) => {
            const dragTarget = e.target.closest("[data-drag-id]");
            if (dragTarget) {
                e.preventDefault();
                const id = dragTarget.getAttribute("data-drag-id");
                const posMap = this.positions[this.submode];
                const cur = posMap[id] || { x: 0, y: 0 };
                this._dragState = {
                    type: "node",
                    id,
                    startMouseX: e.clientX,
                    startMouseY: e.clientY,
                    origX: cur.x,
                    origY: cur.y,
                    moved: false,
                };
                return;
            }
            // Pan del lienzo al arrastrar el fondo vacío
            this._dragState = {
                type: "pan",
                startMouseX: e.clientX,
                startMouseY: e.clientY,
                origPanX: this.panX,
                origPanY: this.panY,
                moved: false,
            };
            this.viewport.style.cursor = "grabbing";
        });

        window.addEventListener("mousemove", (e) => {
            if (!this._dragState) return;
            const rawDx = e.clientX - this._dragState.startMouseX;
            const rawDy = e.clientY - this._dragState.startMouseY;
            if (Math.abs(rawDx) > 3 || Math.abs(rawDy) > 3) {
                this._dragState.moved = true;
            }
            const dx = rawDx / this.zoom;
            const dy = rawDy / this.zoom;
            if (this._dragState.type === "node") {
                const posMap = this.positions[this.submode];
                posMap[this._dragState.id] = {
                    x: this._dragState.origX + dx,
                    y: this._dragState.origY + dy,
                };
                this._renderCurrent();
            } else if (this._dragState.type === "pan") {
                this.panX = this._dragState.origPanX + rawDx;
                this.panY = this._dragState.origPanY + rawDy;
                this._applyTransform();
            }
        });

        window.addEventListener("mouseup", () => {
            if (this._dragState) {
                const drag = this._dragState;
                this._dragState = null;
                if (this.viewport) this.viewport.style.cursor = "";
                if (drag.type === "node" && !drag.moved && this.contract) {
                    if (drag.id.startsWith("ent:") || drag.id.startsWith("tbl:")) {
                        const tblName = drag.id.slice(4);
                        const tbl = (this.contract.tables || []).find((t) => t.name === tblName);
                        if (tbl) {
                            this.onSelectElement({ type: "table", table: tbl.name, data: tbl });
                        }
                    } else if (drag.id.startsWith("rel:")) {
                        const relId = drag.id.slice(4);
                        const rel = (this.contract.relations || []).find((r) => r.id === relId);
                        if (rel) {
                            this.onSelectElement({ type: "relation", relation: rel.id, data: rel });
                        }
                    }
                }
            }
        });

        // Doble clic en un rombo de relación para renombrar su verbo
        this.svg.addEventListener("dblclick", (e) => {
            const relNode = e.target.closest("[data-rel-verb-id]");
            if (!relNode) return;
            const relId = relNode.getAttribute("data-rel-verb-id");
            const currentVerb = relNode.getAttribute("data-rel-verb") || "Relaciona";
            const newVerb = window.prompt("Verbo o nombre de la relación en el rombo:", currentVerb);
            if (newVerb && newVerb.trim()) {
                this.customVerbs[relId] = newVerb.trim();
                this._renderCurrent();
            }
        });

        // Resaltado interactivo de pares FK <-> PK al pasar el cursor en Paso a Tablas
        this.svg.addEventListener("mouseover", (e) => {
            const keyRow = e.target.closest("[data-key-ref]");
            if (!keyRow) return;
            const refId = keyRow.getAttribute("data-key-ref");
            this.svg.querySelectorAll(`[data-arc-id="${refId}"]`).forEach((el) => {
                el.classList.add("rd-arc-highlight");
            });
        });
        this.svg.addEventListener("mouseout", (e) => {
            const keyRow = e.target.closest("[data-key-ref]");
            if (!keyRow) return;
            this.svg.querySelectorAll(".rd-arc-highlight").forEach((el) => {
                el.classList.remove("rd-arc-highlight");
            });
        });
    }

    setSubmode(mode) {
        this.submode = mode === "tables" ? "tables" : "chen";
        this._updateLegend();
        this._renderCurrent();
        this.fitToViewport();
    }

    toggleAttributes() {
        this.showAttributes = !this.showAttributes;
        this._renderCurrent();
        return this.showAttributes;
    }

    setZoom(nextZoom) {
        this.zoom = Math.max(0.35, Math.min(2.2, Number(nextZoom.toFixed(2))));
        if (this.zoomLabel) {
            this.zoomLabel.textContent = `${Math.round(this.zoom * 100)}%`;
        }
        this._applyTransform();
    }

    resetLayout() {
        this.positions[this.submode] = {};
        this._renderCurrent();
        this.fitToViewport();
    }

    fitToViewport() {
        if (!this.viewport || !this.svg) return;
        const root = this.svg.querySelector("#reldiag-root");
        if (!root) return;
        try {
            const bbox = root.getBBox();
            if (!bbox || bbox.width <= 0 || bbox.height <= 0) return;
            const vw = Math.max(300, this.viewport.clientWidth);
            const vh = Math.max(260, this.viewport.clientHeight);
            const pad = 40;
            const scaleX = (vw - pad * 2) / bbox.width;
            const scaleY = (vh - pad * 2) / bbox.height;
            const fitZoom = Math.max(0.45, Math.min(1.15, Math.min(scaleX, scaleY)));
            this.zoom = Number(fitZoom.toFixed(2));
            this.panX = (vw - bbox.width * this.zoom) / 2 - bbox.x * this.zoom;
            this.panY = (vh - bbox.height * this.zoom) / 2 - bbox.y * this.zoom;
            if (this.zoomLabel) {
                this.zoomLabel.textContent = `${Math.round(this.zoom * 100)}%`;
            }
            this._applyTransform();
        } catch (_err) {
            // Ignorar si el SVG está oculto (display:none)
        }
    }

    _applyTransform() {
        if (!this.svg) return;
        const root = this.svg.querySelector("#reldiag-root");
        if (root) {
            root.setAttribute("transform", `translate(${this.panX}, ${this.panY}) scale(${this.zoom})`);
        }
    }

    render(contract) {
        this.contract = contract;
        if (!contract) return;

        const dbKey = `${contract.db_name}::${(contract.tables || []).map((t) => t.name).join(",")}`;
        if (dbKey !== this.lastDbKey) {
            this.positions = { chen: {}, tables: {} };
            this.lastDbKey = dbKey;
        }

        this._updateLegend();
        this._renderCurrent();
    }

    _updateLegend() {
        if (!this.legendEl) return;
        if (this.submode === "chen") {
            this.legendEl.innerHTML = `
                <span class="legend-chip"><i class="rd-leg-rect"></i> Entidad</span>
                <span class="legend-chip"><i class="rd-leg-diamond"></i> Relación (doble clic: editar verbo)</span>
                <span class="legend-chip"><i class="rd-leg-oval-pk"></i> PK (subrayado)</span>
                <span class="legend-chip"><i class="rd-leg-oval-uk"></i> UK (discontinuo)</span>
                <span class="legend-chip"><i class="rd-leg-oval-fx"></i> Derivado (calculado)</span>
            `;
        } else {
            this.legendEl.innerHTML = `
                <span class="legend-chip"><i class="badge-pk">pk</i> Primaria</span>
                <span class="legend-chip"><i class="badge-fk">fk</i> Foránea</span>
                <span class="legend-chip"><i class="badge-uq">uk</i> Única</span>
                <span class="legend-chip"><i class="rd-leg-nn">nn</i> Obligatoria (|)</span>
                <span class="legend-chip"><i class="rd-leg-opt">○</i> Opcional (NULL)</span>
            `;
        }
    }

    _renderCurrent() {
        if (!this.svg || !this.contract) return;
        const tables = this.contract.tables || [];
        if (tables.length === 0) {
            this.svg.innerHTML = `<g id="reldiag-root"><text x="60" y="80" class="rd-empty-text">No hay tablas en el esquema actual.</text></g>`;
            return;
        }
        if (this.submode === "chen") {
            this._renderChenDiagram();
        } else {
            this._renderTableMappingDiagram();
        }
        this._applyTransform();
    }

    /* =========================================================================
       MODO 1: DIAGRAMA CONCEPTUAL (NOTACIÓN DE CHEN)
       ========================================================================= */
    _inferVerb(srcTable, tgtTable, rel) {
        if (this.customVerbs[rel.id]) return this.customVerbs[rel.id];
        const pair = `${tgtTable.toLowerCase()}->${srcTable.toLowerCase()}`;
        const known = {
            "instalacion->pista": "Contiene",
            "instalaciones->pistas": "Contiene",
            "pista->reserva": "Se reserva en",
            "pistas->reservas": "Se reserva en",
            "socio->reserva": "Realiza",
            "socios->reservas": "Realiza",
            "clientes->vehiculos": "Posee",
            "vehiculos->reparaciones": "Tiene",
            "clientes->facturas": "Recibe",
            "facturas->pagos": "Se liquida con",
            "autores->libros": "Escribe",
            "socios->prestamos": "Realiza",
            "libros->prestamos": "Se presta en",
            "pacientes->citas": "Agenda",
            "medicos->citas": "Atiende",
            "departamentos->empleados": "Agrupa",
            "clientes->pedidos": "Realiza",
            "categorias->productos": "Clasifica",
            "proveedores->productos": "Suministra",
            "habitaciones->reservas": "Asigna",
            "huespedes->reservas": "Efectúa",
        };
        if (known[pair]) return known[pair];
        if (srcTable.toLowerCase() === tgtTable.toLowerCase()) return "Se asocia con";
        if (rel.cardinality === "N:M") return "Participa en";
        return "Tiene";
    }

    _renderChenDiagram() {
        const tables = this.contract.tables || [];
        const relations = this.contract.relations || [];
        const posMap = this.positions.chen;

        // Identificar tablas asociativas N:M para representarlas como rombos entre sus dos entidades padre
        const assocTables = new Set(tables.filter((t) => t.is_associative).map((t) => t.name));
        const entityTables = tables.filter((t) => !assocTables.has(t.name));

        // 1. Calcular posiciones iniciales de entidades en una cuadrícula generosa
        const colsPerRow = entityTables.length <= 2 ? 2 : entityTables.length <= 4 ? 2 : 3;
        const spacingX = this.showAttributes ? 480 : 340;
        const spacingY = this.showAttributes ? 390 : 250;

        entityTables.forEach((tbl, idx) => {
            const key = `ent:${tbl.name}`;
            if (!posMap[key]) {
                const col = idx % colsPerRow;
                const row = Math.floor(idx / colsPerRow);
                posMap[key] = {
                    x: 220 + col * spacingX,
                    y: 190 + row * spacingY,
                };
            }
        });

        // 2. Construir lista de rombos de relación (1:N, 1:1, reflexivas y N:M)
        const chenRelations = [];
        const handledAssoc = new Set();

        // Rombos para tablas asociativas N:M
        tables.forEach((tbl) => {
            if (!assocTables.has(tbl.name)) return;
            const assocRels = relations.filter((r) => r.source_table === tbl.name);
            if (assocRels.length >= 2) {
                const leftEnt = assocRels[0].target_table;
                const rightEnt = assocRels[1].target_table;
                const extraAttrs = (tbl.columns || []).filter((c) => !c.is_pk && !c.is_fk);
                chenRelations.push({
                    id: `assoc_${tbl.name}`,
                    left: leftEnt,
                    right: rightEnt,
                    verb: this.customVerbs[`assoc_${tbl.name}`] || tbl.name.replace(/_/g, " "),
                    leftCard: "(0,N)",
                    rightCard: "(0,N)",
                    isDouble: true,
                    isReflexive: leftEnt === rightEnt,
                    extraAttrs,
                });
                handledAssoc.add(tbl.name);
            }
        });

        // Rombos para relaciones directas (no asociativas)
        relations.forEach((rel) => {
            if (handledAssoc.has(rel.source_table) || assocTables.has(rel.source_table)) return;
            const srcTbl = tables.find((t) => t.name === rel.source_table);
            const fkCol = srcTbl ? (srcTbl.columns || []).find((c) => c.name === rel.source_column) : null;
            const isMandatory = fkCol ? !fkCol.nullable : true;
            const isWeakRel = Boolean(fkCol && fkCol.is_pk);
            const minSrc = isMandatory ? "1" : "0";
            const maxSrc = rel.cardinality === "1:1" ? "1" : "N";
            chenRelations.push({
                id: rel.id,
                left: rel.target_table, // Lado 1 (padre)
                right: rel.source_table, // Lado N (hija)
                verb: this._inferVerb(rel.source_table, rel.target_table, rel),
                leftCard: rel.cardinality === "1:1" ? `(${minSrc},1)` : `(0,${maxSrc})`,
                rightCard: `(${minSrc},1)`,
                isDouble: isWeakRel,
                isReflexive: rel.source_table === rel.target_table,
                extraAttrs: [],
            });
        });

        // Posicionar cada rombo en el punto medio de sus entidades (o a la derecha si es reflexiva)
        chenRelations.forEach((cr, idx) => {
            const key = `rel:${cr.id}`;
            if (!posMap[key]) {
                const pL = posMap[`ent:${cr.left}`] || { x: 220, y: 190 };
                const pR = posMap[`ent:${cr.right}`] || { x: 520, y: 190 };
                if (cr.isReflexive) {
                    posMap[key] = { x: pL.x + 190, y: pL.y };
                } else {
                    const offset = (idx % 2 === 0 ? -1 : 1) * 14;
                    posMap[key] = {
                        x: (pL.x + pR.x) / 2 + offset,
                        y: (pL.y + pR.y) / 2 + offset,
                    };
                }
            }
        });

        // 3. Posicionar óvalos de atributos alrededor de cada entidad
        const attrNodes = [];
        if (this.showAttributes) {
            entityTables.forEach((tbl) => {
                const entPos = posMap[`ent:${tbl.name}`];
                // En Chen conceptual, las FK puras (que no son PK) se representan con el rombo, pero si forman parte de PK compuesta sí se muestran
                const visibleCols = (tbl.columns || []).filter((c) => !c.is_fk || c.is_pk);
                const count = visibleCols.length;
                visibleCols.forEach((col, i) => {
                    const aKey = `attr:${tbl.name}.${col.name}`;
                    if (!posMap[aKey]) {
                        // Distribuir en arco superior e inferior para dejar libres los laterales a los rombos
                        const half = Math.ceil(count / 2);
                        const isTop = i < half;
                        const slotIdx = isTop ? i : i - half;
                        const slotTotal = isTop ? half : Math.max(1, count - half);
                        const spread = Math.min(340, Math.max(160, slotTotal * 98));
                        const startX = entPos.x - spread / 2;
                        const stepX = slotTotal > 1 ? spread / (slotTotal - 1) : 0;
                        const ax = slotTotal === 1 ? entPos.x : startX + slotIdx * stepX;
                        const archOffset = slotTotal > 2 ? Math.abs(slotIdx - (slotTotal - 1) / 2) * 14 : 0;
                        const ay = isTop ? entPos.y - 105 + archOffset : entPos.y + 105 - archOffset;
                        posMap[aKey] = { x: ax, y: ay };
                    }
                    attrNodes.push({
                        key: aKey,
                        table: tbl.name,
                        col,
                        pos: posMap[aKey],
                        entPos,
                    });
                });
            });
        }

        // 4. Ensamblar capas SVG: líneas -> rombos -> entidades -> óvalos
        let linesSvg = "";
        let shapesSvg = "";

        // Líneas de atributos
        attrNodes.forEach((a) => {
            const isDerived = Boolean(a.col.computed_expression);
            linesSvg += `<line x1="${a.entPos.x}" y1="${a.entPos.y}" x2="${a.pos.x}" y2="${a.pos.y}" class="rd-attr-line ${isDerived ? "rd-dashed" : ""}" />`;
        });

        // Líneas y cardinalidades de relaciones
        chenRelations.forEach((cr) => {
            const pRel = posMap[`rel:${cr.id}`];
            const pL = posMap[`ent:${cr.left}`];
            const pR = posMap[`ent:${cr.right}`];
            if (!pRel || !pL || !pR) return;

            if (cr.isReflexive) {
                // Dos arcos curvos (Rol1 arriba, Rol2 abajo) como en la imagen de referencia
                const dTop = `M ${pL.x + 68} ${pL.y - 10} C ${pL.x + 115} ${pL.y - 70}, ${pRel.x - 45} ${pRel.y - 70}, ${pRel.x - 56} ${pRel.y - 4}`;
                const dBot = `M ${pL.x + 68} ${pL.y + 10} C ${pL.x + 115} ${pL.y + 70}, ${pRel.x - 45} ${pRel.y + 70}, ${pRel.x - 56} ${pRel.y + 4}`;
                linesSvg += `<path d="${dTop}" class="rd-rel-line" fill="none" />`;
                linesSvg += `<path d="${dBot}" class="rd-rel-line" fill="none" />`;
                linesSvg += `<text x="${(pL.x + pRel.x) / 2}" y="${pL.y - 54}" class="rd-card-label" text-anchor="middle">${this._esc(cr.leftCard)} · Rol 1</text>`;
                linesSvg += `<text x="${(pL.x + pRel.x) / 2}" y="${pL.y + 66}" class="rd-card-label" text-anchor="middle">${this._esc(cr.rightCard)} · Rol 2</text>`;
            } else {
                linesSvg += `<line x1="${pL.x}" y1="${pL.y}" x2="${pRel.x}" y2="${pRel.y}" class="rd-rel-line" />`;
                linesSvg += `<line x1="${pRel.x}" y1="${pRel.y}" x2="${pR.x}" y2="${pR.y}" class="rd-rel-line" />`;

                const lx = pL.x + (pRel.x - pL.x) * 0.45;
                const ly = pL.y + (pRel.y - pL.y) * 0.45 - 9;
                const rx = pR.x + (pRel.x - pR.x) * 0.45;
                const ry = pR.y + (pRel.y - pR.y) * 0.45 - 9;
                linesSvg += `<rect x="${lx - 22}" y="${ly - 12}" width="44" height="16" rx="4" class="rd-card-bg" />`;
                linesSvg += `<text x="${lx}" y="${ly}" class="rd-card-label" text-anchor="middle">${this._esc(cr.leftCard)}</text>`;
                linesSvg += `<rect x="${rx - 22}" y="${ry - 12}" width="44" height="16" rx="4" class="rd-card-bg" />`;
                linesSvg += `<text x="${rx}" y="${ry}" class="rd-card-label" text-anchor="middle">${this._esc(cr.rightCard)}</text>`;
            }

            // Atributos propios de relación N:M
            if (this.showAttributes && cr.extraAttrs.length > 0) {
                cr.extraAttrs.forEach((col, ci) => {
                    const ox = pRel.x + (ci - (cr.extraAttrs.length - 1) / 2) * 104;
                    const oy = pRel.y - 78;
                    linesSvg += `<line x1="${pRel.x}" y1="${pRel.y}" x2="${ox}" y2="${oy}" class="rd-attr-line" />`;
                    const rxOval = Math.max(44, col.name.length * 4.2 + 16);
                    shapesSvg += `
                        <g class="rd-oval-node">
                            <ellipse cx="${ox}" cy="${oy}" rx="${rxOval}" ry="17" class="rd-oval" />
                            <text x="${ox}" y="${oy + 4}" class="rd-oval-text" text-anchor="middle">${this._esc(col.name)}</text>
                        </g>
                    `;
                });
            }
        });

        // Rombos de relación
        chenRelations.forEach((cr) => {
            const p = posMap[`rel:${cr.id}`];
            if (!p) return;
            const w = Math.max(66, cr.verb.length * 4.6 + 24);
            const h = 36;
            const pts = `${p.x},${p.y - h} ${p.x + w},${p.y} ${p.x},${p.y + h} ${p.x - w},${p.y}`;
            const innerPts = `${p.x},${p.y - h + 6} ${p.x + w - 9},${p.y} ${p.x},${p.y + h - 6} ${p.x - w + 9},${p.y}`;
            shapesSvg += `
                <g class="rd-draggable rd-diamond-node" data-drag-id="rel:${this._esc(cr.id)}" data-rel-verb-id="${this._esc(cr.id)}" data-rel-verb="${this._esc(cr.verb)}">
                    <polygon points="${pts}" class="rd-diamond" />
                    ${cr.isDouble ? `<polygon points="${innerPts}" class="rd-diamond-inner" />` : ""}
                    <text x="${p.x}" y="${p.y + 4}" class="rd-diamond-text" text-anchor="middle">${this._esc(cr.verb)}</text>
                </g>
            `;
        });

        // Rectángulos de entidades
        entityTables.forEach((tbl) => {
            const p = posMap[`ent:${tbl.name}`];
            if (!p) return;
            const pkCols = (tbl.columns || []).filter((c) => c.is_pk);
            const isWeak = pkCols.length > 1 && pkCols.some((c) => c.is_fk);
            const w = Math.max(138, tbl.name.length * 9.2 + 34);
            const h = 44;
            shapesSvg += `
                <g class="rd-draggable rd-entity-node" data-drag-id="ent:${this._esc(tbl.name)}">
                    <rect x="${p.x - w / 2}" y="${p.y - h / 2}" width="${w}" height="${h}" rx="4" class="rd-entity-rect" />
                    ${isWeak ? `<rect x="${p.x - w / 2 + 5}" y="${p.y - h / 2 + 5}" width="${w - 10}" height="${h - 10}" rx="2" class="rd-entity-rect-inner" />` : ""}
                    <text x="${p.x}" y="${p.y + 5}" class="rd-entity-text" text-anchor="middle">${this._esc(tbl.name)}</text>
                </g>
            `;
        });

        // Óvalos de atributos
        attrNodes.forEach((a) => {
            const isPk = Boolean(a.col.is_pk);
            const isUk = Boolean(a.col.is_unique && !isPk);
            const isDerived = Boolean(a.col.computed_expression);
            const rx = Math.max(46, a.col.name.length * 4.2 + 18);
            const ry = 17;
            const textW = Math.min(rx * 1.45, a.col.name.length * 7.2);
            shapesSvg += `
                <g class="rd-draggable rd-oval-node" data-drag-id="${this._esc(a.key)}">
                    <ellipse cx="${a.pos.x}" cy="${a.pos.y}" rx="${rx}" ry="${ry}" class="rd-oval ${isPk ? "rd-oval-pk" : ""} ${isDerived ? "rd-oval-derived" : ""}" />
                    <text x="${a.pos.x}" y="${a.pos.y + 4}" class="rd-oval-text ${isPk ? "rd-text-pk" : ""}" text-anchor="middle">${this._esc(a.col.name)}</text>
                    ${isPk ? `<line x1="${a.pos.x - textW / 2}" y1="${a.pos.y + 8}" x2="${a.pos.x + textW / 2}" y2="${a.pos.y + 8}" class="rd-underline-pk" />` : ""}
                    ${isUk ? `<line x1="${a.pos.x - textW / 2}" y1="${a.pos.y + 8}" x2="${a.pos.x + textW / 2}" y2="${a.pos.y + 8}" class="rd-underline-uk" />` : ""}
                </g>
            `;
        });

        this.svg.innerHTML = `<g id="reldiag-root">${linesSvg}${shapesSvg}</g>`;
    }

    /* =========================================================================
       MODO 2: PASO A TABLAS (NOTACIÓN DE CLAVES pk, nn, uk, fk + ARCOS | / ○)
       ========================================================================= */
    _renderTableMappingDiagram() {
        const tables = this.contract.tables || [];
        const relations = this.contract.relations || [];
        const posMap = this.positions.tables;

        const tblW = 264;
        const headerH = 34;
        const rowH = 26;
        const colsPerRow = tables.length <= 2 ? 2 : tables.length <= 4 ? 2 : 3;
        const gapX = 360;
        const gapY = 310;

        // 1. Posiciones iniciales de cada tabla
        const boxByTable = {};
        tables.forEach((tbl, idx) => {
            const key = `tbl:${tbl.name}`;
            if (!posMap[key]) {
                const c = idx % colsPerRow;
                const r = Math.floor(idx / colsPerRow);
                posMap[key] = {
                    x: 70 + c * gapX,
                    y: 60 + r * gapY,
                };
            }
            const p = posMap[key];
            const h = headerH + Math.max(1, (tbl.columns || []).length) * rowH;
            boxByTable[tbl.name] = { x: p.x, y: p.y, w: tblW, h, tbl };
        });

        // Mapear qué arcos conectan a cada columna para hover
        const colRelMap = {};
        relations.forEach((rel) => {
            const kSrc = `${rel.source_table}.${rel.source_column}`;
            const kTgt = `${rel.target_table}.${rel.target_column}`;
            colRelMap[kSrc] = rel.id;
            if (!colRelMap[kTgt]) colRelMap[kTgt] = rel.id;
        });

        // 2. Renderizar tablas (dos columnas: atributo | siglas pk, nn, uk, fk, fx)
        let tablesSvg = "";
        tables.forEach((tbl) => {
            const b = boxByTable[tbl.name];
            const cols = tbl.columns || [];
            const splitX = b.x + b.w - 86;

            let rowsSvg = "";
            cols.forEach((col, rIdx) => {
                const ry = b.y + headerH + rIdx * rowH;
                const flags = [];
                if (col.is_pk) flags.push("pk");
                if (!col.nullable && !col.is_pk && !col.computed_expression) flags.push("nn");
                if (col.is_fk) flags.push("fk");
                if (col.is_unique && !col.is_pk) flags.push("uk");
                if (col.computed_expression) flags.push("fx");
                const flagsText = flags.join(",");
                const refId = colRelMap[`${tbl.name}.${col.name}`] || "";
                const rowClass = col.is_pk ? "rd-trow-pk" : col.is_fk ? "rd-trow-fk" : "";

                rowsSvg += `
                    <g class="rd-trow ${rowClass}" ${refId ? `data-key-ref="${this._esc(refId)}"` : ""}>
                        <rect x="${b.x}" y="${ry}" width="${b.w}" height="${rowH}" class="rd-trow-bg" />
                        <line x1="${b.x}" y1="${ry}" x2="${b.x + b.w}" y2="${ry}" class="rd-trow-sep" />
                        <text x="${b.x + 10}" y="${ry + 17}" class="rd-tcol-name ${col.is_pk ? "rd-text-pk" : ""}">${this._esc(col.name)}</text>
                        <text x="${splitX + 8}" y="${ry + 17}" class="rd-tcol-flags">${this._esc(flagsText)}</text>
                    </g>
                `;
            });

            tablesSvg += `
                <g class="rd-draggable rd-table-box" data-drag-id="tbl:${this._esc(tbl.name)}">
                    <rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="5" class="rd-table-frame" />
                    <rect x="${b.x}" y="${b.y}" width="${b.w}" height="${headerH}" rx="5" class="rd-table-header" />
                    <rect x="${b.x}" y="${b.y + headerH - 5}" width="${b.w}" height="5" class="rd-table-header" />
                    <text x="${b.x + b.w / 2}" y="${b.y + 22}" class="rd-table-title" text-anchor="middle">${this._esc(tbl.name)}</text>
                    ${rowsSvg}
                    <line x1="${splitX}" y1="${b.y + headerH}" x2="${splitX}" y2="${b.y + b.h}" class="rd-trow-sep" />
                    <rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="5" fill="none" class="rd-table-border" />
                </g>
            `;
        });

        // 3. Renderizar arcos FK -> PK con símbolos de obligatoriedad (| para NOT NULL, ○ para NULL)
        let arcsSvg = "";
        relations.forEach((rel, idx) => {
            const bSrc = boxByTable[rel.source_table];
            const bTgt = boxByTable[rel.target_table];
            if (!bSrc || !bTgt) return;

            const srcColIdx = Math.max(
                0,
                (bSrc.tbl.columns || []).findIndex((c) => c.name === rel.source_column)
            );
            const tgtColIdx = Math.max(
                0,
                (bTgt.tbl.columns || []).findIndex((c) => c.name === rel.target_column)
            );
            const srcCol = (bSrc.tbl.columns || [])[srcColIdx];
            const isMandatory = srcCol ? !srcCol.nullable : true;

            const y1 = bSrc.y + headerH + srcColIdx * rowH + rowH / 2;
            const y2 = bTgt.y + headerH + tgtColIdx * rowH + rowH / 2;

            let x1, x2, pathD, fkSide, pkSide;
            if (rel.source_table === rel.target_table) {
                // Bucle reflexivo por el lado derecho (igual que la primera imagen)
                x1 = bSrc.x + bSrc.w;
                x2 = bTgt.x + bTgt.w;
                const bulge = 64 + (idx % 3) * 18;
                pathD = `M ${x1} ${y1} C ${x1 + bulge} ${y1}, ${x2 + bulge} ${y2}, ${x2} ${y2}`;
                fkSide = 1;
                pkSide = 1;
            } else if (bSrc.x + bSrc.w < bTgt.x) {
                x1 = bSrc.x + bSrc.w;
                x2 = bTgt.x;
                const midX = (x1 + x2) / 2;
                pathD = `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`;
                fkSide = 1;
                pkSide = -1;
            } else if (bTgt.x + bTgt.w < bSrc.x) {
                x1 = bSrc.x;
                x2 = bTgt.x + bTgt.w;
                const midX = (x1 + x2) / 2;
                pathD = `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`;
                fkSide = -1;
                pkSide = 1;
            } else {
                // Misma columna vertical: salir ambos por el lado derecho
                x1 = bSrc.x + bSrc.w;
                x2 = bTgt.x + bTgt.w;
                const bulge = 56 + (idx % 3) * 20;
                const maxX = Math.max(x1, x2) + bulge;
                pathD = `M ${x1} ${y1} C ${maxX} ${y1}, ${maxX} ${y2}, ${x2} ${y2}`;
                fkSide = 1;
                pkSide = 1;
            }

            // Marcador en el extremo PK (siempre barra vertical de unicidad '1')
            const pkMarkX = x2 + pkSide * 10;
            const pkMarker = `<line x1="${pkMarkX}" y1="${y2 - 7}" x2="${pkMarkX}" y2="${y2 + 7}" class="rd-arc-marker" />`;

            // Marcador en el extremo FK (barra '|' si NOT NULL, círculo '○' si NULL)
            const fkMarkX = x1 + fkSide * 12;
            const fkMarker = isMandatory
                ? `<line x1="${fkMarkX}" y1="${y1 - 7}" x2="${fkMarkX}" y2="${y1 + 7}" class="rd-arc-marker" />`
                : `<circle cx="${fkMarkX}" cy="${y1}" r="5" class="rd-arc-opt-circle" />`;

            // Punto de anclaje en FK y flecha hacia PK
            const arrowTip = `<polygon points="${x2},${y2} ${x2 + pkSide * 7},${y2 - 4} ${x2 + pkSide * 7},${y2 + 4}" class="rd-arc-arrow" />`;

            arcsSvg += `
                <g class="rd-key-arc-group" data-arc-id="${this._esc(rel.id)}">
                    <path d="${pathD}" class="rd-key-arc" fill="none" />
                    ${fkMarker}
                    ${pkMarker}
                    ${arrowTip}
                </g>
            `;
        });

        this.svg.innerHTML = `<g id="reldiag-root">${tablesSvg}${arcsSvg}</g>`;
    }

    /* =========================================================================
       EXPORTACIÓN DE ALTA CALIDAD (SVG Y PNG)
       ========================================================================= */
    _buildExportableSvgString() {
        if (!this.svg) return null;
        const root = this.svg.querySelector("#reldiag-root");
        if (!root) return null;
        const bbox = root.getBBox();
        const pad = 36;
        const width = Math.max(400, Math.ceil(bbox.width + pad * 2));
        const height = Math.max(300, Math.ceil(bbox.height + pad * 2));
        const viewBox = `${Math.floor(bbox.x - pad)} ${Math.floor(bbox.y - pad)} ${width} ${height}`;

        const isLight = document.documentElement.getAttribute("data-theme") === "light";
        const bg = isLight ? "#f3f5f8" : "#0b0d12";
        const textPrimary = isLight ? "#0f172a" : "#edf1f7";
        const textSecondary = isLight ? "#475569" : "#a1aec4";
        const entityFill = isLight ? "#ffffff" : "#171b26";
        const entityStroke = isLight ? "#2563eb" : "#3b82f6";
        const diamondFill = isLight ? "#ecfdf5" : "#0f2922";
        const diamondStroke = isLight ? "#059669" : "#10b981";
        const ovalFill = isLight ? "#ffffff" : "#11141c";
        const ovalStroke = isLight ? "#64748b" : "#475569";
        const lineStroke = isLight ? "#059669" : "#10b981";
        const tableHeaderFill = isLight ? "#eff6ff" : "#1e293b";
        const tableRowFill = isLight ? "#ffffff" : "#11141c";
        const tableBorder = isLight ? "#cbd5e1" : "#2d364a";
        const flagColor = isLight ? "#2563eb" : "#3b82f6";

        const embeddedCss = `
            text { font-family: 'Segoe UI', system-ui, sans-serif; }
            .rd-attr-line { stroke: ${textSecondary}; stroke-width: 1.4; }
            .rd-attr-line.rd-dashed { stroke-dasharray: 5 4; }
            .rd-rel-line { stroke: ${lineStroke}; stroke-width: 2; }
            .rd-card-bg { fill: ${bg}; }
            .rd-card-label { fill: ${lineStroke}; font-size: 12px; font-weight: 700; }
            .rd-entity-rect { fill: ${entityFill}; stroke: ${entityStroke}; stroke-width: 2; }
            .rd-entity-rect-inner { fill: none; stroke: ${entityStroke}; stroke-width: 1.5; }
            .rd-entity-text { fill: ${textPrimary}; font-size: 13.5px; font-weight: 700; }
            .rd-diamond { fill: ${diamondFill}; stroke: ${diamondStroke}; stroke-width: 2; }
            .rd-diamond-inner { fill: none; stroke: ${diamondStroke}; stroke-width: 1.4; }
            .rd-diamond-text { fill: ${textPrimary}; font-size: 12.5px; font-weight: 700; }
            .rd-oval { fill: ${ovalFill}; stroke: ${ovalStroke}; stroke-width: 1.5; }
            .rd-oval-pk { stroke: ${entityStroke}; stroke-width: 2; }
            .rd-oval-derived { stroke-dasharray: 5 3; }
            .rd-oval-text { fill: ${textPrimary}; font-size: 12px; }
            .rd-text-pk { font-weight: 700; }
            .rd-underline-pk { stroke: ${textPrimary}; stroke-width: 1.5; }
            .rd-underline-uk { stroke: ${textSecondary}; stroke-width: 1.4; stroke-dasharray: 3 2; }
            .rd-table-frame { fill: ${tableRowFill}; }
            .rd-table-header { fill: ${tableHeaderFill}; }
            .rd-table-title { fill: ${textPrimary}; font-size: 13.5px; font-weight: 700; }
            .rd-table-border { stroke: ${tableBorder}; stroke-width: 2; }
            .rd-trow-bg { fill: ${tableRowFill}; }
            .rd-trow-sep { stroke: ${tableBorder}; stroke-width: 1; opacity: 0.6; }
            .rd-tcol-name { fill: ${textPrimary}; font-size: 12px; font-family: Consolas, monospace; }
            .rd-tcol-flags { fill: ${flagColor}; font-size: 11.5px; font-weight: 700; font-family: Consolas, monospace; }
            .rd-key-arc { stroke: ${lineStroke}; stroke-width: 2; }
            .rd-arc-marker { stroke: ${lineStroke}; stroke-width: 2.2; }
            .rd-arc-opt-circle { fill: ${bg}; stroke: ${lineStroke}; stroke-width: 2; }
            .rd-arc-arrow { fill: ${lineStroke}; }
        `;

        const innerContent = root.innerHTML;
        const svgStr = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="${viewBox}">
            <style>${embeddedCss}</style>
            <rect x="${Math.floor(bbox.x - pad)}" y="${Math.floor(bbox.y - pad)}" width="${width}" height="${height}" fill="${bg}" />
            <g>${innerContent}</g>
        </svg>`;
        return { svgStr, width, height };
    }

    exportSVG() {
        const built = this._buildExportableSvgString();
        if (!built) {
            this.onNotify("No hay diagrama visible para exportar.");
            return;
        }
        const db = (this.contract && this.contract.db_name) || "diagrama";
        const suffix = this.submode === "chen" ? "conceptual_chen" : "paso_a_tablas";
        const filename = `${db}_${suffix}.svg`;
        const blob = new Blob([built.svgStr], { type: "image/svg+xml;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
        this.onNotify(`Diagrama exportado como ${filename}`);
    }

    exportPNG() {
        const built = this._buildExportableSvgString();
        if (!built) {
            this.onNotify("No hay diagrama visible para exportar.");
            return;
        }
        const db = (this.contract && this.contract.db_name) || "diagrama";
        const suffix = this.submode === "chen" ? "conceptual_chen" : "paso_a_tablas";
        const filename = `${db}_${suffix}.png`;

        const scale = 2; // Alta resolución 2x
        const canvas = document.createElement("canvas");
        canvas.width = built.width * scale;
        canvas.height = built.height * scale;
        const ctx = canvas.getContext("2d");

        const img = new Image();
        const svgBlob = new Blob([built.svgStr], { type: "image/svg+xml;charset=utf-8" });
        const url = URL.createObjectURL(svgBlob);

        img.onload = () => {
            ctx.scale(scale, scale);
            ctx.drawImage(img, 0, 0);
            URL.revokeObjectURL(url);
            canvas.toBlob((pngBlob) => {
                if (!pngBlob) return;
                const pngUrl = URL.createObjectURL(pngBlob);
                const a = document.createElement("a");
                a.href = pngUrl;
                a.download = filename;
                a.click();
                URL.revokeObjectURL(pngUrl);
                this.onNotify(`Imagen PNG de alta resolución exportada: ${filename}`);
            }, "image/png");
        };
        img.onerror = () => {
            URL.revokeObjectURL(url);
            this.onNotify("No se pudo rasterizar a PNG; prueba con Exportar SVG.");
        };
        img.src = url;
    }

    _esc(str) {
        return String(str === null || str === undefined ? "" : str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }
}

window.RelationalDiagramController = RelationalDiagramController;
