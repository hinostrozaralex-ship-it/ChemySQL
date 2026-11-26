/**
 * Módulo del Modo Tutor de SGBD-Smart.
 * Gestiona las tarjetas didácticas contextuales sobre el diagrama ER,
 * el desglosador paso a paso del orden lógico de ejecución SQL,
 * los esquemas visuales SVG de intersección de conjuntos (JOIN / GROUP BY)
 * y los escenarios de práctica guiada con pistas escalonadas.
 */

class TutorController {
    constructor(options) {
        this.lessonContainer = document.getElementById("tutor-lesson-container");
        this.challengesContainer = document.getElementById("challenges-list");
        this.logicalStepsContainer = document.getElementById("sql-logical-steps");
        this.vennContainer = document.getElementById("sql-venn-visualizer");
        this.bannerEl = document.getElementById("tutor-active-banner");
        this.bannerTitle = document.getElementById("tutor-banner-title");
        this.bannerText = document.getElementById("tutor-banner-text");

        this.onLoadChallengePrompt = options.onLoadChallengePrompt || (() => {});
        this.isTutorMode = false;
    }

    setTutorMode(enabled, contract, currentSelection) {
        this.isTutorMode = Boolean(enabled);
        if (this.bannerEl) {
            this.bannerEl.classList.toggle("hidden", !this.isTutorMode);
        }
        this.renderContextualLesson(contract, currentSelection);
    }

