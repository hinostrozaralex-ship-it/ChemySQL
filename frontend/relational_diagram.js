/**
 * Motor Interactivo de Diagrama Relacional para ChemySQL.
 * Soporta dos notaciones académicas sincronizadas en tiempo real con el Contrato Maestro JSON:
 *   1. Conceptual (Notación de Chen): Entidades (rectángulos simples y dobles para débiles),
 *      Relaciones binarias, reflexivas y N-arias/ternarias (rombos con verbo editable y cardinalidades),
 *      Atributos distribuidos con algoritmo anti-colisión angular (óvalos con subrayado PK, discontinuo UK,
 *      discriminador de entidad débil y borde punteado para derivados/calculados).
 *   2. Paso a Tablas (Claves): Tablas con siglas (pk, nn, uk, fk, fx) y modo opcional de tipos físicos
 *      y políticas referenciales, con arcos interactivos FK -> PK y marcadores de obligatoriedad (| / ○).
 * Incluye rótulo del esquema en el lienzo/exportación, persistencia en diagram_layout y exportación SVG / PNG.
 */

class RelationalDiagramController {
    constructor(options = {}) {
        this.viewport = document.getElementById("reldiag-viewport");
        this.svg = document.getElementById("reldiag-svg");
        this.zoomLabel = document.getElementById("reldiag-zoom-label");
        this.legendEl = document.getElementById("reldiag-legend");

        this.onSelectElement = options.onSelectElement || (() => {});
        this.onNotify = options.onNotify || (() => {});
        this.onLayoutChanged = options.onLayoutChanged || (() => {});
        this.getLang = options.getLang || (() => document.documentElement.lang || "es");

        this.contract = null;
        this.submode = "chen"; // 'chen' | 'tables'
        this.showAttributes = true;
        this.showWeakFkAttrs = false;
        this.showPhysicalDetails = false;
        this.zoom = 1.0;
        this.panX = 0;
        this.panY = 0;

        this.positions = { chen: {}, tables: {} };
        this.customVerbs = {};
        this.lastDbKey = "";

        this._dragState = null;
        this._bindGlobalInteractions();
    }

    _isEn() {
        return this.getLang() === "en";
    }

    _syncLayoutToContract() {
        if (!this.contract) return;
        this.contract.diagram_layout = {
            positions: {
                chen: Object.assign({}, this.positions.chen),
                tables: Object.assign({}, this.positions.tables),
            },
            customVerbs: Object.assign({}, this.customVerbs),
            showWeakFkAttrs: this.showWeakFkAttrs,
            showPhysicalDetails: this.showPhysicalDetails,
        };
        this.onLayoutChanged(this.contract);
    }

    _bindGlobalInteractions() {
        if (!this.viewport || !this.svg) return;

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
                    x: Math.round(this._dragState.origX + dx),
                    y: Math.round(this._dragState.origY + dy),
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
                if (drag.type === "node") {
                    if (drag.moved) {
                        this._syncLayoutToContract();
                    } else if (this.contract) {
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
            }
        });

        this.svg.addEventListener("dblclick", (e) => {
            const relNode = e.target.closest("[data-rel-verb-id]");
            if (!relNode) return;
            const relId = relNode.getAttribute("data-rel-verb-id");
            const currentVerb = relNode.getAttribute("data-rel-verb") || (this._isEn() ? "Relates" : "Relaciona");
            const promptMsg = this._isEn()
                ? "Relationship verb or label inside diamond:"
                : "Verbo o nombre de la relación en el rombo:";
            const newVerb = window.prompt(promptMsg, currentVerb);
            if (newVerb && newVerb.trim()) {
                this.customVerbs[relId] = newVerb.trim();
                this._syncLayoutToContract();
                this._renderCurrent();
            }
        });

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

    toggleWeakFkAttrs() {
        this.showWeakFkAttrs = !this.showWeakFkAttrs;
        this.positions.chen = {};
        this._syncLayoutToContract();
        this._renderCurrent();
        return this.showWeakFkAttrs;
    }

    togglePhysicalDetails() {
        this.showPhysicalDetails = !this.showPhysicalDetails;
        this._syncLayoutToContract();
        this._renderCurrent();
        this.fitToViewport();
        return this.showPhysicalDetails;
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
        this._syncLayoutToContract();
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
        const saved = contract.diagram_layout || {};
        if (dbKey !== this.lastDbKey) {
            this.positions = {
                chen: Object.assign({}, (saved.positions && saved.positions.chen) || {}),
                tables: Object.assign({}, (saved.positions && saved.positions.tables) || {}),
            };
            this.customVerbs = Object.assign({}, saved.customVerbs || {});
            if (typeof saved.showWeakFkAttrs === "boolean") {
                this.showWeakFkAttrs = saved.showWeakFkAttrs;
            }
            if (typeof saved.showPhysicalDetails === "boolean") {
                this.showPhysicalDetails = saved.showPhysicalDetails;
            }
            this.lastDbKey = dbKey;
        } else if (saved.positions) {
            if (Object.keys(this.positions.chen).length === 0 && saved.positions.chen) {
                this.positions.chen = Object.assign({}, saved.positions.chen);
            }
            if (Object.keys(this.positions.tables).length === 0 && saved.positions.tables) {
                this.positions.tables = Object.assign({}, saved.positions.tables);
            }
        }

        this._updateLegend();
        this._renderCurrent();
    }

    _updateLegend() {
        if (!this.legendEl) return;
        const isEn = this._isEn();
        if (this.submode === "chen") {
            this.legendEl.innerHTML = isEn
                ? `
                <span class="legend-chip"><i class="rd-leg-rect"></i> Entity</span>
                <span class="legend-chip"><i class="rd-leg-diamond"></i> Relation (dbl-click: edit verb)</span>
                <span class="legend-chip"><i class="rd-leg-oval-pk"></i> PK (underlined)</span>
                <span class="legend-chip"><i class="rd-leg-oval-disc"></i> Weak Discriminator</span>
                <span class="legend-chip"><i class="rd-leg-oval-uk"></i> UK (dashed)</span>
                <span class="legend-chip"><i class="rd-leg-oval-fx"></i> Derived (computed)</span>
                `
                : `
                <span class="legend-chip"><i class="rd-leg-rect"></i> Entidad</span>
                <span class="legend-chip"><i class="rd-leg-diamond"></i> Relación (doble clic: editar verbo)</span>
                <span class="legend-chip"><i class="rd-leg-oval-pk"></i> PK (subrayado)</span>
                <span class="legend-chip"><i class="rd-leg-oval-disc"></i> Discriminador débil</span>
                <span class="legend-chip"><i class="rd-leg-oval-uk"></i> UK (discontinuo)</span>
                <span class="legend-chip"><i class="rd-leg-oval-fx"></i> Derivado (calculado)</span>
                `;
        } else {
            this.legendEl.innerHTML = isEn
                ? `
                <span class="legend-chip"><i class="badge-pk">pk</i> Primary</span>
                <span class="legend-chip"><i class="badge-fk">fk</i> Foreign</span>
                <span class="legend-chip"><i class="badge-uq">uk</i> Unique</span>
                <span class="legend-chip"><i class="badge-nm">fx</i> Computed</span>
                <span class="legend-chip"><i class="rd-leg-nn">nn</i> Mandatory (|)</span>
                <span class="legend-chip"><i class="rd-leg-opt">○</i> Optional (NULL)</span>
                `
                : `
                <span class="legend-chip"><i class="badge-pk">pk</i> Primaria</span>
                <span class="legend-chip"><i class="badge-fk">fk</i> Foránea</span>
                <span class="legend-chip"><i class="badge-uq">uk</i> Única</span>
                <span class="legend-chip"><i class="badge-nm">fx</i> Calculada</span>
                <span class="legend-chip"><i class="rd-leg-nn">nn</i> Obligatoria (|)</span>
                <span class="legend-chip"><i class="rd-leg-opt">○</i> Opcional (NULL)</span>
                `;
        }
    }

    _renderCurrent() {
        if (!this.svg || !this.contract) return;
        const tables = this.contract.tables || [];
        if (tables.length === 0) {
            const msg = this._isEn()
                ? "No tables in the current schema."
                : "No hay tablas en el esquema actual.";
            this.svg.innerHTML = `<g id="reldiag-root"><text x="60" y="80" class="rd-empty-text">${this._esc(msg)}</text></g>`;
            return;
        }
        if (this.submode === "chen") {
            this._renderChenDiagram();
        } else {
            this._renderTableMappingDiagram();
        }
        this._applyTransform();
    }

    _buildDiagramBanner(anchorX, anchorY) {
        if (!this.contract) return "";
        const isEn = this._isEn();
        const rawTitle =
            (this.contract.ddl_identifier || "").trim() ||
            (this.contract.title || "").trim() ||
            this.contract.db_name ||
            "ChemySQL";
        const subtitle =
            this.submode === "chen"
                ? isEn
                    ? "Conceptual E/R Model · Chen Notation"
                    : "Modelo Conceptual E/R · Notación de Chen"
                : isEn
                ? "Logical Relational Model · Table & Key Mapping"
                : "Modelo Lógico Relacional · Paso a Tablas (Claves)";
        const boxW = Math.max(280, Math.max(rawTitle.length * 9.5 + 36, subtitle.length * 6.8 + 34));
        const bx = Math.round(anchorX);
        const by = Math.round(anchorY - 68);
        return `
            <g class="rd-schema-banner">
                <rect x="${bx}" y="${by}" width="${Math.ceil(boxW)}" height="48" rx="6" class="rd-banner-box" />
                <text x="${bx + 14}" y="${by + 21}" class="rd-banner-title">${this._esc(rawTitle)}</text>
                <text x="${bx + 14}" y="${by + 38}" class="rd-banner-subtitle">${this._esc(subtitle)}</text>
            </g>
        `;
    }

    static _angularDistance(a, b) {
        let d = Math.abs(a - b) % (Math.PI * 2);
        if (d > Math.PI) d = Math.PI * 2 - d;
        return d;
    }