    renderContextualLesson(contract, selection) {
        if (!this.lessonContainer) return;

        if (!contract) {
            this.lessonContainer.innerHTML = `
                <div class="inspector-card">
                    <h3 class="sidebar-heading">Guía Pedagógica del Modo Tutor</h3>
                    <p class="sidebar-helper-text">Carga o genera un esquema para explorar explicaciones vivas sobre tus propias tablas y relaciones.</p>
                </div>
            `;
            return;
        }

        if (!selection) {
            const tableNames = (contract.tables || []).map((t) => t.name).join(", ");
            this.lessonContainer.innerHTML = `
                <div class="inspector-card">
                    <h3 class="sidebar-heading">Resumen Pedagógico del Esquema: ${this._escape(contract.title)}</h3>
                    <p class="sidebar-helper-text">${this._escape(
                        (contract.tutor_metadata && contract.tutor_metadata.nlp_summary) ||
                        "Este modelo estructura la información en tablas normalizadas conectadas mediante claves primarias y foráneas."
                    )}</p>
                    <div class="tutor-micro-lesson">
                        <strong>Entidades activas en tu lienzo:</strong>
                        <span>${this._escape(tableNames)}</span>
                    </div>
                    <p class="sidebar-helper-text">Selecciona cualquier tabla, columna (PK/FK) o línea de relación en el Lienzo ER para ver por qué existe y cómo protege tus datos.</p>
                </div>
            `;
            return;
        }

        if (selection.type === "table" && selection.data) {
            const tbl = selection.data;
            const pkCol = (tbl.columns || []).find((c) => c.is_pk);
            const fkCols = (tbl.columns || []).filter((c) => c.is_fk);

            if (this.isTutorMode && this.bannerTitle && this.bannerText) {
                this.bannerTitle.textContent = `Modo Tutor · Entidad seleccionada: '${tbl.name}'`;
                this.bannerText.textContent = tbl.tutor_explanation || tbl.description;
            }

            this.lessonContainer.innerHTML = `
                <div class="inspector-card">
                    <h3 class="sidebar-heading">Tabla '${this._escape(tbl.name)}'</h3>
                    <p class="sidebar-helper-text">${this._escape(tbl.tutor_explanation || tbl.description)}</p>
                    <div class="tutor-micro-lesson">
                        <strong>Rol en el modelo relacional:</strong>
                        <p>${
                            tbl.is_associative
                                ? `Es una Tabla Asociativa (Intermedia) que resuelve una relación Muchos-a-Muchos (N:M). Contiene claves foráneas hacia las tablas que conecta para evitar duplicar filas.`
                                : `Es una Entidad Sustantiva del dominio. Su clave primaria '${pkCol ? pkCol.name : "id"}' garantiza que cada registro sea único.`
                        }</p>
                        ${
                            fkCols.length > 0
                                ? `<p><strong>Vínculos salientes (${fkCols.length}):</strong> Depende de ${fkCols
                                      .map((f) => `${f.fk_target_table} (vía ${f.name})`)
                                      .join(", ")}.</p>`
                                : `<p><strong>Tabla Maestra / Independiente:</strong> No posee claves foráneas hacia otras tablas; otras tablas dependen de ella.</p>`
                        }
                    </div>
                </div>
            `;
            return;
        }

        if (selection.type === "column" && selection.data) {
            const col = selection.data;
            const roleLabel = col.is_pk
                ? "Clave Primaria Subrogada (PRIMARY KEY)"
                : col.is_fk
                ? `Clave Foránea (FOREIGN KEY -> ${col.fk_target_table}.${col.fk_target_column || "id"})`
                : col.is_unique
                ? "Atributo de Negocio Único (UNIQUE)"
                : `Atributo Descriptivo (${col.data_type})`;

            if (this.isTutorMode && this.bannerTitle && this.bannerText) {
                this.bannerTitle.textContent = `Modo Tutor · Columna '${selection.table}.${col.name}' (${roleLabel})`;
                this.bannerText.textContent = col.tutor_explanation || col.description;
            }

            this.lessonContainer.innerHTML = `
                <div class="inspector-card">
                    <h3 class="sidebar-heading">Columna '${this._escape(selection.table)}.${this._escape(col.name)}'</h3>
                    <div class="tutor-micro-lesson">
                        <strong>Clasificación estructural: ${this._escape(roleLabel)}</strong>
                        <p>${this._escape(col.tutor_explanation || col.description)}</p>
                    </div>
                    <div class="before-after-grid">
                        <div class="ba-box ba-after">
                            <strong>Tipo SQL:</strong> ${this._escape(col.data_type)} · 
                            <strong>Nulabilidad:</strong> ${col.nullable ? "NULL permitido" : "NOT NULL obligatorio"}
                        </div>
                    </div>
                </div>
            `;
            return;
        }

        if (selection.type === "view" && selection.data) {
            const vw = selection.data;
            if (this.isTutorMode && this.bannerTitle && this.bannerText) {
                this.bannerTitle.textContent = `Modo Tutor · Vista Virtual '${vw.name}' (VIEW)`;
                this.bannerText.textContent = vw.tutor_explanation || vw.description;
            }
            this.lessonContainer.innerHTML = `
                <div class="inspector-card">
                    <h3 class="sidebar-heading">Vista '${this._escape(vw.name)}' (CREATE VIEW)</h3>
                    <p class="sidebar-helper-text">${this._escape(
                        vw.tutor_explanation || "Una vista almacena una consulta SELECT con nombre propio, sin duplicar datos en disco."
                    )}</p>
                    <div class="tutor-micro-lesson">
                        <strong>Definición SQL virtual:</strong>
                        <pre class="ddl-code-preview">${this._escape(vw.select_sql)}</pre>
                    </div>
                </div>
            `;
            return;
        }

        if (selection.type === "relation" && selection.data) {
            const rel = selection.data;
            if (this.isTutorMode && this.bannerTitle && this.bannerText) {
                this.bannerTitle.textContent = `Modo Tutor · Relación ${rel.cardinality}: ${rel.source_table}.${rel.source_column} -> ${rel.target_table}.${rel.target_column}`;
                this.bannerText.textContent = rel.tutor_explanation;
            }

            this.lessonContainer.innerHTML = `
                <div class="inspector-card">
                    <h3 class="sidebar-heading">Vínculo Relacional (${this._escape(rel.cardinality)})</h3>
                    <p class="sidebar-helper-text">${this._escape(rel.tutor_explanation)}</p>
                    <div class="tutor-micro-lesson">
                        <strong>Política ON DELETE ${this._escape(rel.on_delete)}:</strong>
                        <p>${
                            rel.on_delete === "RESTRICT"
                                ? `Protección activa (RESTRICT): el motor SQLite impedirá borrar un registro de '${rel.target_table}' si todavía tiene registros asociados en '${rel.source_table}'.`
                                : rel.on_delete === "CASCADE"
                                ? `Borrado en cascada (CASCADE): al borrar una fila padre en '${rel.target_table}', se destruirán automáticamente todas las filas hijas asociadas en '${rel.source_table}'.`
                                : `Anulación de referencia (SET NULL): si se elimina el registro padre en '${rel.target_table}', la columna '${rel.source_column}' quedará en NULL.`
                        }</p>
                    </div>
                </div>
            `;
        }
    }