    _computeCollisionFreeOvalAngles(count, blockedAngles) {
        if (count <= 0) return [];
        const TOTAL_SLOTS = 72;
        const candidates = [];
        // Ordenar candidatos dando preferencia a los sectores superior e inferior (estética Chen clásica)
        for (let s = 0; s < TOTAL_SLOTS; s++) {
            const ang = -Math.PI + (s * 2 * Math.PI) / TOTAL_SLOTS;
            candidates.push(ang);
        }

        const filterByMargin = (minRad) =>
            candidates.filter((ang) =>
                blockedAngles.every((blk) => RelationalDiagramController._angularDistance(ang, blk) >= minRad)
            );

        let valid = filterByMargin(0.50);
        if (valid.length < count) valid = filterByMargin(0.34);
        if (valid.length < count) valid = filterByMargin(0.18);
        if (valid.length < count) valid = candidates;

        // Selección greedy maximizando distancia angular mutua y cercanía a polos verticales (-PI/2 y +PI/2)
        const chosen = [];
        const verticalScore = (ang) => Math.abs(Math.sin(ang)); // 1 en arriba/abajo, 0 en izq/der

        // Primer ángulo: el candidato válido más cercano al polo superior (-PI/2)
        let firstIdx = 0;
        let bestFirst = -Infinity;
        valid.forEach((ang, idx) => {
            const score = -RelationalDiagramController._angularDistance(ang, -Math.PI / 2);
            if (score > bestFirst) {
                bestFirst = score;
                firstIdx = idx;
            }
        });
        chosen.push(valid[firstIdx]);

        while (chosen.length < count) {
            let bestAng = valid[0];
            let bestScore = -Infinity;
            for (const cand of valid) {
                let minDistToChosen = Infinity;
                for (const ch of chosen) {
                    const d = RelationalDiagramController._angularDistance(cand, ch);
                    if (d < minDistToChosen) minDistToChosen = d;
                }
                // Priorizar máxima separación mutua + ligero sesgo estético hacia arcos superior/inferior
                const combined = minDistToChosen + verticalScore(cand) * 0.14;
                if (combined > bestScore) {
                    bestScore = combined;
                    bestAng = cand;
                }
            }
            chosen.push(bestAng);
        }

        return chosen.sort((a, b) => a - b);
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
        };
        if (known[pair]) return known[pair];
        if (srcTable.toLowerCase() === tgtTable.toLowerCase()) {
            return this._isEn() ? "Relates to" : "Se asocia con";
        }
        if (rel.cardinality === "N:M") {
            return this._isEn() ? "Participates in" : "Participa en";
        }
        return this._isEn() ? "Has" : "Tiene";
    }

    _renderChenDiagram() {
        const tables = this.contract.tables || [];
        const relations = this.contract.relations || [];
        const posMap = this.positions.chen;

        const assocTables = new Set(tables.filter((t) => t.is_associative).map((t) => t.name));
        const entityTables = tables.filter((t) => !assocTables.has(t.name));

        const colsPerRow = entityTables.length <= 2 ? 2 : entityTables.length <= 4 ? 2 : 3;
        const spacingX = this.showAttributes ? 500 : 340;
        const spacingY = this.showAttributes ? 410 : 250;

        let minEntX = Infinity;
        let minEntY = Infinity;

        entityTables.forEach((tbl, idx) => {
            const key = `ent:${tbl.name}`;
            if (!posMap[key]) {
                const col = idx % colsPerRow;
                const row = Math.floor(idx / colsPerRow);
                posMap[key] = {
                    x: 220 + col * spacingX,
                    y: 210 + row * spacingY,
                };
            }
            if (posMap[key].x < minEntX) minEntX = posMap[key].x;
            if (posMap[key].y < minEntY) minEntY = posMap[key].y;
        });

        // 2. Construir lista de rombos (1:N, 1:1, reflexivas, N:M binarias y N-arias / ternarias >= 3 FKs)
        const chenRelations = [];
        const handledAssoc = new Set();

        tables.forEach((tbl) => {
            if (!assocTables.has(tbl.name)) return;
            const assocRels = relations.filter((r) => r.source_table === tbl.name);
            if (assocRels.length >= 2) {
                const extraAttrs = (tbl.columns || []).filter((c) => !c.is_pk && !c.is_fk);
                const participants = assocRels.map((r) => ({
                    table: r.target_table,
                    card: "(0,N)",
                    fkCol: r.source_column,
                }));
                const isNary = participants.length >= 3;
                const isReflexive = !isNary && participants[0].table === participants[1].table;
                const relKey = `assoc_${tbl.name}`;
                chenRelations.push({
                    id: relKey,
                    isNary,
                    participants,
                    left: participants[0].table,
                    right: participants[1].table,
                    verb: this.customVerbs[relKey] || tbl.name.replace(/_/g, " "),
                    leftCard: "(0,N)",
                    rightCard: "(0,N)",
                    isDouble: true,
                    isReflexive,
                    extraAttrs,
                });
                handledAssoc.add(tbl.name);
            }
        });

        relations.forEach((rel) => {
            if (handledAssoc.has(rel.source_table) || assocTables.has(rel.source_table)) return;
            const srcTbl = tables.find((t) => t.name === rel.source_table);
            const fkCol = srcTbl ? (srcTbl.columns || []).find((c) => c.name === rel.source_column) : null;
            const isMandatory = fkCol ? !fkCol.nullable : true;
            const srcPkCols = srcTbl ? (srcTbl.columns || []).filter((c) => c.is_pk) : [];
            const isWeakRel = Boolean(fkCol && fkCol.is_pk && srcPkCols.length > 1);
            const minSrc = isMandatory ? "1" : "0";
            const maxSrc = rel.cardinality === "1:1" ? "1" : "N";
            const leftCard = rel.cardinality === "1:1" ? `(${minSrc},1)` : `(0,${maxSrc})`;
            const rightCard = `(${minSrc},1)`;
            chenRelations.push({
                id: rel.id,
                isNary: false,
                participants: [
                    { table: rel.target_table, card: leftCard },
                    { table: rel.source_table, card: rightCard },
                ],
                left: rel.target_table,
                right: rel.source_table,
                verb: this._inferVerb(rel.source_table, rel.target_table, rel),
                leftCard,
                rightCard,
                isDouble: isWeakRel,
                isReflexive: rel.source_table === rel.target_table,
                extraAttrs: [],
            });
        });

        // Posicionar cada rombo (centroide para N-arias, punto medio para binarias, lateral para reflexivas)
        chenRelations.forEach((cr, idx) => {
            const key = `rel:${cr.id}`;
            if (!posMap[key]) {
                if (cr.isNary) {
                    let sumX = 0;
                    let sumY = 0;
                    let validN = 0;
                    cr.participants.forEach((pt) => {
                        const pe = posMap[`ent:${pt.table}`];
                        if (pe) {
                            sumX += pe.x;
                            sumY += pe.y;
                            validN += 1;
                        }
                    });
                    posMap[key] = {
                        x: validN > 0 ? Math.round(sumX / validN) : 380,
                        y: validN > 0 ? Math.round(sumY / validN) : 300,
                    };
                } else {
                    const pL = posMap[`ent:${cr.left}`] || { x: 220, y: 210 };
                    const pR = posMap[`ent:${cr.right}`] || { x: 520, y: 210 };
                    if (cr.isReflexive) {
                        posMap[key] = { x: pL.x + 195, y: pL.y };
                    } else {
                        const dx = pR.x - pL.x;
                        const dy = pR.y - pL.y;
                        // Desplazar perpendicularmente solo si hay múltiples relaciones entre el mismo par
                        const samePairCount = chenRelations.filter(
                            (o) =>
                                !o.isNary &&
                                ((o.left === cr.left && o.right === cr.right) ||
                                    (o.left === cr.right && o.right === cr.left))
                        ).length;
                        const offset = samePairCount > 1 ? (idx % 2 === 0 ? -28 : 28) : 0;
                        const norm = Math.hypot(dx, dy) || 1;
                        posMap[key] = {
                            x: Math.round((pL.x + pR.x) / 2 + (-dy / norm) * offset),
                            y: Math.round((pL.y + pR.y) / 2 + (dx / norm) * offset),
                        };
                    }
                }
            }
        });

        // 3. Calcular ángulos ocupados por líneas de relación en cada entidad para evitar colisiones de óvalos
        const blockedByEntity = {};
        entityTables.forEach((tbl) => {
            blockedByEntity[tbl.name] = [];
        });

        chenRelations.forEach((cr) => {
            const pRel = posMap[`rel:${cr.id}`];
            if (!pRel) return;
            if (cr.isReflexive) {
                if (blockedByEntity[cr.left]) {
                    blockedByEntity[cr.left].push(-0.42, 0.0, 0.42);
                }
                return;
            }
            cr.participants.forEach((pt) => {
                const pEnt = posMap[`ent:${pt.table}`];
                if (pEnt && blockedByEntity[pt.table]) {
                    const ang = Math.atan2(pRel.y - pEnt.y, pRel.x - pEnt.x);
                    blockedByEntity[pt.table].push(ang);
                }
            });
        });

        // 4. Posicionar óvalos de atributos alrededor de cada entidad sin pisar conectores
        const attrNodes = [];
        if (this.showAttributes) {
            entityTables.forEach((tbl) => {
                const entPos = posMap[`ent:${tbl.name}`];
                const pkCols = (tbl.columns || []).filter((c) => c.is_pk);
                const isWeakEntity = pkCols.length > 1 && pkCols.some((c) => c.is_fk);
                const entW = Math.max(138, tbl.name.length * 9.2 + 34);

                const visibleCols = (tbl.columns || []).filter((c) => {
                    if (!c.is_fk) return true;
                    if (c.is_pk && isWeakEntity) {
                        return this.showWeakFkAttrs;
                    }
                    return c.is_pk;
                });

                const angles = this._computeCollisionFreeOvalAngles(
                    visibleCols.length,
                    blockedByEntity[tbl.name] || []
                );
                const rxOrbit = Math.max(154, entW / 2 + 86);
                const ryOrbit = 114;

                visibleCols.forEach((col, i) => {
                    const aKey = `attr:${tbl.name}.${col.name}`;
                    if (!posMap[aKey]) {
                        const ang = angles[i] !== undefined ? angles[i] : -Math.PI / 2;
                        posMap[aKey] = {
                            x: Math.round(entPos.x + Math.cos(ang) * rxOrbit),
                            y: Math.round(entPos.y + Math.sin(ang) * ryOrbit),
                        };
                    }
                    const isWeakDiscriminator = Boolean(
                        isWeakEntity && col.is_pk && !col.is_fk && !this.showWeakFkAttrs
                    );
                    attrNodes.push({
                        key: aKey,
                        table: tbl.name,
                        col,
                        isWeakDiscriminator,
                        pos: posMap[aKey],
                        entPos,
                    });
                });
            });
        }

        // 5. Ensamblar capas SVG: banner -> líneas -> rombos -> entidades -> óvalos
        let linesSvg = "";
        let shapesSvg = "";

        attrNodes.forEach((a) => {
            const isDerived = Boolean(a.col.computed_expression);
            linesSvg += `<line x1="${a.entPos.x}" y1="${a.entPos.y}" x2="${a.pos.x}" y2="${a.pos.y}" class="rd-attr-line ${isDerived ? "rd-dashed" : ""}" />`;
        });

        chenRelations.forEach((cr) => {
            const pRel = posMap[`rel:${cr.id}`];
            if (!pRel) return;
            const relBlockedAngles = [];

            if (cr.isReflexive) {
                const pL = posMap[`ent:${cr.left}`];
                if (!pL) return;
                const dTop = `M ${pL.x + 68} ${pL.y - 10} C ${pL.x + 115} ${pL.y - 70}, ${pRel.x - 45} ${pRel.y - 70}, ${pRel.x - 56} ${pRel.y - 4}`;
                const dBot = `M ${pL.x + 68} ${pL.y + 10} C ${pL.x + 115} ${pL.y + 70}, ${pRel.x - 45} ${pRel.y + 70}, ${pRel.x + 4 - 60} ${pRel.y + 4}`;
                linesSvg += `<path d="${dTop}" class="rd-rel-line" fill="none" />`;
                linesSvg += `<path d="${dBot}" class="rd-rel-line" fill="none" />`;
                const r1 = this._isEn() ? "Role 1" : "Rol 1";
                const r2 = this._isEn() ? "Role 2" : "Rol 2";
                linesSvg += `<text x="${(pL.x + pRel.x) / 2}" y="${pL.y - 54}" class="rd-card-label" text-anchor="middle">${this._esc(cr.leftCard)} · ${r1}</text>`;
                linesSvg += `<text x="${(pL.x + pRel.x) / 2}" y="${pL.y + 66}" class="rd-card-label" text-anchor="middle">${this._esc(cr.rightCard)} · ${r2}</text>`;
                relBlockedAngles.push(Math.PI);
            } else {
                cr.participants.forEach((pt) => {
                    const pEnt = posMap[`ent:${pt.table}`];
                    if (!pEnt) return;
                    linesSvg += `<line x1="${pEnt.x}" y1="${pEnt.y}" x2="${pRel.x}" y2="${pRel.y}" class="rd-rel-line" />`;
                    relBlockedAngles.push(Math.atan2(pEnt.y - pRel.y, pEnt.x - pRel.x));

                    const mx = pEnt.x + (pRel.x - pEnt.x) * 0.46;
                    const my = pEnt.y + (pRel.y - pEnt.y) * 0.46;
                    linesSvg += `<rect x="${mx - 23}" y="${my - 11}" width="46" height="17" rx="4" class="rd-card-bg" />`;
                    linesSvg += `<text x="${mx}" y="${my + 2}" class="rd-card-label" text-anchor="middle">${this._esc(pt.card)}</text>`;
                });
            }

            if (this.showAttributes && cr.extraAttrs.length > 0) {
                const relAngles = this._computeCollisionFreeOvalAngles(
                    cr.extraAttrs.length,
                    relBlockedAngles
                );
                cr.extraAttrs.forEach((col, ci) => {
                    const oaKey = `relattr:${cr.id}.${col.name}`;
                    if (!posMap[oaKey]) {
                        const ang = relAngles[ci] !== undefined ? relAngles[ci] : -Math.PI / 2;
                        posMap[oaKey] = {
                            x: Math.round(pRel.x + Math.cos(ang) * 124),
                            y: Math.round(pRel.y + Math.sin(ang) * 92),
                        };
                    }
                    const op = posMap[oaKey];
                    linesSvg += `<line x1="${pRel.x}" y1="${pRel.y}" x2="${op.x}" y2="${op.y}" class="rd-attr-line" />`;
                    const rxOval = Math.max(44, col.name.length * 4.2 + 16);
                    shapesSvg += `
                        <g class="rd-draggable rd-oval-node" data-drag-id="${this._esc(oaKey)}">
                            <ellipse cx="${op.x}" cy="${op.y}" rx="${rxOval}" ry="17" class="rd-oval" />
                            <text x="${op.x}" y="${op.y + 4}" class="rd-oval-text" text-anchor="middle">${this._esc(col.name)}</text>
                        </g>
                    `;
                });
            }
        });

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

        let minBoundX = isFinite(minEntX) ? minEntX - 90 : 80;
        let minBoundY = isFinite(minEntY) ? minEntY - 40 : 120;

        attrNodes.forEach((a) => {
            const isPk = Boolean(a.col.is_pk);
            const isDisc = Boolean(a.isWeakDiscriminator);
            const isUk = Boolean(a.col.is_unique && !isPk);
            const isDerived = Boolean(a.col.computed_expression);
            const rx = Math.max(46, a.col.name.length * 4.2 + 18);
            const ry = 17;
            if (a.pos.x - rx < minBoundX) minBoundX = a.pos.x - rx;
            if (a.pos.y - ry < minBoundY) minBoundY = a.pos.y - ry;
            const textW = Math.min(rx * 1.45, a.col.name.length * 7.2);
            let underlineSvg = "";
            if (isDisc) {
                underlineSvg = `<line x1="${a.pos.x - textW / 2}" y1="${a.pos.y + 8}" x2="${a.pos.x + textW / 2}" y2="${a.pos.y + 8}" class="rd-underline-disc" />`;
            } else if (isPk) {
                underlineSvg = `<line x1="${a.pos.x - textW / 2}" y1="${a.pos.y + 8}" x2="${a.pos.x + textW / 2}" y2="${a.pos.y + 8}" class="rd-underline-pk" />`;
            } else if (isUk) {
                underlineSvg = `<line x1="${a.pos.x - textW / 2}" y1="${a.pos.y + 8}" x2="${a.pos.x + textW / 2}" y2="${a.pos.y + 8}" class="rd-underline-uk" />`;
            }
            shapesSvg += `
                <g class="rd-draggable rd-oval-node" data-drag-id="${this._esc(a.key)}">
                    <ellipse cx="${a.pos.x}" cy="${a.pos.y}" rx="${rx}" ry="${ry}" class="rd-oval ${isPk ? "rd-oval-pk" : ""} ${isDerived ? "rd-oval-derived" : ""}" />
                    <text x="${a.pos.x}" y="${a.pos.y + 4}" class="rd-oval-text ${isPk ? "rd-text-pk" : ""}" text-anchor="middle">${this._esc(a.col.name)}</text>
                    ${underlineSvg}
                </g>
            `;
        });

        const bannerSvg = this._buildDiagramBanner(minBoundX, minBoundY);
        this.svg.innerHTML = `<g id="reldiag-root">${bannerSvg}${linesSvg}${shapesSvg}</g>`;
    }

    /* =========================================================================
       MODO 2: PASO A TABLAS (NOTACIÓN DE CLAVES pk, nn, uk, fk, fx + ARCOS | / ○)
       ========================================================================= */
    _formatShortType(col) {
        const dt = String(col.data_type || "VARCHAR").toUpperCase();
        if ((dt === "VARCHAR" || dt === "CHAR") && col.length) {
            return `${dt}(${col.length})`;
        }
        return dt;
    }

    _renderTableMappingDiagram() {
        const tables = this.contract.tables || [];
        const relations = this.contract.relations || [];
        const posMap = this.positions.tables;
        const showPhys = this.showPhysicalDetails;

        const tblW = showPhys ? 356 : 264;
        const headerH = 34;
        const rowH = 26;
        const colsPerRow = tables.length <= 2 ? 2 : tables.length <= 4 ? 2 : 3;
        const gapX = showPhys ? 450 : 360;
        const gapY = 310;

        let minBoxX = Infinity;
        let minBoxY = Infinity;

        const boxByTable = {};
        tables.forEach((tbl, idx) => {
            const key = `tbl:${tbl.name}`;
            if (!posMap[key]) {
                const c = idx % colsPerRow;
                const r = Math.floor(idx / colsPerRow);
                posMap[key] = {
                    x: 70 + c * gapX,
                    y: 96 + r * gapY,
                };
            }
            const p = posMap[key];
            if (p.x < minBoxX) minBoxX = p.x;
            if (p.y < minBoxY) minBoxY = p.y;
            const h = headerH + Math.max(1, (tbl.columns || []).length) * rowH;
            boxByTable[tbl.name] = { x: p.x, y: p.y, w: tblW, h, tbl };
        });

        const colRelMap = {};
        relations.forEach((rel) => {
            const kSrc = `${rel.source_table}.${rel.source_column}`;
            const kTgt = `${rel.target_table}.${rel.target_column}`;
            colRelMap[kSrc] = rel.id;
            if (!colRelMap[kTgt]) colRelMap[kTgt] = rel.id;
        });

        let tablesSvg = "";
        tables.forEach((tbl) => {
            const b = boxByTable[tbl.name];
            const cols = tbl.columns || [];
            const splitFlagsX = b.x + b.w - 84;
            const splitTypeX = showPhys ? splitFlagsX - 96 : splitFlagsX;

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
                const shortType = showPhys ? this._formatShortType(col) : "";

                rowsSvg += `
                    <g class="rd-trow ${rowClass}" ${refId ? `data-key-ref="${this._esc(refId)}"` : ""}>
                        <rect x="${b.x}" y="${ry}" width="${b.w}" height="${rowH}" class="rd-trow-bg" />
                        <line x1="${b.x}" y1="${ry}" x2="${b.x + b.w}" y2="${ry}" class="rd-trow-sep" />
                        <text x="${b.x + 10}" y="${ry + 17}" class="rd-tcol-name ${col.is_pk ? "rd-text-pk" : ""}">${this._esc(col.name)}</text>
                        ${showPhys ? `<text x="${splitTypeX + 7}" y="${ry + 17}" class="rd-tcol-type">${this._esc(shortType)}</text>` : ""}
                        <text x="${splitFlagsX + 8}" y="${ry + 17}" class="rd-tcol-flags">${this._esc(flagsText)}</text>
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
                    ${showPhys ? `<line x1="${splitTypeX}" y1="${b.y + headerH}" x2="${splitTypeX}" y2="${b.y + b.h}" class="rd-trow-sep" />` : ""}
                    <line x1="${splitFlagsX}" y1="${b.y + headerH}" x2="${splitFlagsX}" y2="${b.y + b.h}" class="rd-trow-sep" />
                    <rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="5" fill="none" class="rd-table-border" />
                </g>
            `;
        });

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

            let x1, x2, pathD, fkSide, pkSide, labelX, labelY;
            if (rel.source_table === rel.target_table) {
                x1 = bSrc.x + bSrc.w;
                x2 = bTgt.x + bTgt.w;
                const bulge = 64 + (idx % 3) * 18;
                pathD = `M ${x1} ${y1} C ${x1 + bulge} ${y1}, ${x2 + bulge} ${y2}, ${x2} ${y2}`;
                fkSide = 1;
                pkSide = 1;
                labelX = x1 + bulge * 0.75;
                labelY = (y1 + y2) / 2;
            } else if (bSrc.x + bSrc.w < bTgt.x) {
                x1 = bSrc.x + bSrc.w;
                x2 = bTgt.x;
                const midX = (x1 + x2) / 2;
                pathD = `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`;
                fkSide = 1;
                pkSide = -1;
                labelX = midX;
                labelY = (y1 + y2) / 2;
            } else if (bTgt.x + bTgt.w < bSrc.x) {
                x1 = bSrc.x;
                x2 = bTgt.x + bTgt.w;
                const midX = (x1 + x2) / 2;
                pathD = `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`;
                fkSide = -1;
                pkSide = 1;
                labelX = midX;
                labelY = (y1 + y2) / 2;
            } else {
                x1 = bSrc.x + bSrc.w;
                x2 = bTgt.x + bTgt.w;
                const bulge = 56 + (idx % 3) * 20;
                const maxX = Math.max(x1, x2) + bulge;
                pathD = `M ${x1} ${y1} C ${maxX} ${y1}, ${maxX} ${y2}, ${x2} ${y2}`;
                fkSide = 1;
                pkSide = 1;
                labelX = maxX - 10;
                labelY = (y1 + y2) / 2;
            }

            const pkMarkX = x2 + pkSide * 10;
            const pkMarker = `<line x1="${pkMarkX}" y1="${y2 - 7}" x2="${pkMarkX}" y2="${y2 + 7}" class="rd-arc-marker" />`;

            const fkMarkX = x1 + fkSide * 12;
            const fkMarker = isMandatory
                ? `<line x1="${fkMarkX}" y1="${y1 - 7}" x2="${fkMarkX}" y2="${y1 + 7}" class="rd-arc-marker" />`
                : `<circle cx="${fkMarkX}" cy="${y1}" r="5" class="rd-arc-opt-circle" />`;

            const arrowTip = `<polygon points="${x2},${y2} ${x2 + pkSide * 7},${y2 - 4} ${x2 + pkSide * 7},${y2 + 4}" class="rd-arc-arrow" />`;

            let policyBadge = "";
            if (showPhys) {
                const polText = `DEL:${rel.on_delete || "RESTRICT"}`;
                const pw = polText.length * 6.4 + 12;
                policyBadge = `
                    <rect x="${labelX - pw / 2}" y="${labelY - 9}" width="${pw}" height="17" rx="4" class="rd-card-bg" />
                    <text x="${labelX}" y="${labelY + 3}" class="rd-policy-label" text-anchor="middle">${this._esc(polText)}</text>
                `;
            }

            arcsSvg += `
                <g class="rd-key-arc-group" data-arc-id="${this._esc(rel.id)}">
                    <path d="${pathD}" class="rd-key-arc" fill="none" />
                    ${fkMarker}
                    ${pkMarker}
                    ${arrowTip}
                    ${policyBadge}
                </g>
            `;
        });

        const bannerSvg = this._buildDiagramBanner(
            isFinite(minBoxX) ? minBoxX : 70,
            isFinite(minBoxY) ? minBoxY : 96
        );
        this.svg.innerHTML = `<g id="reldiag-root">${bannerSvg}${tablesSvg}${arcsSvg}</g>`;
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
        const entityStroke = isLight ? "#d97706" : "#fbbf24";
        const pkStroke = isLight ? "#0369a1" : "#38bdf8";
        const diamondFill = isLight ? "#ecfdf5" : "#0f2922";
        const diamondStroke = isLight ? "#059669" : "#10b981";
        const ovalFill = isLight ? "#ffffff" : "#11141c";
        const ovalStroke = isLight ? "#64748b" : "#475569";
        const lineStroke = isLight ? "#059669" : "#10b981";
        const tableHeaderFill = isLight ? "#fef3c7" : "#1e293b";
        const tableRowFill = isLight ? "#ffffff" : "#11141c";
        const tableBorder = isLight ? "#d97706" : "#fbbf24";
        const flagColor = isLight ? "#0369a1" : "#38bdf8";

        const embeddedCss = `
            text { font-family: 'Segoe UI', system-ui, sans-serif; }
            .rd-banner-box { fill: ${entityFill}; stroke: ${tableBorder}; stroke-width: 1.4; }
            .rd-banner-title { fill: ${textPrimary}; font-size: 15px; font-weight: 700; }
            .rd-banner-subtitle { fill: ${textSecondary}; font-size: 11.5px; font-family: Consolas, monospace; }
            .rd-attr-line { stroke: ${textSecondary}; stroke-width: 1.4; }
            .rd-attr-line.rd-dashed { stroke-dasharray: 5 4; }
            .rd-rel-line { stroke: ${lineStroke}; stroke-width: 2; }
            .rd-card-bg { fill: ${bg}; }
            .rd-card-label { fill: ${lineStroke}; font-size: 12px; font-weight: 700; font-family: Consolas, monospace; }
            .rd-policy-label { fill: ${pkStroke}; font-size: 11px; font-weight: 700; font-family: Consolas, monospace; }
            .rd-entity-rect { fill: ${entityFill}; stroke: ${entityStroke}; stroke-width: 2; }
            .rd-entity-rect-inner { fill: none; stroke: ${entityStroke}; stroke-width: 1.5; }
            .rd-entity-text { fill: ${textPrimary}; font-size: 13.5px; font-weight: 700; }
            .rd-diamond { fill: ${diamondFill}; stroke: ${diamondStroke}; stroke-width: 2; }
            .rd-diamond-inner { fill: none; stroke: ${diamondStroke}; stroke-width: 1.4; }
            .rd-diamond-text { fill: ${textPrimary}; font-size: 12.5px; font-weight: 700; }
            .rd-oval { fill: ${ovalFill}; stroke: ${ovalStroke}; stroke-width: 1.5; }
            .rd-oval-pk { stroke: ${pkStroke}; stroke-width: 2; }
            .rd-oval-derived { stroke-dasharray: 5 3; }
            .rd-oval-text { fill: ${textPrimary}; font-size: 12px; }
            .rd-text-pk { font-weight: 700; }
            .rd-underline-pk { stroke: ${pkStroke}; stroke-width: 1.6; }
            .rd-underline-disc { stroke: ${pkStroke}; stroke-width: 1.6; stroke-dasharray: 4 2.5; }
            .rd-underline-uk { stroke: ${textSecondary}; stroke-width: 1.4; stroke-dasharray: 3 2; }
            .rd-table-frame { fill: ${tableRowFill}; }
            .rd-table-header { fill: ${tableHeaderFill}; }
            .rd-table-title { fill: ${entityStroke}; font-size: 13px; font-weight: 700; font-family: Consolas, monospace; }
            .rd-table-border { stroke: ${tableBorder}; stroke-width: 1.8; }
            .rd-trow-bg { fill: ${tableRowFill}; }
            .rd-trow-sep { stroke: ${ovalStroke}; stroke-width: 1; opacity: 0.45; }
            .rd-tcol-name { fill: ${textPrimary}; font-size: 12px; font-family: Consolas, monospace; }
            .rd-tcol-type { fill: ${textSecondary}; font-size: 11px; font-family: Consolas, monospace; }
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
            this.onNotify(this._isEn() ? "No visible diagram to export." : "No hay diagrama visible para exportar.");
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
        this.onNotify(this._isEn() ? `Diagram exported as ${filename}` : `Diagrama exportado como ${filename}`);
    }

    exportPNG() {
        const built = this._buildExportableSvgString();
        if (!built) {
            this.onNotify(this._isEn() ? "No visible diagram to export." : "No hay diagrama visible para exportar.");
            return;
        }
        const db = (this.contract && this.contract.db_name) || "diagrama";
        const suffix = this.submode === "chen" ? "conceptual_chen" : "paso_a_tablas";
        const filename = `${db}_${suffix}.png`;

        const scale = 2;
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
                this.onNotify(
                    this._isEn()
                        ? `High-resolution PNG exported: ${filename}`
                        : `Imagen PNG de alta resolución exportada: ${filename}`
                );
            }, "image/png");
        };
        img.onerror = () => {
            URL.revokeObjectURL(url);
            this.onNotify(
                this._isEn()
                    ? "Could not rasterize to PNG; try Export SVG."
                    : "No se pudo rasterizar a PNG; prueba con Exportar SVG."
            );
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