    renderSQLBreakdown(breakdown) {
        if (!this.logicalStepsContainer || !this.vennContainer) return;

        if (!breakdown || !breakdown.steps || breakdown.steps.length === 0) {
            this.logicalStepsContainer.innerHTML = `<span class="sidebar-helper-text">Escribe una consulta SQL para visualizar el orden lógico en que la procesa el motor.</span>`;
            this.vennContainer.innerHTML = "";
            return;
        }

        const algebra = breakdown.relational_algebra;
        const algebraHtml = algebra && algebra.expression
            ? `
                <div class="algebra-formula-box">
                    <div class="logical-step-top">
                        <span class="step-order-badge" style="background:var(--accent-indigo-tint); color:var(--accent-indigo); border-color:var(--accent-indigo);">Álgebra Relacional Equivalente</span>
                    </div>
                    <code class="algebra-expr-code">${this._escape(algebra.expression)}</code>
                    ${
                        algebra.operators && algebra.operators.length > 0
                            ? `<div class="algebra-ops-list">${algebra.operators
                                  .map(
                                      (op) =>
                                          `<span class="algebra-op-chip" title="${this._escape(op.detail)}"><strong>${this._escape(op.symbol)}</strong></span>`
                                  )
                                  .join(" ")}</div>`
                            : ""
                    }
                </div>
            `
            : "";

        this.logicalStepsContainer.innerHTML =
            algebraHtml +
            breakdown.steps
                .map(
                    (step) => `
                <div class="logical-step-card">
                    <div class="logical-step-top">
                        <span class="step-order-badge">Paso ${step.order} · ${this._escape(step.clause)}</span>
                    </div>
                    <code class="step-fragment">${this._escape(step.fragment)}</code>
                    <p class="step-desc">${this._escape(step.explanation)}</p>
                </div>
            `
                )
                .join("");

        const viz = breakdown.join_visualizer;
        if (!viz) {
            this.vennContainer.innerHTML = `
                <div class="sidebar-helper-text">
                    Incluye una cláusula <code>INNER JOIN</code>, <code>LEFT JOIN</code> o <code>GROUP BY</code> en tu consulta para visualizar el esquema de intersección de conjuntos aplicado a tus tablas.
                </div>
            `;
            return;
        }

        const isLeft = viz.type === "LEFT JOIN" || viz.type === "FULL JOIN" || viz.type === "CROSS JOIN";
        const isRight = viz.type === "RIGHT JOIN" || viz.type === "FULL JOIN" || viz.type === "CROSS JOIN";
        const isGroup = viz.type === "GROUP BY";

        const svgDiagram = isGroup
            ? `<svg width="120" height="64" viewBox="0 0 120 64" fill="none">
                    <rect x="6" y="8" width="32" height="14" rx="3" fill="var(--accent-cyan-tint)" stroke="var(--accent-cyan)"/>
                    <rect x="6" y="25" width="32" height="14" rx="3" fill="var(--accent-cyan-tint)" stroke="var(--accent-cyan)"/>
                    <rect x="6" y="42" width="32" height="14" rx="3" fill="var(--accent-cyan-tint)" stroke="var(--accent-cyan)"/>
                    <path d="M44 15L72 32M44 32L72 32M44 49L72 32" stroke="var(--accent-amber)" stroke-width="1.5"/>
                    <rect x="74" y="20" width="40" height="24" rx="4" fill="var(--accent-amber-tint)" stroke="var(--accent-amber)" stroke-width="2"/>
               </svg>`
            : `<svg width="120" height="64" viewBox="0 0 120 64" fill="none">
                    <circle cx="44" cy="32" r="23" fill="${
                        isLeft ? "rgba(56, 189, 248, 0.38)" : "rgba(56, 189, 248, 0.08)"
                    }" stroke="var(--accent-cyan)" stroke-width="1.8"/>
                    <circle cx="76" cy="32" r="23" fill="${
                        isRight ? "rgba(129, 140, 248, 0.38)" : "rgba(129, 140, 248, 0.08)"
                    }" stroke="var(--accent-indigo)" stroke-width="1.8"/>
                    <path d="M60 15.5 A23 23 0 0 1 60 48.5 A23 23 0 0 1 60 15.5 Z" fill="rgba(16, 185, 129, 0.55)" stroke="var(--accent-emerald)" stroke-width="1.5"/>
               </svg>`;

        this.vennContainer.innerHTML = `
            ${svgDiagram}
            <div>
                <strong style="font-size:13px; color:var(--accent-cyan); display:block;">${this._escape(viz.title)}</strong>
                <code style="font-size:12px; color:var(--accent-emerald);">${this._escape(viz.on_condition)}</code>
                <p style="font-size:12.5px; color:var(--text-secondary); margin-top:2px;">${this._escape(viz.explanation)}</p>
            </div>
        `;
    }

    renderChallenges(challenges) {
        if (!this.challengesContainer) return;
        this.challengesContainer.innerHTML = "";

        (challenges || []).forEach((ch) => {
            const card = document.createElement("article");
            card.className = "inspector-card";
            card.innerHTML = `
                <div class="audit-card-header">
                    <h4 class="audit-title">${this._escape(ch.title)}</h4>
                    <span class="count-chip">${this._escape(ch.level)}</span>
                </div>
                <p class="sidebar-helper-text">${this._escape(ch.goal)}</p>
                <div class="dialect-pills">
                    <button type="button" class="btn-xs" data-hint="1">1. Pista Conceptual</button>
                    <button type="button" class="btn-xs" data-hint="2">2. Pista Estructural</button>
                    <button type="button" class="btn-xs" data-hint="3">3. Solución</button>
                </div>
                <div class="tutor-micro-lesson hidden" data-hint-box></div>
                <button type="button" class="btn btn-secondary btn-sm" data-load-challenge>
                    Cargar Escenario en el Lienzo ER
                </button>
            `;

            const hintBox = card.querySelector("[data-hint-box]");
            card.querySelectorAll("[data-hint]").forEach((btn) => {
                btn.addEventListener("click", () => {
                    const lvl = btn.getAttribute("data-hint");
                    hintBox.classList.remove("hidden");
                    if (lvl === "1") {
                        hintBox.innerHTML = `<strong>Pista 1 (Conceptual):</strong><p>${this._escape(ch.hint_1_conceptual)}</p>`;
                    } else if (lvl === "2") {
                        hintBox.innerHTML = `<strong>Pista 2 (Estructural):</strong><p>${this._escape(ch.hint_2_estructural)}</p>`;
                    } else {
                        hintBox.innerHTML = `<strong>Pista 3 (Solución Comentada):</strong><p>${this._escape(ch.hint_3_solution)}</p>`;
                    }
                });
            });

            const loadBtn = card.querySelector("[data-load-challenge]");
            loadBtn.addEventListener("click", () => {
                this.onLoadChallengePrompt(ch);
            });

            this.challengesContainer.appendChild(card);
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

window.TutorController = TutorController;
