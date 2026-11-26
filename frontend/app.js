/**
 * Orquestador Principal del Frontend de SGBD-Smart.
 * Conecta el Contrato Maestro JSON con el Lienzo Visual ER, el Auditor Proactivo,
 * el Modo Tutor, el Explorador de Datos Relacional, el Editor SQL Dual y el Escudo Anti-Desastres.
 */

import {
    NLP_PRESETS,
    STORAGE_KEYS,
    apiFetch,
    createInitialState,
    escapeHtml,
    readStorage,
    showToast,
    writeStorage,
} from "./modules/core.js";
import { exportExplorerTable, exportSQLResults } from "./modules/export_utils.js";
import { LANG_STORAGE_KEY, applyLanguageToDOM, t } from "./modules/i18n.js";
import { renderLiveSQLInspector, renderProfessionalInspector } from "./modules/inspector.js";
import { SchemaUndoManager } from "./modules/undo_manager.js";

    const state = createInitialState();
    state.lang = "es";
    const undoManager = new SchemaUndoManager(40);

    let erCanvas = null;
    let relDiagram = null;
    let tutorCtrl = null;
    let sqlEditor = null;
    let ddlEditor = null;

    function restoreUserPreferences() {
        const savedTheme = readStorage(STORAGE_KEYS.theme);
        if (savedTheme === "dark" || savedTheme === "light") {
            state.theme = savedTheme;
            document.documentElement.setAttribute("data-theme", state.theme);
        }
        const savedLang = readStorage(LANG_STORAGE_KEY);
        if (savedLang === "en" || savedLang === "es") {
            state.lang = savedLang;
            applyLanguageToDOM(state.lang);
        } else {
            apiFetch("/api/health")
                .then((h) => {
                    if (h && (h.default_language === "en" || h.default_language === "es")) {
                        state.lang = h.default_language;
                        applyLanguageToDOM(state.lang);
                    }
                })
                .catch(() => {});
        }
        const savedLeft = Number(readStorage(STORAGE_KEYS.leftWidth));
        if (Number.isFinite(savedLeft) && savedLeft >= 210 && savedLeft <= 440) {
            document.documentElement.style.setProperty("--sidebar-left-width", `${savedLeft}px`);
        }
        const savedRight = Number(readStorage(STORAGE_KEYS.rightWidth));
        if (Number.isFinite(savedRight) && savedRight >= 290 && savedRight <= 560) {
            document.documentElement.style.setProperty("--sidebar-right-width", `${savedRight}px`);
        }
    }

    /* ======================================================================
       Inicialización Principal
       ====================================================================== */
    async function initApp() {
        restoreUserPreferences();
        if (window.innerWidth <= 540 || window.location.search.includes("mobile=1")) {
            document.documentElement.setAttribute("data-viewport", "mobile");
        }
        erCanvas = new window.ERCanvasController({
            onSelectElement: (sel) => handleElementSelected(sel),
            onSchemaMutated: (contract, runAudit = true) => handleLocalSchemaMutation(contract, runAudit),
            onDeleteTable: (tableName) => requestDeleteTable(tableName),
        });

        relDiagram = new window.RelationalDiagramController({
            onSelectElement: (sel) => handleElementSelected(sel),
            onNotify: (msg) => showToast(msg),
        });

        tutorCtrl = new window.TutorController({
            onLoadChallengePrompt: (challenge) => {
                const promptEl = document.getElementById("nlp-prompt-input");
                const dbNameEl = document.getElementById("nlp-db-name-input");
                if (promptEl) promptEl.value = challenge.suggested_prompt;
                if (dbNameEl) dbNameEl.value = challenge.id.replace("reto_", "proyecto_");
                setMode("tutor");
                runNLPInference();
            },
        });

        let sqlDebounce = null;
        let sqlLiveInspectDebounce = null;
        sqlEditor = new window.SQLCodeEditorController({
            textareaId: "sql-code-textarea",
            highlightId: "sql-highlight-layer",
            gutterId: "sql-line-gutter",
            popupId: "sql-autocomplete-popup",
            getSchemaContract: () => state.contract,
            onChange: (val) => {
                if (state.mode === "tutor") {
                    clearTimeout(sqlDebounce);
                    sqlDebounce = setTimeout(() => refreshLiveSQLDecomposition(), 240);
                }
                clearTimeout(sqlLiveInspectDebounce);
                sqlLiveInspectDebounce = setTimeout(() => {
                    const inspTab = document.getElementById("right-tab-inspector");
                    if (inspTab && inspTab.classList.contains("active")) {
                        refreshLiveSQLInspectorPanel(val);
                    }
                }, 260);
            },
            onExecuteShortcut: () => executeSQLQuery(false),
            onSaveShortcut: () => saveCurrentSQLFile(false),
        });

        ddlEditor = new window.SQLCodeEditorController({
            textareaId: "ddl-code-textarea",
            highlightId: "ddl-highlight-layer",
            gutterId: "ddl-line-gutter",
            popupId: "ddl-autocomplete-popup",
            getSchemaContract: () => state.contract,
            onExecuteShortcut: () => applyDDLEditsToSchema(),
            onSaveShortcut: () => downloadDDLScript(),
        });

        bindGlobalControls();
        bindResizablePanels();
        bindExplorerControls();
        bindSQLEditorControls();
        bindRelationModal();
        bindShieldModal();
        bindProjectAndDeleteModals();

        await refreshDatabasesList();
        if (state.databases.length > 0) {
            await loadDatabaseProject(state.databases[0].db_name);
        } else {
            createBlankProjectContract("nuevo_proyecto", "Nuevo Proyecto", true, true);
        }

        const savedMode = readStorage(STORAGE_KEYS.mode);
        if (savedMode === "tutor") {
            setMode("tutor", true);
        }
    }

    async function refreshDatabasesList() {
        try {
            const data = await apiFetch("/api/databases");
            state.databases = data.databases || [];
            state.challenges = data.challenges || [];
            if (data.workspaces_dir) {
                updateWorkspacePathDisplay(data.workspaces_dir);
            }
            renderDatabasesSidebar();
            tutorCtrl.renderChallenges(state.challenges);
        } catch (err) {
            showToast(`Error al cargar catálogo de bases de datos: ${err.message}`);
        }
    }

    function updateWorkspacePathDisplay(dirPath) {
        const el = document.getElementById("workspace-path-display");
        if (!el || !dirPath) return;
        el.textContent = dirPath;
        el.title = `Carpeta conectada: ${dirPath}`;
    }

    async function loadDatabaseProject(dbName) {
        try {
            const data = await apiFetch(`/api/databases/${encodeURIComponent(dbName)}`);
            state.activeDbName = dbName;
            state.contract = data.schema_contract;
            undoManager.reset(state.contract);
            state.ddlPreviews = data.ddl_previews || { sqlite: "", postgresql: "", mysql: "", sqlserver: "" };
            state.history = data.history || [];
            state.selectedElement = state.contract.tables && state.contract.tables[0]
                ? { type: "table", table: state.contract.tables[0].name, data: state.contract.tables[0] }
                : null;

            const promptEl = document.getElementById("nlp-prompt-input");
            const dbNameEl = document.getElementById("nlp-db-name-input");
            if (promptEl && state.contract.source_prompt) {
                promptEl.value = state.contract.source_prompt;
            }
            if (dbNameEl) {
                dbNameEl.value = state.contract.db_name;
            }

            syncAllViews();
            erCanvas.fitToViewport();

            if (state.contract.tables && state.contract.tables.length > 0) {
                state.explorer.activeTable = state.contract.tables[0].name;
                state.explorer.page = 1;
                state.explorer.search = "";
                const searchEl = document.getElementById("explorer-search-input");
                if (searchEl) searchEl.value = "";
                setDefaultSQLForContract(state.contract);
                if (state.contract.is_deployed) {
                    await loadExplorerTableRows();
                } else {
                    renderUndeployedExplorerNotice();
                }
            }
            await refreshLiveSQLDecomposition();
        } catch (err) {
            showToast(`No se pudo abrir '${dbName}': ${err.message}`);
        }
    }

    function setSQLCodeValue(code) {
        if (sqlEditor) {
            sqlEditor.setValue(code);
        } else {
            const textarea = document.getElementById("sql-code-textarea");
            if (textarea) textarea.value = code;
        }
    }

    function setDefaultSQLForContract(contract) {
        if (!contract || !contract.tables || !contract.tables.length) return;
        if (contract.db_name === "taller_mecanico") {
            setSQLCodeValue(
                "SELECT c.nombre AS cliente, v.matricula, v.marca, r.codigo AS orden, r.total\nFROM clientes c\nINNER JOIN vehiculos v ON c.id = v.cliente_id\nINNER JOIN reparaciones r ON v.id = r.vehiculo_id\nORDER BY r.total DESC\nLIMIT 20;"
            );
        } else if (contract.db_name === "biblioteca_municipal") {
            setSQLCodeValue(
                "SELECT s.nombre AS socio, l.titulo AS libro, p.fecha_prestamo, p.fecha_vencimiento, p.devuelto\nFROM socios s\nINNER JOIN prestamos p ON s.id = p.socio_id\nINNER JOIN libros l ON l.id = p.libro_id\nORDER BY p.fecha_prestamo DESC\nLIMIT 20;"
            );
        } else if (contract.relations && contract.relations.length > 0) {
            const r = contract.relations[0];
            setSQLCodeValue(
                `SELECT a.*, b.*\nFROM ${r.target_table} a\nINNER JOIN ${r.source_table} b ON a.${r.target_column} = b.${r.source_column}\nLIMIT 20;`
            );
        } else {
            setSQLCodeValue(`SELECT *\nFROM ${contract.tables[0].name}\nLIMIT 20;`);
        }
    }

    function renderUndeployedExplorerNotice() {
        const thead = document.getElementById("explorer-grid-thead");
        const tbody = document.getElementById("explorer-grid-tbody");
        const summary = document.getElementById("explorer-row-summary");
        if (thead) thead.innerHTML = "";
        if (tbody) {
            tbody.innerHTML = `<tr><td style="text-align:center; padding:28px; color:var(--accent-amber);">Este boceto tiene cambios pendientes de aprobación. Pulsa <strong>Aprobar y Desplegar</strong> en la barra superior para materializar las tablas en SQLite y explorar sus registros.</td></tr>`;
        }
        if (summary) summary.textContent = "Boceto sin desplegar en disco";
    }

    function syncAllViews() {
        if (!state.contract) return;

        // Actualizar cabecera y estado
        const badge = document.getElementById("schema-status-badge");
        const subtitle = document.getElementById("active-project-subtitle");
        const projSelect = document.getElementById("project-select");

        if (badge) {
            if (state.contract.is_deployed) {
                badge.textContent = `Desplegado en SQLite v${state.contract.version || 1}`;
                badge.className = "status-pill status-deployed";
            } else {
                badge.textContent = "Boceto en Revisión (Pendiente de Aprobar)";
                badge.className = "status-pill status-draft";
            }
        }
        if (subtitle) {
            subtitle.textContent = `${state.contract.db_name}.db · ${state.contract.title}`;
        }
        if (projSelect) {
            const exists = state.databases.some((d) => d.db_name === state.contract.db_name);
            let optsHtml = state.databases
                .map(
                    (d) =>
                        `<option value="${escapeHtml(d.db_name)}" ${
                            d.db_name === state.contract.db_name ? "selected" : ""
                        }>${escapeHtml(d.db_name)}.db (${d.table_count} tablas)</option>`
                )
                .join("");
            if (!exists) {
                optsHtml =
                    `<option value="${escapeHtml(state.contract.db_name)}" selected>${escapeHtml(
                        state.contract.db_name
                    )}.db (Boceto)</option>` + optsHtml;
            }
            projSelect.innerHTML = optsHtml;
        }

        // Actualizar contadores de telemetría
        const tCount = (state.contract.tables || []).length;
        const rCount = (state.contract.relations || []).length;
        const aCount = (state.contract.audit_alerts || []).length;

        const elBadgeTbl = document.getElementById("badge-table-count");
        const elMetTbl = document.getElementById("metric-tables");
        const elMetRel = document.getElementById("metric-relations");
        const elMetAl = document.getElementById("metric-alerts");
        const elRightBadge = document.getElementById("right-tab-alert-badge");

        if (elBadgeTbl) elBadgeTbl.textContent = String(tCount);
        if (elMetTbl) elMetTbl.textContent = String(tCount);
        if (elMetRel) elMetRel.textContent = String(rCount);
        if (elMetAl) elMetAl.textContent = String(aCount);
        if (elRightBadge) elRightBadge.textContent = String(aCount);

        updateIDEStatusBar(tCount, rCount, aCount);

        renderDatabasesSidebar();
        renderMigrationsHistory();
        erCanvas.selectedElement = state.selectedElement;
        erCanvas.render(state.contract);
        if (relDiagram) {
            relDiagram.render(state.contract);
        }
        renderAuditorAlerts();
        renderInspectorEditor();
        renderDDLPreview();
        tutorCtrl.renderContextualLesson(state.contract, state.selectedElement);
        renderExplorerTablePills();
        populateGuidedQueryBuilder();
        renderSQLAutocompleteChips();
    }

    /* ======================================================================
       Barra Lateral Izquierda: Bases de Datos, Árbol de Esquema y Migraciones
       ====================================================================== */
    function updateIDEStatusBar(tCount, rCount, aCount) {
        const dbEl = document.getElementById("status-db-name");
        const dotEngine = document.getElementById("status-engine-dot");
        const countsEl = document.getElementById("status-counts");
        const audDot = document.getElementById("status-auditor-dot");
        const audText = document.getElementById("status-auditor-text");
        const modeEl = document.getElementById("status-mode-label");
        const themeEl = document.getElementById("status-theme-label");

        if (dbEl && state.contract) {
            const verStr = state.contract.is_deployed ? `v${state.contract.version || 1}` : "borrador";
            dbEl.textContent = `${state.contract.db_name}.db (${verStr})`;
        }
        if (dotEngine && state.contract) {
            dotEngine.className = `statusbar-dot ${state.contract.is_deployed ? "ok" : "warn"}`;
        }
        if (countsEl) {
            countsEl.textContent = `${tCount} tabla${tCount === 1 ? "" : "s"} · ${rCount} rel.`;
        }
        if (audDot && audText) {
            audDot.className = `statusbar-dot ${aCount === 0 ? "ok" : "warn"}`;
            audText.textContent =
                aCount === 0 ? "Auditoría: 0 alertas" : `Auditoría: ${aCount} alerta${aCount === 1 ? "" : "s"}`;
        }
        if (modeEl) {
            modeEl.textContent = state.mode === "tutor" ? "Modo Tutor" : "Modo Estándar";
        }
        if (themeEl) {
            themeEl.textContent = state.theme === "light" ? "Tema Claro" : "Tema Oscuro";
        }
    }

    function renderDatabasesSidebar() {
        const listEl = document.getElementById("databases-list");
        const countEl = document.getElementById("db-count-badge");
        if (!listEl) return;

        const isActiveUnsavedDraft =
            state.contract &&
            !state.contract.is_deployed &&
            !state.databases.some((d) => d.db_name === state.contract.db_name);

        const totalShown = state.databases.length + (isActiveUnsavedDraft ? 1 : 0);
        if (countEl) countEl.textContent = String(totalShown);

        let html = "";

        if (isActiveUnsavedDraft) {
            const draftTitle = state.contract.title || state.contract.db_name;
            html += `
                <div class="db-item-card active" title="${escapeHtml(state.contract.db_name)}.db (Boceto sin guardar en disco)">
                    <div class="db-item-top">
                        <div class="db-item-title-cluster">
                            <svg class="db-item-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                                <ellipse cx="12" cy="5" rx="8" ry="3"></ellipse>
                                <path d="M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5"></path>
                            </svg>
                            <span class="db-item-name">${escapeHtml(draftTitle)}</span>
                        </div>
                        <span class="tab-badge-amber">Boceto</span>
                    </div>
                </div>
            `;
        }

        html += state.databases
            .map((db) => {
                const displayTitle = db.title || db.db_name;
                const isActive = state.contract && state.contract.db_name === db.db_name;
                return `
                    <div class="db-item-card ${isActive ? "active" : ""}" data-open-db="${escapeHtml(
                    db.db_name
                )}" title="${escapeHtml(displayTitle)} (${escapeHtml(db.db_name)}.db)">
                        <div class="db-item-top">
                            <div class="db-item-title-cluster">
                                <svg class="db-item-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                                    <ellipse cx="12" cy="5" rx="8" ry="3"></ellipse>
                                    <path d="M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5"></path>
                                </svg>
                                <span class="db-item-name">${escapeHtml(displayTitle)}</span>
                            </div>
                            <button type="button" class="btn-delete-inline" data-delete-db="${escapeHtml(
                                db.db_name
                            )}" title="Eliminar proyecto '${escapeHtml(displayTitle)}'" aria-label="Eliminar proyecto ${escapeHtml(displayTitle)}">
                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
                                    <polyline points="3 6 5 6 21 6"></polyline>
                                    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"></path>
                                </svg>
                            </button>
                        </div>
                    </div>
                `;
            })
            .join("");

        if (!html) {
            html = `<div class="sidebar-helper-text" style="padding:8px 4px;">No hay proyectos en esta carpeta. Pulsa <strong>+ Nuevo</strong> para crear uno.</div>`;
        }

        listEl.innerHTML = html;

        listEl.querySelectorAll("[data-open-db]").forEach((card) => {
            card.addEventListener("click", () => {
                const targetDb = card.getAttribute("data-open-db");
                if (targetDb) loadDatabaseProject(targetDb);
            });
        });

        listEl.querySelectorAll("[data-delete-db]").forEach((btn) => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                const targetDb = btn.getAttribute("data-delete-db");
                if (targetDb) requestDeleteProject(targetDb);
            });
        });
    }

    function renderMigrationsHistory() {
        const container = document.getElementById("migrations-timeline");
        if (!container) return;

        if (!state.history || state.history.length === 0) {
            container.innerHTML = `<div class="inspector-card"><p class="sidebar-helper-text">Aún no hay migraciones desplegadas para este boceto. Pulsa "Aprobar y Desplegar" para crear la versión v1.</p></div>`;
            return;
        }

        container.innerHTML = state.history
            .map(
                (ver) => `
                <article class="inspector-card">
                    <div class="audit-card-header">
                        <strong class="audit-title">Versión v${ver.version_id}</strong>
                        <span class="db-item-meta">${escapeHtml(ver.timestamp)}</span>
                    </div>
                    <p class="sidebar-helper-text">${escapeHtml(ver.summary)}</p>
                    <pre class="ddl-code-preview">${escapeHtml((ver.ddl_statements || []).join("\n"))}</pre>
                </article>
            `
            )
            .join("");
    }

    /* ======================================================================
       Panel Derecho: Auditor Proactivo, Inspector y DDL Multi-Dialecto
       ====================================================================== */
    function renderAuditorAlerts() {
        const container = document.getElementById("auditor-alerts-container");
        if (!container || !state.contract) return;

        const alerts = state.contract.audit_alerts || [];
        if (alerts.length === 0) {
            container.innerHTML = `
                <div class="inspector-card">
                    <strong class="audit-title" style="color:var(--accent-emerald);">Esquema 100 % Verificado (0 Alertas)</strong>
                    <p class="sidebar-helper-text">Todas las tablas cuentan con clave primaria, cumplen la 1ª Forma Normal, utilizan tipos semánticos exactos, protegen el historial frente a cascadas destructivas y tienen índices en sus claves foráneas.</p>
                </div>
            `;
            return;
        }

        const sevLabel = {
            critical: "Crítico",
            warning: "Advertencia",
            suggestion: "Sugerencia",
            info: "Info",
        };

        container.innerHTML = alerts
            .map((al) => {
                const lesson = al.tutor_lesson || {};
                const showLesson = state.mode === "tutor" && lesson.concept;
                return `
                    <article class="audit-card severity-${escapeHtml(al.severity)}">
                        <div class="audit-card-header">
                            <h4 class="audit-title">${escapeHtml(al.title)}</h4>
                            <span class="severity-badge">${escapeHtml(sevLabel[al.severity] || al.severity)}</span>
                        </div>
                        <p class="audit-tech-msg">${escapeHtml(al.technical_message)}</p>
                        ${
                            showLesson
                                ? `
                            <div class="tutor-micro-lesson">
                                <strong style="color:var(--accent-amber);">Micro-Lección Tutor: ${escapeHtml(
                                    lesson.concept
                                )}</strong>
                                <p>${escapeHtml(lesson.why_it_matters || "")}</p>
                                ${
                                    lesson.before_example
                                        ? `
                                    <div class="before-after-grid">
                                        <div class="ba-box ba-before"><strong>Antes:</strong> ${escapeHtml(
                                            lesson.before_example
                                        )}</div>
                                        <div class="ba-box ba-after"><strong>Después:</strong> ${escapeHtml(
                                            lesson.after_example || ""
                                        )}</div>
                                    </div>
                                `
                                        : ""
                                }
                                ${
                                    lesson.analogy
                                        ? `<p><em>Analogía cotidiana:</em> ${escapeHtml(lesson.analogy)}</p>`
                                        : ""
                                }
                            </div>
                        `
                                : ""
                        }
                        ${
                            al.auto_fix_action
                                ? `
                            <button type="button" class="btn btn-secondary btn-sm" data-autofix-id="${escapeHtml(
                                al.id
                            )}">
                                <span>${escapeHtml(al.auto_fix_label || "Aplicar Corrección Automática")}</span>
                            </button>
                        `
                                : ""
                        }
                    </article>
                `;
            })
            .join("");

        container.querySelectorAll("[data-autofix-id]").forEach((btn) => {
            btn.addEventListener("click", async () => {
                const alertId = btn.getAttribute("data-autofix-id");
                if (!alertId) return;
                try {
                    const res = await apiFetch("/api/schema/autofix", {
                        method: "POST",
                        body: JSON.stringify({
                            schema_contract: state.contract,
                            alert_id: alertId,
                        }),
                    });
                    state.contract = res.schema_contract;
                    state.ddlPreviews = res.ddl_previews;
                    state.contract.is_deployed = false;
                    undoManager.record(state.contract);
                    syncAllViews();
            erCanvas.fitToViewport();
                    showToast(res.summary || "Corrección automática aplicada al boceto.");
                } catch (err) {
                    showToast(`Error al aplicar corrección: ${err.message}`);
                }
            });
        });
    }

    function refreshLiveSQLInspectorPanel(sqlText) {
        const container = document.getElementById("inspector-editor-container");
        if (!container || !state.contract) return;
        renderLiveSQLInspector(container, sqlText, state.contract, {
            lang: state.lang || "es",
            onJumpToLine: (line) => {
                activateCenterView("sql");
                activateSQLSubtab("dml");
                if (sqlEditor && typeof sqlEditor.jumpToLine === "function") {
                    sqlEditor.jumpToLine(line);
                }
            },
            onSelectElement: (sel) => {
                state.selectedElement = sel;
                renderInspectorEditor();
            },
        });
    }

    function renderInspectorEditor() {
        const container = document.getElementById("inspector-editor-container");
        if (!container || !state.contract) return;
        renderProfessionalInspector(container, state, {
            onSelectElement: (sel) => {
                state.selectedElement = sel;
                renderInspectorEditor();
                if (tutorCtrl) tutorCtrl.renderContextualLesson(state.contract, sel);
            },
            onSchemaMutated: (contract, runAudit = true) => handleLocalSchemaMutation(contract, runAudit),
            onDeleteTable: (tableName) => requestDeleteTable(tableName),
            onOpenTableInExplorer: (tableName) => {
                state.explorer.activeTable = tableName;
                state.explorer.page = 1;
                activateCenterView("explorer");
                renderExplorerTablePills();
                if (state.contract.is_deployed) {
                    loadExplorerTableRows();
                } else {
                    renderUndeployedExplorerNotice();
                }
            },
        });
    }

    function renderDDLPreview() {
        const rawSql = state.ddlPreviews[state.activeDialect] || "-- Sin DDL generado";
        if (ddlEditor) {
            ddlEditor.setValue(rawSql);
        } else {
            const editorEl = document.getElementById("ddl-code-textarea");
            if (editorEl) editorEl.value = rawSql;
        }
        const dialectBadge = document.getElementById("ddl-dialect-badge");
        if (dialectBadge) {
            const labels = {
                sqlite: "SQLITE",
                mysql: "MYSQL",
                sqlserver: "SQL SERVER",
                postgresql: "POSTGRESQL",
            };
            dialectBadge.textContent = labels[state.activeDialect] || state.activeDialect.toUpperCase();
        }
    }

    function activateSQLSubtab(subtab) {
        state.activeSqlSubtab = subtab === "dml" ? "dml" : "ddl";
        document.querySelectorAll("[data-sql-subtab]").forEach((btn) => {
            btn.classList.toggle("active", btn.getAttribute("data-sql-subtab") === state.activeSqlSubtab);
        });
        const ddlPane = document.getElementById("sql-subpane-ddl");
        const dmlPane = document.getElementById("sql-subpane-dml");
        if (ddlPane) ddlPane.classList.toggle("active", state.activeSqlSubtab === "ddl");
        if (dmlPane) dmlPane.classList.toggle("active", state.activeSqlSubtab === "dml");

        const hintEl = document.getElementById("sql-subtab-hint");
        if (hintEl) {
            hintEl.textContent =
                state.activeSqlSubtab === "ddl"
                    ? "Código DDL sincronizado bidireccionalmente con el Lienzo ER"
                    : "Consultas DML interactivas con EXPLAIN QUERY PLAN y Escudo Anti-Desastres";
        }
        if (state.activeSqlSubtab === "ddl" && ddlEditor) {
            ddlEditor.refreshHighlight();
        } else if (state.activeSqlSubtab === "dml" && sqlEditor) {
            sqlEditor.refreshHighlight();
            refreshLiveSQLDecomposition();
        }
    }

    async function applyDDLEditsToSchema() {
        const editedSql = ddlEditor
            ? ddlEditor.getValue().trim()
            : (document.getElementById("ddl-code-textarea")?.value || "").trim();
        if (!editedSql) {
            showToast("El código DDL está vacío.");
            return;
        }
        try {
            const res = await apiFetch("/api/schema/parse-ddl", {
                method: "POST",
                body: JSON.stringify({
                    sql: editedSql,
                    schema_contract: state.contract,
                }),
            });
            state.contract = res.schema_contract;
            state.ddlPreviews = res.ddl_previews;
            state.contract.is_deployed = false;
            undoManager.record(state.contract);
            syncAllViews();
            showToast("Cambios del código DDL aplicados al Lienzo ER y al Auditor.");
        } catch (err) {
            showToast(err.message);
        }
    }

    async function downloadDDLScript() {
        const ddl =
            (ddlEditor && ddlEditor.getValue()) ||
            state.ddlPreviews[state.activeDialect] ||
            "";
        const filename = `${(state.contract && state.contract.db_name) || "esquema"}_${state.activeDialect}.sql`;
        try {
            const res = await apiFetch("/api/files/save-sql", {
                method: "POST",
                body: JSON.stringify({
                    content: ddl,
                    filename: filename,
                    save_as: true,
                }),
            });
            if (res.saved) {
                showToast(`Script DDL guardado en: ${res.path}`);
            }
        } catch (_err) {
            const blob = new Blob([ddl], { type: "text/sql;charset=utf-8" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = filename;
            a.click();
            URL.revokeObjectURL(url);
            showToast(`Script descargado: ${filename}`);
        }
    }

    function handleElementSelected(selection) {
        state.selectedElement = selection;
        renderInspectorEditor();
        tutorCtrl.renderContextualLesson(state.contract, selection);

        if (state.mode === "tutor") {
            activateRightTab("tutor");
        }
    }

    async function handleLocalSchemaMutation(contract, runAudit = true, recordHistory = true) {
        state.contract = contract;
        state.contract.is_deployed = false;
        if (!runAudit) {
            if (recordHistory) undoManager.record(state.contract);
            syncAllViews();
            erCanvas.fitToViewport();
            return;
        }
        try {
            const res = await apiFetch("/api/schema/audit", {
                method: "POST",
                body: JSON.stringify(state.contract),
            });
            state.contract = res.schema_contract;
            state.ddlPreviews = res.ddl_previews;
            if (recordHistory) undoManager.record(state.contract);
            syncAllViews();
            erCanvas.fitToViewport();
        } catch (err) {
            showToast(`Error al auditar cambios: ${err.message}`);
        }
    }

    async function performSchemaUndo() {
        const prev = undoManager.undo();
        if (!prev) return;
        state.selectedElement = null;
        await handleLocalSchemaMutation(prev, true, false);
        showToast("Deshacer aplicado al esquema.");
    }

    async function performSchemaRedo() {
        const next = undoManager.redo();
        if (!next) return;
        state.selectedElement = null;
        await handleLocalSchemaMutation(next, true, false);
        showToast("Rehacer aplicado al esquema.");
    }

    /* ======================================================================
       Flujo Central: Inferencia NLP y Aprobación / Despliegue Explícito
       ====================================================================== */
    async function runNLPInference() {
        const promptEl = document.getElementById("nlp-prompt-input");
        const dbNameEl = document.getElementById("nlp-db-name-input");
        const text = promptEl ? promptEl.value.trim() : "";
        const dbName = dbNameEl ? dbNameEl.value.trim() : "";

        if (!text) {
            showToast("Escribe una descripción en español para generar el esquema.");
            return;
        }

        try {
            const res = await apiFetch("/api/nlp/infer", {
                method: "POST",
                body: JSON.stringify({
                    text: text,
                    db_name: dbName || null,
                    dialect: state.activeDialect,
                }),
            });
            state.contract = res.schema_contract;
            undoManager.reset(state.contract);
            state.activeDbName = state.contract.db_name;
            state.ddlPreviews = res.ddl_previews;
            if (dbNameEl && state.contract.db_name) {
                dbNameEl.value = state.contract.db_name;
            }
            state.activeSqlFile = {
                filename: `${state.contract.db_name}.sql`,
                path: null,
            };
            updateActiveSQLFilenameUI();
            state.selectedElement = state.contract.tables[0]
                ? { type: "table", table: state.contract.tables[0].name, data: state.contract.tables[0] }
                : null;
            setDefaultSQLForContract(state.contract);
            activateCenterView("canvas");
            syncAllViews();
            erCanvas.fitToViewport();
            showToast(
                `Boceto '${state.contract.db_name}' generado: ${state.contract.tables.length} tablas y ${state.contract.relations.length} relaciones. Script DDL cargado en Editor SQL Dual.`
            );
        } catch (err) {
            showToast(`Error en motor NLP: ${err.message}`);
        }
    }

    async function approveAndDeploySchema() {
        if (!state.contract) return;
        const existingDb = state.databases.find((d) => d.db_name === state.contract.db_name);
        const shouldPopulateMock = !existingDb || (existingDb.total_rows || 0) === 0;
        try {
            const res = await apiFetch("/api/schema/deploy", {
                method: "POST",
                body: JSON.stringify({
                    schema_contract: state.contract,
                    populate_mock_data: shouldPopulateMock,
                    mock_rows_per_table: 12,
                }),
            });
            state.contract = res.schema_contract;
            undoManager.reset(state.contract);
            state.activeDbName = state.contract.db_name;
            state.ddlPreviews = res.ddl_previews;
            state.history = res.history || [];
            state.databases = res.databases || state.databases;
            syncAllViews();
            erCanvas.fitToViewport();

            if (state.contract.tables.length > 0) {
                state.explorer.activeTable = state.contract.tables[0].name;
                await loadExplorerTableRows();
            }
            showToast(
                shouldPopulateMock
                    ? `Esquema v${state.contract.version} aprobado y desplegado en workspaces/${state.contract.db_name}.db con datos de prueba coherentes.`
                    : `Esquema v${state.contract.version} actualizado en workspaces/${state.contract.db_name}.db preservando los registros existentes.`
            );
        } catch (err) {
            showToast(`Error al desplegar base de datos: ${err.message}`);
        }
    }

    /* ======================================================================
       Explorador de Datos Relacional y Previsualización Flotante FK
       ====================================================================== */
    function renderExplorerTablePills() {
        const container = document.getElementById("explorer-table-pills");
        if (!container || !state.contract) return;

        const tables = state.contract.tables || [];
        if (!state.explorer.activeTable && tables.length > 0) {
            state.explorer.activeTable = tables[0].name;
        }

        container.innerHTML = tables
            .map(
                (t) => `
                <button type="button" class="table-pill-btn ${
                    state.explorer.activeTable === t.name ? "active" : ""
                }" data-exp-table="${escapeHtml(t.name)}">
                    ${escapeHtml(t.name)}
                </button>
            `
            )
            .join("");

        container.querySelectorAll("[data-exp-table]").forEach((btn) => {
            btn.addEventListener("click", async () => {
                state.explorer.activeTable = btn.getAttribute("data-exp-table");
                state.explorer.page = 1;
                renderExplorerTablePills();
                await loadExplorerTableRows();
            });
        });
    }

    async function loadExplorerTableRows() {
        if (!state.contract || !state.explorer.activeTable) return;
        if (!state.contract.is_deployed) {
            renderUndeployedExplorerNotice();
            return;
        }
        try {
            const url = `/api/databases/${encodeURIComponent(
                state.contract.db_name
            )}/tables/${encodeURIComponent(state.explorer.activeTable)}/rows?page=${
                state.explorer.page
            }&page_size=${state.explorer.pageSize}&search=${encodeURIComponent(state.explorer.search)}`;
            const data = await apiFetch(url);
            state.explorer.columns = data.columns || [];
            state.explorer.rows = data.rows || [];
            state.explorer.totalRows = data.total_rows || 0;
            state.explorer.totalPages = data.total_pages || 1;
            renderExplorerDataGrid();
        } catch (err) {
            showToast(`Error al leer registros: ${err.message}`);
        }
    }

    function renderExplorerDataGrid() {
        const thead = document.getElementById("explorer-grid-thead");
        const tbody = document.getElementById("explorer-grid-tbody");
        const summary = document.getElementById("explorer-row-summary");
        const pageInd = document.getElementById("explorer-page-indicator");
        if (!thead || !tbody) return;

        const cols = state.explorer.columns;
        const pkCols = cols.filter((c) => c.is_pk);
        const effectivePkCols = pkCols.length > 0 ? pkCols : [cols[0] || { name: "id" }];
        const pkColNames = new Set(effectivePkCols.map((c) => c.name));
        const pkColObj = effectivePkCols[0];

        thead.innerHTML = `
            <tr>
                ${cols
                    .map(
                        (c) => `
                    <th>
                        ${c.is_pk ? '<i class="badge-pk">PK</i> ' : ""}
                        ${c.is_fk ? `<i class="badge-fk">FK &rarr; ${escapeHtml(c.fk_target_table)}</i> ` : ""}
                        ${escapeHtml(c.name)}
                    </th>
                `
                    )
                    .join("")}
                <th>Acciones</th>
            </tr>
        `;

        if (state.explorer.rows.length === 0) {
            tbody.innerHTML = `<tr><td colspan="${cols.length + 1}" style="text-align:center; padding:24px; color:var(--text-secondary);">No hay registros en esta tabla. Usa el botón "Mock Data" o "+ Nuevo Registro".</td></tr>`;
        } else {
            tbody.innerHTML = state.explorer.rows
                .map((row) => {
                    const pkMap = {};
                    effectivePkCols.forEach((p) => {
                        pkMap[p.name] = row[p.name];
                    });
                    const pkJson = JSON.stringify(pkMap);
                    const pkVal = row[pkColObj.name];
                    const cellsHtml = cols
                        .map((c) => {
                            const val = row[c.name];
                            if (c.is_fk && c.fk_target_table && val !== null && val !== undefined) {
                                return `
                                    <td>
                                        <button type="button" class="fk-cell-btn" data-fk-table="${escapeHtml(
                                            c.fk_target_table
                                        )}" data-fk-col="${escapeHtml(
                                    c.fk_target_column || "id"
                                )}" data-fk-val="${escapeHtml(val)}">
                                            <span>#${escapeHtml(val)} &rarr; ${escapeHtml(c.fk_target_table)}</span>
                                        </button>
                                    </td>
                                `;
                            }
                            const isNull = val === null || val === undefined;
                            const isNum = typeof val === "number";
                            const rendered = isNull ? '<span class="cell-null">NULL</span>' : escapeHtml(val);
                            return `<td class="${isNum ? "cell-num" : ""}" data-edit-col="${escapeHtml(c.name)}" data-pk-val="${escapeHtml(
                                pkVal
                            )}" data-pk-json="${escapeHtml(pkJson)}" data-raw-val="${isNull ? "" : escapeHtml(val)}" title="${
                                pkColNames.has(c.name) ? "Clave primaria" : "Doble clic para editar valor"
                            }">${rendered}</td>`;
                        })
                        .join("");

                    return `
                        <tr>
                            ${cellsHtml}
                            <td>
                                <button type="button" class="btn-xs" data-del-pk="${escapeHtml(
                                    pkVal
                                )}" data-pk-json="${escapeHtml(pkJson)}" style="color:var(--accent-crimson);">Eliminar</button>
                            </td>
                        </tr>
                    `;
                })
                .join("");
        }

        if (summary) {
            summary.textContent = `${state.explorer.totalRows} registros en '${state.explorer.activeTable}'`;
        }
        if (pageInd) {
            pageInd.textContent = `Página ${state.explorer.page} de ${state.explorer.totalPages}`;
        }

        // Eventos de Previsualización Flotante FK
        tbody.querySelectorAll("[data-fk-table]").forEach((btn) => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                const targetTbl = btn.getAttribute("data-fk-table");
                const targetCol = btn.getAttribute("data-fk-col");
                const val = btn.getAttribute("data-fk-val");
                const rect = btn.getBoundingClientRect();
                openFKPreviewPopover(targetTbl, targetCol, val, rect);
            });
        });

        // Edición en línea con doble clic
        tbody.querySelectorAll("[data-edit-col]").forEach((td) => {
            td.addEventListener("dblclick", () => {
                const colName = td.getAttribute("data-edit-col");
                const pkVal = td.getAttribute("data-pk-val");
                const pkJsonRaw = td.getAttribute("data-pk-json");
                if (pkColNames.has(colName)) return;
                let pkValuesObj = null;
                try {
                    pkValuesObj = pkJsonRaw ? JSON.parse(pkJsonRaw) : null;
                } catch (_err) {
                    pkValuesObj = null;
                }
                const oldVal = td.getAttribute("data-raw-val") !== null ? td.getAttribute("data-raw-val") : td.textContent;
                const input = document.createElement("input");
                input.type = "text";
                input.className = "control-input-sm";
                input.value = oldVal;
                input.style.width = "100%";
                td.innerHTML = "";
                td.appendChild(input);
                input.focus();

                const commitEdit = async () => {
                    const newVal = input.value;
                    if (newVal === oldVal) {
                        td.textContent = oldVal;
                        return;
                    }
                    try {
                        await apiFetch("/api/explorer/cell", {
                            method: "PUT",
                            body: JSON.stringify({
                                db_name: state.contract.db_name,
                                table_name: state.explorer.activeTable,
                                pk_column: pkColObj.name,
                                pk_value: pkVal,
                                pk_values: pkValuesObj,
                                target_column: colName,
                                new_value: newVal,
                            }),
                        });
                        td.textContent = newVal;
                        showToast(`Celda '${colName}' actualizada en SQLite.`);
                    } catch (err) {
                        td.textContent = oldVal;
                        showToast(err.message);
                    }
                };

                input.addEventListener("blur", commitEdit);
                input.addEventListener("keydown", (ev) => {
                    if (ev.key === "Enter") input.blur();
                    if (ev.key === "Escape") {
                        input.value = oldVal;
                        input.blur();
                    }
                });
            });
        });

        // Eliminar fila (soporta PK simple y PK compuesta)
        tbody.querySelectorAll("[data-del-pk]").forEach((btn) => {
            btn.addEventListener("click", async () => {
                const pkVal = btn.getAttribute("data-del-pk");
                const pkJsonRaw = btn.getAttribute("data-pk-json");
                try {
                    let deleteUrl = `/api/explorer/row?db_name=${encodeURIComponent(
                        state.contract.db_name
                    )}&table_name=${encodeURIComponent(
                        state.explorer.activeTable
                    )}&pk_column=${encodeURIComponent(pkColObj.name)}&pk_value=${encodeURIComponent(pkVal)}`;
                    if (pkJsonRaw) {
                        deleteUrl += `&pk_values=${encodeURIComponent(pkJsonRaw)}`;
                    }
                    await apiFetch(deleteUrl, { method: "DELETE" });
                    showToast(`Registro eliminado correctamente.`);
                    await loadExplorerTableRows();
                } catch (err) {
                    showToast(err.message);
                }
            });
        });
    }

    async function openFKPreviewPopover(targetTable, targetColumn, value, anchorRect) {
        const popover = document.getElementById("fk-preview-popover");
        const titleEl = document.getElementById("fk-popover-title");
        const bodyEl = document.getElementById("fk-popover-body");
        if (!popover || !titleEl || !bodyEl) return;

        popover.classList.remove("hidden");
        const top = Math.min(window.innerHeight - 240, anchorRect.bottom + 6);
        const left = Math.min(window.innerWidth - 340, Math.max(12, anchorRect.left));
        popover.style.top = `${top}px`;
        popover.style.left = `${left}px`;

        titleEl.textContent = `Cargando ${targetTable}.${targetColumn} = ${value}...`;
        bodyEl.innerHTML = "";

        try {
            const url = `/api/databases/${encodeURIComponent(
                state.contract.db_name
            )}/fk-preview?target_table=${encodeURIComponent(
                targetTable
            )}&target_column=${encodeURIComponent(targetColumn)}&value=${encodeURIComponent(value)}`;
            const data = await apiFetch(url);
            if (!data.found) {
                titleEl.textContent = `${targetTable} #${value} (No encontrado)`;
                return;
            }
            titleEl.textContent = `${targetTable} · ${data.headline}`;
            bodyEl.innerHTML = Object.entries(data.record || {})
                .map(
                    ([k, v]) => `
                    <div class="fk-kv-row">
                        <span class="fk-kv-key">${escapeHtml(k)}</span>
                        <span class="fk-kv-val">${escapeHtml(v)}</span>
                    </div>
                `
                )
                .join("");
        } catch (err) {
            titleEl.textContent = "Error al previsualizar FK";
            bodyEl.textContent = err.message;
        }
    }

    /* ======================================================================
       Editor SQL Dual, Asistente por Reglas, EXPLAIN QUERY PLAN y Escudo
       ====================================================================== */
    function populateGuidedQueryBuilder() {
        const tblSel = document.getElementById("qb-table");
        const joinSel = document.getElementById("qb-join");
        const whereColSel = document.getElementById("qb-where-col");
        const orderColSel = document.getElementById("qb-order-col");
        if (!tblSel || !state.contract) return;

        const tables = state.contract.tables || [];
        tblSel.innerHTML = tables
            .map((t) => `<option value="${escapeHtml(t.name)}">${escapeHtml(t.name)}</option>`)
            .join("");

        const updateDependentDropdowns = () => {
            const selectedTable = tblSel.value;
            const tblObj = tables.find((t) => t.name === selectedTable);
            if (!tblObj) return;

            const rels = (state.contract.relations || []).filter(
                (r) => r.source_table === selectedTable || r.target_table === selectedTable
            );
            joinSel.innerHTML =
                `<option value="">Sin cruce JOIN</option>` +
                rels
                    .map((r) => {
                        const otherTable = r.source_table === selectedTable ? r.target_table : r.source_table;
                        const onCond =
                            r.source_table === selectedTable
                                ? `${selectedTable}.${r.source_column} = ${otherTable}.${r.target_column}`
                                : `${selectedTable}.${r.target_column} = ${otherTable}.${r.source_column}`;
                        return `<option value="INNER JOIN ${escapeHtml(otherTable)} ON ${escapeHtml(
                            onCond
                        )}">INNER JOIN ${escapeHtml(otherTable)} (${escapeHtml(onCond)})</option>
                        <option value="LEFT JOIN ${escapeHtml(otherTable)} ON ${escapeHtml(
                            onCond
                        )}">LEFT JOIN ${escapeHtml(otherTable)}</option>`;
                    })
                    .join("");

            const colOpts = (tblObj.columns || [])
                .map(
                    (c) =>
                        `<option value="${escapeHtml(selectedTable)}.${escapeHtml(c.name)}">${escapeHtml(
                            c.name
                        )} (${escapeHtml(c.data_type)})</option>`
                )
                .join("");
            whereColSel.innerHTML = `<option value="">Sin filtro WHERE</option>` + colOpts;
            orderColSel.innerHTML = `<option value="">Orden natural</option>` + colOpts;
        };

        tblSel.onchange = updateDependentDropdowns;
        updateDependentDropdowns();
    }

    function renderSQLAutocompleteChips() {
        const container = document.getElementById("sql-autocomplete-chips");
        const textarea = document.getElementById("sql-code-textarea");
        if (!container || !textarea || !state.contract) return;

        const chips = (state.contract.tables || []).map((t) => t.name);
        container.innerHTML = chips
            .map(
                (name) =>
                    `<button type="button" class="pill-btn" data-insert-token="${escapeHtml(name)}">${escapeHtml(
                        name
                    )}</button>`
            )
            .join("");

        container.querySelectorAll("[data-insert-token]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const tok = btn.getAttribute("data-insert-token");
                if (sqlEditor) {
                    sqlEditor.insertTokenAtCursor(tok);
                }
            });
        });
    }

    async function refreshLiveSQLDecomposition() {
        const textarea = document.getElementById("sql-code-textarea");
        if (!textarea) return;
        try {
            const breakdown = await apiFetch("/api/query/decompose", {
                method: "POST",
                body: JSON.stringify({ sql: textarea.value }),
            });
            tutorCtrl.renderSQLBreakdown(breakdown);
        } catch (_err) {
            // Silenciar errores mientras el usuario escribe
        }
    }

    function renderInspectorSQLError(sqlErr, lineOffset = 0) {
        const container = document.getElementById("inspector-editor-container");
        if (!container || !sqlErr) return;
        const lang = state.lang || "es";
        const realLine = Math.max(1, Number(sqlErr.line || 1) + Number(lineOffset || 0));

        // Asegurar que el panel derecho esté visible y enfocado en el Inspector
        const rightPanel = document.getElementById("right-panel");
        const rightResizer = document.getElementById("resizer-right");
        if (rightPanel) rightPanel.classList.remove("panel-collapsed");
        if (rightResizer) rightResizer.classList.remove("panel-collapsed");
        activateRightTab("inspector");

        container.innerHTML = `
            <div class="inspector-error-card">
                <div class="inspector-error-header">
                    <h3 class="sidebar-heading" style="color:var(--accent-crimson);">${escapeHtml(t("errTitle", lang))}</h3>
                    <span class="inspector-error-badge">${escapeHtml(t("errLinePrefix", lang))} ${realLine}</span>
                </div>
                ${
                    sqlErr.rolled_back
                        ? `<div class="inspector-rollback-pill">${escapeHtml(t("errRollbackBadge", lang))}</div>`
                        : ""
                }
                <p style="font-size:12.5px; color:var(--text-primary); line-height:1.45;">
                    ${escapeHtml(sqlErr.raw_error || sqlErr.message || "")}
                </p>
                ${
                    sqlErr.hint
                        ? `<div style="font-size:12px; color:var(--text-secondary); line-height:1.45;">
                               <strong>${escapeHtml(t("errHintLabel", lang))}</strong><br>
                               ${escapeHtml(sqlErr.hint)}
                           </div>`
                        : ""
                }
                ${
                    sqlErr.statement
                        ? `<div>
                               <div style="font-size:11.5px; color:var(--text-muted); margin-bottom:4px;">${escapeHtml(t("errStmtLabel", lang))}</div>
                               <pre class="inspector-error-code">${escapeHtml(sqlErr.statement)}</pre>
                           </div>`
                        : ""
                }
                <button type="button" id="btn-jump-sql-error-line" class="btn btn-primary btn-sm">
                    ${escapeHtml(t("errJumpBtn", lang))} (${escapeHtml(t("errLinePrefix", lang))} ${realLine})
                </button>
            </div>
        `;

        const btnJump = document.getElementById("btn-jump-sql-error-line");
        if (btnJump) {
            btnJump.addEventListener("click", () => {
                activateCenterView("sql");
                activateSQLSubtab("dml");
                if (sqlEditor && typeof sqlEditor.jumpToLine === "function") {
                    sqlEditor.jumpToLine(realLine);
                }
            });
        }
    }

    async function executeSQLQuery(confirmedDangerous = false, targetPage = 1) {
        const textarea = document.getElementById("sql-code-textarea");
        if (!textarea || !state.contract) return;

        let sql = "";
        let startLineOffset = 0;
        let isSelection = false;
        if (confirmedDangerous) {
            sql = state.pendingDangerousSql;
        } else if (targetPage > 1 && state.sqlResults.lastSql) {
            sql = state.sqlResults.lastSql;
        } else if (sqlEditor && typeof sqlEditor.getSelectedOrAllText === "function") {
            const picked = sqlEditor.getSelectedOrAllText();
            sql = picked.text;
            isSelection = picked.isSelection;
            startLineOffset = picked.startLineOffset;
        } else {
            sql = textarea.value.trim();
        }
        if (!sql) return;
        if (isSelection) {
            showToast(t("errSelectionNotice", state.lang || "es"));
        }

        try {
            const res = await apiFetch("/api/query/execute", {
                method: "POST",
                body: JSON.stringify({
                    db_name: state.contract.db_name,
                    sql: sql,
                    confirmed_dangerous: confirmedDangerous,
                    page: targetPage,
                    page_size: state.sqlResults.pageSize || 100,
                }),
            });
            state.sqlResults.lastSql = sql;
            state.sqlResults.page = res.page || 1;
            state.sqlResults.totalPages = res.total_pages || 1;
            state.sqlResults.columns = res.columns || [];
            state.sqlResults.rows = res.rows || [];

            if (res.tutor_breakdown) {
                tutorCtrl.renderSQLBreakdown(res.tutor_breakdown);
            }

            if (res.blocked_by_shield) {
                state.pendingDangerousSql = sql;
                openDisasterShieldModal(res.shield_report);
                return;
            }

            if (res.schema_updated && res.schema_contract) {
                state.activeDbName = res.active_db_name || state.activeDbName;
                state.contract = res.schema_contract;
                if (res.ddl_previews) state.ddlPreviews = res.ddl_previews;
                if (res.databases) state.databases = res.databases;
                syncAllViews();
                if (res.switched_db) {
                    showToast(`Base de datos activa: ${res.switched_db}.db (Esquema y Lienzo ER sincronizados).`);
                } else {
                    showToast("Cambios DDL aplicados y sincronizados con el Lienzo ER y el Auditor.");
                }
            } else {
                await refreshDatabasesList();
            }

            renderSQLQueryResults(res);
        } catch (err) {
            const banner = document.getElementById("sql-explain-banner");
            const metrics = document.getElementById("sql-execution-metrics");
            const thead = document.getElementById("sql-results-thead");
            const tbody = document.getElementById("sql-results-tbody");
            const sqlErr = err.sqlError || {
                line: 1,
                message: err.message,
                raw_error: err.message,
                statement: sql.slice(0, 220),
                hint: "",
                rolled_back: false,
            };
            const realLine = Math.max(1, Number(sqlErr.line || 1) + startLineOffset);
            const displayMsg =
                startLineOffset > 0 && sqlErr.raw_error
                    ? `Error SQL (${t("errLinePrefix", state.lang)} ${realLine}): ${sqlErr.raw_error}`
                    : err.message;

            if (metrics) {
                metrics.textContent = `${t("errLinePrefix", state.lang)} ${realLine} · Error`;
            }
            if (banner) {
                banner.innerHTML = `<div class="explain-rec-row" style="border-color:var(--accent-crimson); background:var(--accent-crimson-tint); color:var(--text-primary);"><span>${escapeHtml(
                    displayMsg
                )}</span></div>`;
            }
            if (thead) thead.innerHTML = "";
            if (tbody) {
                tbody.innerHTML = `<tr><td style="padding:18px; color:var(--accent-crimson); white-space:normal;">${escapeHtml(
                    displayMsg
                )}</td></tr>`;
            }
            renderInspectorSQLError(sqlErr, startLineOffset);
            showToast(displayMsg);
        }
    }

    function renderSQLQueryResults(res) {
        const banner = document.getElementById("sql-explain-banner");
        const metrics = document.getElementById("sql-execution-metrics");
        const thead = document.getElementById("sql-results-thead");
        const tbody = document.getElementById("sql-results-tbody");

        if (metrics) {
            const pageNote =
                (res.total_pages || 1) > 1
                    ? ` · Pág. ${res.page || 1}/${res.total_pages}`
                    : "";
            metrics.textContent = `${res.row_count} filas${pageNote} · ${res.elapsed_ms} ms`;
        }

        const pagWrap = document.getElementById("sql-results-pagination");
        const pagInd = document.getElementById("sql-page-indicator");
        const btnExpCsv = document.getElementById("btn-sql-export-csv");
        const btnExpJson = document.getElementById("btn-sql-export-json");
        const hasRows = (res.columns || []).length > 0 && (res.rows || []).length > 0;
        if (pagWrap) {
            pagWrap.classList.toggle("hidden", (res.total_pages || 1) <= 1);
        }
        if (pagInd) {
            pagInd.textContent = `Pág. ${res.page || 1} / ${res.total_pages || 1}`;
        }
        if (btnExpCsv) btnExpCsv.classList.toggle("hidden", !hasRows);
        if (btnExpJson) btnExpJson.classList.toggle("hidden", !hasRows);

        if (banner) {
            const plans = res.explain_plan || [];
            const recs = res.index_recommendations || [];
            let html = "";

            if (plans.length > 0) {
                const planSteps = plans.map((p) => escapeHtml(p.detail)).join(" -> ");
                html += `<div style="font-family:var(--font-mono); font-size:12px; color:var(--text-secondary);"><strong>EXPLAIN QUERY PLAN:</strong> ${planSteps}</div>`;
            }

            recs.forEach((rec) => {
                html += `
                    <div class="explain-rec-row">
                        <span>${escapeHtml(rec.message)}</span>
                        ${
                            rec.column
                                ? `<button type="button" class="btn btn-primary btn-sm" data-create-idx-tbl="${escapeHtml(
                                      rec.table
                                  )}" data-create-idx-col="${escapeHtml(rec.column)}">
                                    Crear Índice ${escapeHtml(rec.index_name)}
                                  </button>`
                                : ""
                        }
                    </div>
                `;
            });

            banner.innerHTML = html;

            banner.querySelectorAll("[data-create-idx-tbl]").forEach((btn) => {
                btn.addEventListener("click", async () => {
                    const tbl = btn.getAttribute("data-create-idx-tbl");
                    const col = btn.getAttribute("data-create-idx-col");
                    try {
                        const idxRes = await apiFetch("/api/index/create", {
                            method: "POST",
                            body: JSON.stringify({
                                db_name: state.contract.db_name,
                                table_name: tbl,
                                column_name: col,
                                schema_contract: state.contract,
                            }),
                        });
                        state.contract = idxRes.schema_contract;
                        state.ddlPreviews = idxRes.ddl_previews;
                        syncAllViews();
            erCanvas.fitToViewport();
                        showToast(`Índice '${idxRes.index_name}' creado en SQLite. Re-ejecutando consulta...`);
                        await executeSQLQuery(false);
                    } catch (err) {
                        showToast(err.message);
                    }
                });
            });
        }

        if (!thead || !tbody) return;
        const cols = res.columns || [];
        if (cols.length === 0) {
            thead.innerHTML = "";
            const logLines = (res.execution_log || []).length > 0
                ? res.execution_log.map((l) => `<div>${escapeHtml(l)}</div>`).join("")
                : `<div>Operación ejecutada correctamente. Filas afectadas: ${res.row_count} (${res.elapsed_ms} ms).</div>`;
            tbody.innerHTML = `<tr><td style="padding:16px; color:var(--accent-emerald); white-space:normal; line-height:1.6;">${logLines}</td></tr>`;
            return;
        }

        thead.innerHTML = `<tr>${cols.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr>`;
        tbody.innerHTML = (res.rows || [])
            .map(
                (r) =>
                    `<tr>${cols
                        .map((c) => {
                            const v = r[c];
                            if (v === null || v === undefined) {
                                return '<td><span class="cell-null">NULL</span></td>';
                            }
                            const cls = typeof v === "number" ? ' class="cell-num"' : "";
                            return `<td${cls}>${escapeHtml(v)}</td>`;
                        })
                        .join("")}</tr>`
            )
            .join("");
    }

    function openDisasterShieldModal(report) {
        const modal = document.getElementById("disaster-shield-modal");
        if (!modal) return;
        document.getElementById("shield-modal-title").textContent = report.title || "Ejecución Interceptada";
        document.getElementById("shield-modal-reason").textContent = report.reason || "";
        document.getElementById("shield-affected-rows").textContent = String(report.affected_rows || 0);
        document.getElementById("shield-dependent-rows").textContent = String(report.total_dependent_rows || 0);
        document.getElementById("shield-safe-sql").textContent = report.safe_alternative || "";

        const depList = document.getElementById("shield-dependencies-list");
        const deps = report.dependent_tables || [];
        if (depList) {
            if (deps.length === 0) {
                depList.innerHTML = "";
            } else {
                depList.innerHTML = `
                    <div class="inspector-card">
                        <strong style="font-size:12px;">Impacto en Tablas Relacionadas por Clave Foránea:</strong>
                        ${deps
                            .map(
                                (d) =>
                                    `<div style="font-size:12px; color:var(--text-secondary);">• Tabla hija <code>${escapeHtml(
                                        d.child_table
                                    )}.${escapeHtml(d.fk_column)}</code>: <strong>${
                                        d.dependent_rows
                                    } registros dependientes</strong> (Política: <code>ON DELETE ${escapeHtml(
                                        d.on_delete_policy
                                    )}</code>)</div>`
                            )
                            .join("")}
                    </div>
                `;
            }
        }

        modal.classList.remove("hidden");
    }

    /* ======================================================================
       Eventos Globales, Vistas, Modales y Divisores Redimensionables
       ====================================================================== */
    function setMode(mode, silent = false) {
        state.mode = mode;
        writeStorage(STORAGE_KEYS.mode, mode);
        document.body.setAttribute("data-app-mode", mode);
        const modeEl = document.getElementById("status-mode-label");
        if (modeEl) modeEl.textContent = mode === "tutor" ? "Modo Tutor" : "Modo Estándar";
        document.getElementById("btn-mode-standard").classList.toggle("active", mode === "standard");
        document.getElementById("btn-mode-tutor").classList.toggle("active", mode === "tutor");
        tutorCtrl.setTutorMode(mode === "tutor", state.contract, state.selectedElement);
        renderAuditorAlerts();

        if (mode === "standard") {
            // Ocultar pestañas exclusivas del Modo Tutor si estaban abiertas
            const activeLeft = document.querySelector("[data-left-tab].active");
            if (activeLeft && activeLeft.getAttribute("data-left-tab") === "tutor-challenges") {
                const defaultLeft = document.querySelector('[data-left-tab="explorer-tree"]');
                if (defaultLeft) defaultLeft.click();
            }
            const activeRight = document.querySelector("[data-right-tab].active");
            if (activeRight && activeRight.getAttribute("data-right-tab") === "tutor") {
                activateRightTab("auditor");
            }
        } else {
            refreshLiveSQLDecomposition();
            if (!silent) {
                showToast("Modo Tutor activado: retos guiados, desglosador SQL y lecciones Antes/Después habilitados.");
            }
        }
    }

    function activateCenterView(viewName) {
        document.querySelectorAll("[data-center-view]").forEach((btn) => {
            btn.classList.toggle("active", btn.getAttribute("data-center-view") === viewName);
        });
        document.getElementById("view-canvas").classList.toggle("active", viewName === "canvas");
        const relPane = document.getElementById("view-relational");
        if (relPane) relPane.classList.toggle("active", viewName === "relational");
        document.getElementById("view-explorer").classList.toggle("active", viewName === "explorer");
        document.getElementById("view-sql").classList.toggle("active", viewName === "sql");

        if (viewName === "relational" && relDiagram && state.contract) {
            relDiagram.render(state.contract);
            setTimeout(() => relDiagram.fitToViewport(), 30);
        }
        if (viewName === "explorer" && state.contract && state.contract.is_deployed) {
            loadExplorerTableRows();
        }
        if (viewName === "sql") {
            activateSQLSubtab(state.activeSqlSubtab || "ddl");
        }
    }

    function activateRightTab(tabName) {
        const validTab = ["auditor", "inspector", "tutor"].includes(tabName) ? tabName : "auditor";
        document.querySelectorAll("[data-right-tab]").forEach((btn) => {
            btn.classList.toggle("active", btn.getAttribute("data-right-tab") === validTab);
        });
        ["auditor", "inspector", "tutor"].forEach((t) => {
            const el = document.getElementById(`right-tab-${t}`);
            if (el) el.classList.toggle("active", t === validTab);
        });
    }

    function bindGlobalControls() {
        document.getElementById("btn-mode-standard").addEventListener("click", () => setMode("standard"));
        document.getElementById("btn-mode-tutor").addEventListener("click", () => setMode("tutor"));

        document.getElementById("btn-theme-toggle").addEventListener("click", () => {
            state.theme = state.theme === "dark" ? "light" : "dark";
            document.documentElement.setAttribute("data-theme", state.theme);
            writeStorage(STORAGE_KEYS.theme, state.theme);
            const themeEl = document.getElementById("status-theme-label");
            if (themeEl) themeEl.textContent = state.theme === "light" ? "Tema Claro" : "Tema Oscuro";
        });

        const btnLangToggle = document.getElementById("btn-lang-toggle");
        if (btnLangToggle) {
            btnLangToggle.addEventListener("click", () => {
                state.lang = state.lang === "en" ? "es" : "en";
                writeStorage(LANG_STORAGE_KEY, state.lang);
                applyLanguageToDOM(state.lang);
                showToast(state.lang === "en" ? "Language switched to English." : "Idioma cambiado a Español.");
            });
        }

        const statusAudBtn = document.getElementById("status-auditor-btn");
        if (statusAudBtn) {
            statusAudBtn.addEventListener("click", () => {
                const rightPanel = document.getElementById("right-panel");
                const rightResizer = document.getElementById("resizer-right");
                if (rightPanel) rightPanel.classList.remove("panel-collapsed");
                if (rightResizer) rightResizer.classList.remove("panel-collapsed");
                activateRightTab("auditor");
            });
        }

        const toggleNlpBar = (forceHidden = null) => {
            const bar = document.getElementById("nlp-command-bar");
            const btn = document.getElementById("btn-toggle-nlp-bar");
            if (!bar) return;
            const shouldHide = forceHidden !== null ? forceHidden : !bar.classList.contains("hidden");
            bar.classList.toggle("hidden", shouldHide);
            document.body.classList.toggle("nlp-collapsed", shouldHide);
            if (btn) {
                btn.classList.toggle("active", !shouldHide);
                btn.setAttribute("aria-expanded", String(!shouldHide));
            }
            if (!shouldHide) {
                const promptEl = document.getElementById("nlp-prompt-input");
                if (promptEl) promptEl.focus();
            }
        };

        document.getElementById("btn-toggle-nlp-bar").addEventListener("click", () => toggleNlpBar());
        const btnCloseNlp = document.getElementById("btn-close-nlp-bar");
        if (btnCloseNlp) {
            btnCloseNlp.addEventListener("click", () => toggleNlpBar(true));
        }

        document.getElementById("project-select").addEventListener("change", (e) => {
            const val = e.target.value;
            if (val) loadDatabaseProject(val);
        });

        document.getElementById("btn-run-nlp-inference").addEventListener("click", () => runNLPInference());
        document.getElementById("btn-approve-deploy").addEventListener("click", () => approveAndDeploySchema());

        document.getElementById("btn-generate-mock").addEventListener("click", async () => {
            if (!state.contract) return;
            if (!state.contract.is_deployed) {
                await approveAndDeploySchema();
                return;
            }
            try {
                const res = await apiFetch(
                    `/api/databases/${encodeURIComponent(state.contract.db_name)}/mock`,
                    {
                        method: "POST",
                        body: JSON.stringify({
                            db_name: state.contract.db_name,
                            rows_per_table: 10,
                        }),
                    }
                );
                state.databases = res.databases || state.databases;
                renderDatabasesSidebar();
                await loadExplorerTableRows();
                showToast(`Mock Data generado: +${res.total_inserted} registros sintéticos coherentes insertados.`);
            } catch (err) {
                showToast(err.message);
            }
        });

        // Plantillas NLP rápidas
        document.querySelectorAll("[data-preset]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const key = btn.getAttribute("data-preset");
                const preset = NLP_PRESETS[key];
                if (!preset) return;
                document.getElementById("nlp-prompt-input").value = preset.text;
                document.getElementById("nlp-db-name-input").value = preset.db_name;
                runNLPInference();
            });
        });

        // Pestañas del panel izquierdo
        document.querySelectorAll("[data-left-tab]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const target = btn.getAttribute("data-left-tab");
                document.querySelectorAll("[data-left-tab]").forEach((b) =>
                    b.classList.toggle("active", b === btn)
                );
                ["explorer-tree", "tutor-challenges", "version-history"].forEach((t) => {
                    const pane = document.getElementById(`left-tab-${t}`);
                    if (pane) pane.classList.toggle("active", t === target);
                });
            });
        });

        // Pestañas centrales
        document.querySelectorAll("[data-center-view]").forEach((btn) => {
            btn.addEventListener("click", () => {
                activateCenterView(btn.getAttribute("data-center-view"));
            });
        });

        // Pestañas del panel derecho
        document.querySelectorAll("[data-right-tab]").forEach((btn) => {
            btn.addEventListener("click", () => {
                activateRightTab(btn.getAttribute("data-right-tab"));
            });
        });

        document.getElementById("btn-telemetry-alerts").addEventListener("click", () => {
            const rightPanel = document.getElementById("right-panel");
            const rightResizer = document.getElementById("resizer-right");
            if (rightPanel) rightPanel.classList.remove("panel-collapsed");
            if (rightResizer) rightResizer.classList.remove("panel-collapsed");
            activateRightTab("auditor");
        });

        // Botones para plegar/desplegar paneles laterales en pantalla dividida
        const btnToggleLeft = document.getElementById("btn-toggle-left-panel");
        const btnToggleRight = document.getElementById("btn-toggle-right-panel");
        if (btnToggleLeft) {
            btnToggleLeft.addEventListener("click", () => {
                document.getElementById("left-panel").classList.toggle("panel-collapsed");
                document.getElementById("resizer-left").classList.toggle("panel-collapsed");
                setTimeout(() => erCanvas.fitToViewport(), 40);
            });
        }
        if (btnToggleRight) {
            btnToggleRight.addEventListener("click", () => {
                document.getElementById("right-panel").classList.toggle("panel-collapsed");
                document.getElementById("resizer-right").classList.toggle("panel-collapsed");
                setTimeout(() => erCanvas.fitToViewport(), 40);
            });
        }

        // Sub-pestañas del Editor SQL Dual (Estructura DDL vs Consultas DML)
        document.querySelectorAll("[data-sql-subtab]").forEach((btn) => {
            btn.addEventListener("click", () => {
                activateSQLSubtab(btn.getAttribute("data-sql-subtab"));
            });
        });

        // Controles de la Vista Diagrama Relacional (Conceptual Chen <-> Paso a Tablas)
        document.querySelectorAll("[data-reldiag-mode]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const mode = btn.getAttribute("data-reldiag-mode");
                document.querySelectorAll("[data-reldiag-mode]").forEach((b) =>
                    b.classList.toggle("active", b === btn)
                );
                const btnToggleAttrs = document.getElementById("btn-reldiag-toggle-attrs");
                if (btnToggleAttrs) {
                    btnToggleAttrs.classList.toggle("hidden", mode !== "chen");
                }
                if (relDiagram) relDiagram.setSubmode(mode);
            });
        });

        const btnRelToggleAttrs = document.getElementById("btn-reldiag-toggle-attrs");
        if (btnRelToggleAttrs) {
            btnRelToggleAttrs.addEventListener("click", () => {
                if (!relDiagram) return;
                const showing = relDiagram.toggleAttributes();
                btnRelToggleAttrs.textContent = showing ? "Ocultar Atributos" : "Mostrar Atributos";
            });
        }
        const btnRelReset = document.getElementById("btn-reldiag-reset");
        if (btnRelReset) btnRelReset.addEventListener("click", () => relDiagram && relDiagram.resetLayout());
        const btnRelSvg = document.getElementById("btn-reldiag-export-svg");
        if (btnRelSvg) btnRelSvg.addEventListener("click", () => relDiagram && relDiagram.exportSVG());
        const btnRelPng = document.getElementById("btn-reldiag-export-png");
        if (btnRelPng) btnRelPng.addEventListener("click", () => relDiagram && relDiagram.exportPNG());
        const btnRelZOut = document.getElementById("btn-reldiag-zoom-out");
        if (btnRelZOut) btnRelZOut.addEventListener("click", () => relDiagram && relDiagram.setZoom(relDiagram.zoom - 0.15));
        const btnRelZIn = document.getElementById("btn-reldiag-zoom-in");
        if (btnRelZIn) btnRelZIn.addEventListener("click", () => relDiagram && relDiagram.setZoom(relDiagram.zoom + 0.15));
        const btnRelFit = document.getElementById("btn-reldiag-fit");
        if (btnRelFit) btnRelFit.addEventListener("click", () => relDiagram && relDiagram.fitToViewport());

        // Selector de dialecto DDL
        document.querySelectorAll("[data-dialect]").forEach((btn) => {
            btn.addEventListener("click", () => {
                state.activeDialect = btn.getAttribute("data-dialect");
                document.querySelectorAll("[data-dialect]").forEach((b) =>
                    b.classList.toggle("active", b === btn)
                );
                renderDDLPreview();
            });
        });

        const btnApplyDdlEdits = document.getElementById("btn-apply-ddl-edits");
        if (btnApplyDdlEdits) {
            btnApplyDdlEdits.addEventListener("click", () => applyDDLEditsToSchema());
        }

        const btnCopyDdl = document.getElementById("btn-copy-ddl");
        if (btnCopyDdl) {
            btnCopyDdl.addEventListener("click", () => {
                const ddl =
                    (ddlEditor && ddlEditor.getValue()) ||
                    state.ddlPreviews[state.activeDialect] ||
                    "";
                navigator.clipboard.writeText(ddl).then(() => {
                    showToast(`Código DDL (${state.activeDialect.toUpperCase()}) copiado al portapapeles.`);
                });
            });
        }

        const btnDownloadDdl = document.getElementById("btn-download-ddl");
        if (btnDownloadDdl) {
            btnDownloadDdl.addEventListener("click", () => downloadDDLScript());
        }

        // Añadir nueva tabla desde el lienzo o barra lateral
        const addTableHandler = () => {
            if (!state.contract) return;
            const idx = state.contract.tables.length + 1;
            const newName = `nueva_entidad_${idx}`;
            const newTbl = {
                name: newName,
                description: "Tabla añadida visualmente en el lienzo ER",
                is_associative: false,
                is_historical: false,
                position_x: 100 + (idx % 3) * 320,
                position_y: 100 + Math.floor(idx / 3) * 260,
                columns: [
                    {
                        name: "id",
                        data_type: "INTEGER",
                        nullable: false,
                        is_pk: true,
                        is_fk: false,
                        is_unique: false,
                        auto_increment: true,
                        description: "Identificador único subrogado",
                        tutor_explanation: "Clave primaria autoincremental.",
                    },
                    {
                        name: "nombre",
                        data_type: "VARCHAR",
                        length: 150,
                        nullable: false,
                        is_pk: false,
                        is_fk: false,
                        is_unique: false,
                        auto_increment: false,
                        description: "Nombre descriptivo",
                        tutor_explanation: "Atributo nominal principal.",
                    },
                ],
                indexes: [],
                tutor_explanation: `Entidad '${newName}' creada directamente en el lienzo.`,
            };
            state.contract.tables.push(newTbl);
            state.selectedElement = { type: "table", table: newName, data: newTbl };
            activateRightTab("inspector");
            handleLocalSchemaMutation(state.contract, true);
        };

        const btnCanvasAddTable = document.getElementById("btn-canvas-add-table");
        if (btnCanvasAddTable) btnCanvasAddTable.addEventListener("click", addTableHandler);

        const btnCanvasUndo = document.getElementById("btn-canvas-undo");
        const btnCanvasRedo = document.getElementById("btn-canvas-redo");
        if (btnCanvasUndo) btnCanvasUndo.addEventListener("click", () => performSchemaUndo());
        if (btnCanvasRedo) btnCanvasRedo.addEventListener("click", () => performSchemaRedo());

        window.addEventListener("keydown", (e) => {
            const tag = (e.target && e.target.tagName) || "";
            if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
            if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === "z") {
                if (undoManager.canUndo()) {
                    e.preventDefault();
                    performSchemaUndo();
                }
            } else if (
                (e.ctrlKey || e.metaKey) &&
                (e.key.toLowerCase() === "y" || (e.shiftKey && e.key.toLowerCase() === "z"))
            ) {
                if (undoManager.canRedo()) {
                    e.preventDefault();
                    performSchemaRedo();
                }
            }
        });

        document.getElementById("btn-close-fk-popover").addEventListener("click", () => {
            document.getElementById("fk-preview-popover").classList.add("hidden");
        });
    }

    function bindExplorerControls() {
        const btnExpCsv = document.getElementById("btn-explorer-export-csv");
        const btnExpJson = document.getElementById("btn-explorer-export-json");
        const btnExpSql = document.getElementById("btn-explorer-export-sql");
        if (btnExpCsv) btnExpCsv.addEventListener("click", () => exportExplorerTable(state, "csv"));
        if (btnExpJson) btnExpJson.addEventListener("click", () => exportExplorerTable(state, "json"));
        if (btnExpSql) btnExpSql.addEventListener("click", () => exportExplorerTable(state, "sql"));

        const searchInput = document.getElementById("explorer-search-input");
        let timer = null;
        searchInput.addEventListener("input", () => {
            clearTimeout(timer);
            timer = setTimeout(() => {
                state.explorer.search = searchInput.value;
                state.explorer.page = 1;
                loadExplorerTableRows();
            }, 220);
        });

        document.getElementById("btn-page-prev").addEventListener("click", () => {
            if (state.explorer.page > 1) {
                state.explorer.page--;
                loadExplorerTableRows();
            }
        });
        document.getElementById("btn-page-next").addEventListener("click", () => {
            if (state.explorer.page < state.explorer.totalPages) {
                state.explorer.page++;
                loadExplorerTableRows();
            }
        });

        const drawer = document.getElementById("explorer-insert-drawer");
        const fieldsBox = document.getElementById("insert-drawer-fields");

        document.getElementById("btn-explorer-add-row").addEventListener("click", () => {
            if (!state.explorer.columns.length) return;
            drawer.classList.remove("hidden");
            document.getElementById("insert-drawer-title").textContent = `Insertar en '${state.explorer.activeTable}'`;
            fieldsBox.innerHTML = state.explorer.columns
                .filter((c) => !(c.is_pk && c.auto_increment))
                .map(
                    (c) => `
                    <div class="form-row">
                        <label>${escapeHtml(c.name)} (${escapeHtml(c.data_type)})</label>
                        <input type="text" class="control-input-sm" data-insert-col="${escapeHtml(
                            c.name
                        )}" placeholder="${c.is_fk ? `ID de ${escapeHtml(c.fk_target_table)}` : ""}">
                    </div>
                `
                )
                .join("");
        });

        document.getElementById("btn-close-insert-drawer").addEventListener("click", () => {
            drawer.classList.add("hidden");
        });

        document.getElementById("btn-confirm-insert-row").addEventListener("click", async () => {
            const values = {};
            fieldsBox.querySelectorAll("[data-insert-col]").forEach((inp) => {
                const k = inp.getAttribute("data-insert-col");
                if (inp.value.trim() !== "") {
                    values[k] = inp.value.trim();
                }
            });
            try {
                await apiFetch("/api/explorer/row", {
                    method: "POST",
                    body: JSON.stringify({
                        db_name: state.contract.db_name,
                        table_name: state.explorer.activeTable,
                        values: values,
                    }),
                });
                drawer.classList.add("hidden");
                showToast("Nuevo registro insertado en SQLite.");
                await loadExplorerTableRows();
            } catch (err) {
                showToast(err.message);
            }
        });
    }

    function updateActiveSQLFilenameUI() {
        const pill = document.getElementById("active-sql-filename");
        if (!pill) return;
        pill.textContent = state.activeSqlFile.filename || "consulta_actual.sql";
        pill.title = state.activeSqlFile.path || "Archivo SQL aún sin guardar en disco";
    }

    async function saveCurrentSQLFile(saveAs = false) {
        const code = sqlEditor ? sqlEditor.getValue() : (document.getElementById("sql-code-textarea")?.value || "");
        try {
            const res = await apiFetch("/api/files/save-sql", {
                method: "POST",
                body: JSON.stringify({
                    content: code,
                    path: state.activeSqlFile.path,
                    filename: state.activeSqlFile.filename || `${state.activeDbName || "script"}.sql`,
                    save_as: saveAs,
                }),
            });
            if (res.saved) {
                state.activeSqlFile = { filename: res.filename, path: res.path };
                updateActiveSQLFilenameUI();
                showToast(`Archivo SQL guardado: ${res.path}`);
            }
        } catch (err) {
            showToast(err.message);
        }
    }

    function bindSQLEditorControls() {
        document.getElementById("btn-execute-sql").addEventListener("click", () => executeSQLQuery(false, 1));

        const btnSqlPrev = document.getElementById("btn-sql-page-prev");
        const btnSqlNext = document.getElementById("btn-sql-page-next");
        const btnSqlCsv = document.getElementById("btn-sql-export-csv");
        const btnSqlJson = document.getElementById("btn-sql-export-json");
        if (btnSqlPrev) {
            btnSqlPrev.addEventListener("click", () => {
                if (state.sqlResults.page > 1) executeSQLQuery(false, state.sqlResults.page - 1);
            });
        }
        if (btnSqlNext) {
            btnSqlNext.addEventListener("click", () => {
                if (state.sqlResults.page < state.sqlResults.totalPages) {
                    executeSQLQuery(false, state.sqlResults.page + 1);
                }
            });
        }
        if (btnSqlCsv) btnSqlCsv.addEventListener("click", () => exportSQLResults(state, "csv"));
        if (btnSqlJson) btnSqlJson.addEventListener("click", () => exportSQLResults(state, "json"));

        const btnNewSql = document.getElementById("btn-new-sql-file");
        const btnOpenSql = document.getElementById("btn-open-sql-file");
        const btnSaveSql = document.getElementById("btn-save-sql-file");
        const btnSaveSqlAs = document.getElementById("btn-save-sql-as");

        if (btnNewSql) {
            btnNewSql.addEventListener("click", () => {
                state.activeSqlFile = {
                    filename: `${state.activeDbName || "nuevo"}_script.sql`,
                    path: null,
                };
                updateActiveSQLFilenameUI();
                setSQLCodeValue("-- Nuevo script SQL\n-- Usa Ctrl+Espacio para autocompletar o Ctrl+Enter para ejecutar\n\n");
                const ta = document.getElementById("sql-code-textarea");
                if (ta) ta.focus();
                showToast("Nuevo script SQL creado en blanco.");
            });
        }

        if (btnOpenSql) {
            btnOpenSql.addEventListener("click", async () => {
                try {
                    const res = await apiFetch("/api/files/open-sql", { method: "POST" });
                    if (res.opened) {
                        state.activeSqlFile = { filename: res.filename, path: res.path };
                        updateActiveSQLFilenameUI();
                        setSQLCodeValue(res.content || "");
                        showToast(`Archivo SQL abierto: ${res.filename}`);
                    }
                } catch (err) {
                    showToast(err.message);
                }
            });
        }

        if (btnSaveSql) {
            btnSaveSql.addEventListener("click", () => saveCurrentSQLFile(false));
        }
        if (btnSaveSqlAs) {
            btnSaveSqlAs.addEventListener("click", () => saveCurrentSQLFile(true));
        }

        document.getElementById("btn-apply-guided-sql").addEventListener("click", () => {
            const tbl = document.getElementById("qb-table").value;
            const joinClause = document.getElementById("qb-join").value;
            const whereCol = document.getElementById("qb-where-col").value;
            const whereOp = document.getElementById("qb-where-op").value;
            const whereVal = document.getElementById("qb-where-val").value.trim();
            const orderCol = document.getElementById("qb-order-col").value;
            const orderDir = document.getElementById("qb-order-dir").value;

            if (!tbl) return;
            const lines = [`SELECT *`, `FROM ${tbl}`];
            if (joinClause) lines.push(joinClause);
            if (whereCol && whereVal) {
                const formattedVal =
                    whereOp === "LIKE"
                        ? `'%${whereVal}%'`
                        : /^-?\d+(\.\d+)?$/.test(whereVal)
                        ? whereVal
                        : `'${whereVal}'`;
                lines.push(`WHERE ${whereCol} ${whereOp} ${formattedVal}`);
            }
            if (orderCol) {
                lines.push(`ORDER BY ${orderCol} ${orderDir}`);
            }
            lines.push(`LIMIT 25;`);
            setSQLCodeValue(lines.join("\n"));
            refreshLiveSQLDecomposition();
            executeSQLQuery(false);
        });

        // Presets de consultas SQL
        document.querySelectorAll("[data-sql-preset]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const preset = btn.getAttribute("data-sql-preset");
                const tables = (state.contract && state.contract.tables) || [];
                const firstTbl = tables[0] ? tables[0].name : "clientes";

                if (preset === "join_complete") {
                    if (state.contract.db_name === "taller_mecanico") {
                        setSQLCodeValue(
                            "SELECT c.nombre AS cliente, v.matricula, v.marca, r.codigo AS orden, r.total\nFROM clientes c\nINNER JOIN vehiculos v ON c.id = v.cliente_id\nINNER JOIN reparaciones r ON v.id = r.vehiculo_id\nORDER BY r.total DESC\nLIMIT 20;"
                        );
                    } else if (state.contract.relations && state.contract.relations.length > 0) {
                        const r = state.contract.relations[0];
                        setSQLCodeValue(
                            `SELECT a.*, b.*\nFROM ${r.target_table} a\nINNER JOIN ${r.source_table} b ON a.${r.target_column} = b.${r.source_column}\nLIMIT 20;`
                        );
                    }
                    executeSQLQuery(false);
                } else if (preset === "group_summary") {
                    if (state.contract.db_name === "taller_mecanico") {
                        setSQLCodeValue(
                            "SELECT c.nombre AS cliente, COUNT(v.id) AS total_vehiculos\nFROM clientes c\nLEFT JOIN vehiculos v ON c.id = v.cliente_id\nGROUP BY c.nombre\nORDER BY total_vehiculos DESC;"
                        );
                    } else {
                        setSQLCodeValue(`SELECT COUNT(*) AS total_registros\nFROM ${firstTbl};`);
                    }
                    executeSQLQuery(false);
                } else if (preset === "full_scan_test") {
                    if (state.contract.db_name === "taller_mecanico") {
                        setSQLCodeValue(
                            "SELECT * FROM vehiculos WHERE marca = 'Toyota' ORDER BY kilometraje DESC;"
                        );
                    } else {
                        const secondCol =
                            tables[0] && tables[0].columns[1] ? tables[0].columns[1].name : "id";
                        setSQLCodeValue(`SELECT * FROM ${firstTbl} WHERE ${secondCol} IS NOT NULL;`);
                    }
                    executeSQLQuery(false);
                } else if (preset === "disaster_delete") {
                    setSQLCodeValue(`DELETE FROM ${firstTbl};`);
                    executeSQLQuery(false);
                }
            });
        });
    }

    function bindRelationModal() {
        const modal = document.getElementById("relation-builder-modal");
        const parentSel = document.getElementById("rel-parent-table");
        const childSel = document.getElementById("rel-child-table");

        document.getElementById("btn-canvas-add-relation").addEventListener("click", () => {
            if (!state.contract || state.contract.tables.length < 2) {
                showToast("Se necesitan al menos 2 tablas en el lienzo para crear una relación.");
                return;
            }
            const opts = state.contract.tables
                .map((t) => `<option value="${escapeHtml(t.name)}">${escapeHtml(t.name)}</option>`)
                .join("");
            parentSel.innerHTML = opts;
            childSel.innerHTML = opts;
            if (state.contract.tables.length > 1) {
                childSel.selectedIndex = 1;
            }
            modal.classList.remove("hidden");
        });

        const closeModal = () => modal.classList.add("hidden");
        document.getElementById("btn-close-rel-modal").addEventListener("click", closeModal);
        document.getElementById("btn-cancel-rel-modal").addEventListener("click", closeModal);

        document.getElementById("btn-confirm-rel-modal").addEventListener("click", () => {
            const parentName = parentSel.value;
            const childName = childSel.value;
            const card = document.getElementById("rel-cardinality").value;
            const onDel = document.getElementById("rel-on-delete").value;

            if (parentName === childName) {
                showToast("Selecciona dos tablas distintas para vincular.");
                return;
            }

            if (card === "N:M") {
                const leftSing = parentName.replace(/es$/, "").replace(/s$/, "");
                const rightSing = childName.replace(/es$/, "").replace(/s$/, "");
                const assocName = `${leftSing}_${childName}`;
                const leftFk = `${leftSing}_id`;
                const rightFk = `${rightSing}_id`;

                if (!state.contract.tables.some((t) => t.name === assocName)) {
                    state.contract.tables.push({
                        name: assocName,
                        description: `Tabla asociativa intermedia que resuelve la relación N:M entre '${parentName}' y '${childName}'.`,
                        is_associative: true,
                        is_historical: false,
                        position_x: 160,
                        position_y: 310,
                        columns: [
                            {
                                name: "id",
                                data_type: "INTEGER",
                                nullable: false,
                                is_pk: true,
                                is_fk: false,
                                is_unique: false,
                                auto_increment: true,
                                description: `Identificador único de ${assocName}`,
                                tutor_explanation: "Clave primaria subrogada de la tabla intermedia.",
                            },
                            {
                                name: leftFk,
                                data_type: "INTEGER",
                                nullable: false,
                                is_pk: false,
                                is_fk: true,
                                is_unique: false,
                                auto_increment: false,
                                fk_target_table: parentName,
                                fk_target_column: "id",
                                description: `Referencia a ${parentName}.id`,
                                tutor_explanation: `Clave foránea hacia '${parentName}'.`,
                            },
                            {
                                name: rightFk,
                                data_type: "INTEGER",
                                nullable: false,
                                is_pk: false,
                                is_fk: true,
                                is_unique: false,
                                auto_increment: false,
                                fk_target_table: childName,
                                fk_target_column: "id",
                                description: `Referencia a ${childName}.id`,
                                tutor_explanation: `Clave foránea hacia '${childName}'.`,
                            },
                        ],
                        indexes: [leftFk, rightFk],
                        tutor_explanation: `Tabla intermedia creada para resolver la relación Muchos-a-Muchos entre '${parentName}' y '${childName}'.`,
                    });
                }

                state.contract.relations.push({
                    id: `rel_${assocName}_${parentName}_${Date.now()}`,
                    source_table: assocName,
                    source_column: leftFk,
                    target_table: parentName,
                    target_column: "id",
                    cardinality: "N:M",
                    on_delete: onDel,
                    on_update: "CASCADE",
                    via_table: assocName,
                    tutor_explanation: `Vincula '${assocName}' con '${parentName}' en la relación N:M.`,
                });
                state.contract.relations.push({
                    id: `rel_${assocName}_${childName}_${Date.now() + 1}`,
                    source_table: assocName,
                    source_column: rightFk,
                    target_table: childName,
                    target_column: "id",
                    cardinality: "N:M",
                    on_delete: onDel,
                    on_update: "CASCADE",
                    via_table: assocName,
                    tutor_explanation: `Vincula '${assocName}' con '${childName}' en la relación N:M.`,
                });
            } else {
                const fkName = `${parentName.replace(/s$/, "")}_id`;
                const childTbl = state.contract.tables.find((t) => t.name === childName);
                if (childTbl && !childTbl.columns.some((c) => c.name === fkName)) {
                    childTbl.columns.splice(1, 0, {
                        name: fkName,
                        data_type: "INTEGER",
                        nullable: false,
                        is_pk: false,
                        is_fk: true,
                        is_unique: card === "1:1",
                        auto_increment: false,
                        fk_target_table: parentName,
                        fk_target_column: "id",
                        description: `Clave foránea hacia ${parentName}.id`,
                        tutor_explanation: `Conecta cada fila de '${childName}' con '${parentName}'.`,
                    });
                }

                state.contract.relations.push({
                    id: `rel_${childName}_${parentName}_${Date.now()}`,
                    source_table: childName,
                    source_column: fkName,
                    target_table: parentName,
                    target_column: "id",
                    cardinality: card,
                    on_delete: onDel,
                    on_update: "CASCADE",
                    tutor_explanation: `Relación ${card} definida visualmente con política ON DELETE ${onDel}.`,
                });
            }

            closeModal();
            handleLocalSchemaMutation(state.contract, true);
        });
    }

    function bindShieldModal() {
        const modal = document.getElementById("disaster-shield-modal");
        const closeShield = () => modal.classList.add("hidden");

        document.getElementById("btn-shield-cancel").addEventListener("click", closeShield);

        document.getElementById("btn-shield-use-safe").addEventListener("click", () => {
            const safeSql = document.getElementById("shield-safe-sql").textContent;
            if (safeSql) {
                setSQLCodeValue(safeSql);
                refreshLiveSQLDecomposition();
            }
            closeShield();
            showToast("Alternativa segura con cláusula WHERE cargada en el editor.");
        });

        document.getElementById("btn-shield-force").addEventListener("click", async () => {
            closeShield();
            await executeSQLQuery(true);
        });
    }

    let pendingDeleteCallback = null;

    function openConfirmDeleteModal(title, message, onConfirm) {
        const modal = document.getElementById("confirm-delete-modal");
        if (!modal) return;
        document.getElementById("confirm-del-title").textContent = title;
        document.getElementById("confirm-del-message").textContent = message;
        pendingDeleteCallback = onConfirm;
        modal.classList.remove("hidden");
    }

    function requestDeleteTable(tableName) {
        if (!state.contract) return;
        const relCount = (state.contract.relations || []).filter(
            (r) => r.source_table === tableName || r.target_table === tableName
        ).length;
        const msg =
            relCount > 0
                ? `¿Deseas eliminar la tabla '${tableName}' del esquema? También se eliminarán ${relCount} relación(es) vinculadas a ella. (Si la base de datos ya está desplegada, pulsa 'Aprobar y Desplegar' después para aplicarlo en SQLite).`
                : `¿Deseas eliminar la tabla '${tableName}' del esquema actual?`;

        openConfirmDeleteModal(`Eliminar Tabla '${tableName}'`, msg, () => {
            state.contract.tables = state.contract.tables.filter((t) => t.name !== tableName);
            state.contract.relations = state.contract.relations.filter(
                (r) => r.source_table !== tableName && r.target_table !== tableName
            );
            (state.contract.tables || []).forEach((t) => {
                (t.columns || []).forEach((c) => {
                    if (c.fk_target_table === tableName) {
                        c.is_fk = false;
                        c.fk_target_table = null;
                        c.fk_target_column = null;
                    }
                });
            });
            if (state.selectedElement && state.selectedElement.table === tableName) {
                state.selectedElement = null;
            }
            if (state.explorer.activeTable === tableName) {
                state.explorer.activeTable = state.contract.tables[0] ? state.contract.tables[0].name : "";
            }
            handleLocalSchemaMutation(state.contract, true);
            showToast(`Tabla '${tableName}' eliminada del boceto. Pulsa 'Aprobar y Desplegar' para aplicarlo en disco.`);
        });
    }

    function requestDeleteProject(dbName) {
        openConfirmDeleteModal(
            `Eliminar Proyecto '${dbName}.db'`,
            `Se eliminará permanentemente el archivo '${dbName}.db', su esquema JSON y todo su historial de migraciones de la carpeta workspaces/. Esta acción no se puede deshacer.`,
            async () => {
                try {
                    const res = await apiFetch(`/api/databases/${encodeURIComponent(dbName)}`, {
                        method: "DELETE",
                    });
                    state.databases = res.databases || [];
                    showToast(`Proyecto '${dbName}.db' eliminado correctamente.`);
                    if (state.contract && state.contract.db_name === dbName) {
                        if (state.databases.length > 0) {
                            await loadDatabaseProject(state.databases[0].db_name);
                        } else {
                            createBlankProjectContract("mi_proyecto", "Mi Proyecto Relacional");
                        }
                    } else {
                        renderDatabasesSidebar();
                        syncAllViews();
                    }
                } catch (err) {
                    showToast(err.message);
                }
            }
        );
    }

    function createBlankProjectContract(rawName, rawTitle, silent = false, emptyTables = false) {
        const cleanName = (rawName || "nuevo_proyecto").trim().toLowerCase().replace(/[^a-z0-9_]+/g, "_") || "nuevo_proyecto";
        const title = (rawTitle || cleanName.replace(/_/g, " ")).trim();
        state.activeDbName = cleanName;
        state.history = [];
        const initialTables = emptyTables
            ? []
            : [
                  {
                      name: "entidad_principal",
                      description: "Primera tabla del nuevo proyecto (renómbrala o añade más tablas)",
                      is_associative: false,
                      is_historical: false,
                      position_x: 40,
                      position_y: 40,
                      columns: [
                          {
                              name: "id",
                              data_type: "INTEGER",
                              nullable: false,
                              is_pk: true,
                              is_fk: false,
                              is_unique: false,
                              auto_increment: true,
                              description: "Identificador único subrogado",
                              tutor_explanation: "Clave primaria autoincremental.",
                          },
                          {
                              name: "nombre",
                              data_type: "VARCHAR",
                              length: 150,
                              nullable: false,
                              is_pk: false,
                              is_fk: false,
                              is_unique: false,
                              auto_increment: false,
                              description: "Nombre principal del registro",
                              tutor_explanation: "Atributo descriptivo principal.",
                          },
                      ],
                      indexes: [],
                      tutor_explanation: "Entidad inicial de tu nuevo proyecto.",
                  },
              ];
        state.contract = {
            db_name: cleanName,
            title: title,
            description: "Nuevo proyecto creado en blanco listo para modelar.",
            source_prompt: "",
            dialect: state.activeDialect,
            is_deployed: false,
            version: 1,
            updated_at: new Date().toISOString().slice(0, 19),
            tables: initialTables,
            relations: [],
            audit_alerts: [],
            tutor_metadata: {
                nlp_summary: "Espacio de trabajo en blanco. Añade una tabla, usa Texto a Esquema o abre una base de datos .db.",
            },
        };
        state.selectedElement =
            initialTables.length > 0
                ? { type: "table", table: initialTables[0].name, data: initialTables[0] }
                : null;
        const dbInput = document.getElementById("nlp-db-name-input");
        const promptInput = document.getElementById("nlp-prompt-input");
        if (dbInput) dbInput.value = cleanName;
        if (promptInput) promptInput.value = "";
        state.explorer.activeTable = initialTables.length > 0 ? initialTables[0].name : "";
        state.explorer.rows = [];
        state.explorer.totalRows = 0;
        renderUndeployedExplorerNotice();
        state.activeSqlFile = { filename: `${cleanName}.sql`, path: null };
        updateActiveSQLFilenameUI();
        setSQLCodeValue(`-- Proyecto: ${title} (${cleanName}.db)\n-- Escribe tus sentencias SQL o diseña el esquema en el Lienzo ER\n\n`);
        activateCenterView("canvas");
        undoManager.reset(state.contract);
        handleLocalSchemaMutation(state.contract, true, false);
        if (!silent) {
            showToast(`Nuevo proyecto '${title}' creado en borrador.`);
        }
    }

    function bindProjectAndDeleteModals() {
        const newModal = document.getElementById("new-project-modal");
        const delModal = document.getElementById("confirm-delete-modal");

        const openNewProj = () => {
            const idx = state.databases.length + 1;
            document.getElementById("new-proj-name").value = `proyecto_${idx}`;
            document.getElementById("new-proj-title").value = `Proyecto Relacional ${idx}`;
            document.getElementById("new-proj-prompt").value = "";
            newModal.classList.remove("hidden");
        };

        const btnHeaderNew = document.getElementById("btn-new-project");
        const btnSidebarNew = document.getElementById("btn-sidebar-new-project");
        if (btnHeaderNew) btnHeaderNew.addEventListener("click", openNewProj);
        if (btnSidebarNew) btnSidebarNew.addEventListener("click", openNewProj);

        const closeNew = () => newModal.classList.add("hidden");
        document.getElementById("btn-close-new-proj-modal").addEventListener("click", closeNew);
        document.getElementById("btn-cancel-new-proj-modal").addEventListener("click", closeNew);

        document.getElementById("btn-confirm-new-proj-modal").addEventListener("click", async () => {
            const nameVal = document.getElementById("new-proj-name").value.trim();
            const titleVal = document.getElementById("new-proj-title").value.trim();
            const promptVal = document.getElementById("new-proj-prompt").value.trim();
            closeNew();

            if (promptVal) {
                document.getElementById("nlp-db-name-input").value = nameVal || "nuevo_proyecto";
                document.getElementById("nlp-prompt-input").value = promptVal;
                await runNLPInference();
            } else {
                createBlankProjectContract(nameVal, titleVal);
            }
        });

        const closeDel = () => {
            delModal.classList.add("hidden");
            pendingDeleteCallback = null;
        };
        document.getElementById("btn-cancel-del-modal").addEventListener("click", closeDel);
        document.getElementById("btn-confirm-del-modal").addEventListener("click", async () => {
            const cb = pendingDeleteCallback;
            closeDel();
            if (cb) await cb();
        });

        // Controles de Carpeta de Proyectos Conectada
        const btnChangeWs = document.getElementById("btn-change-workspace");
        const btnOpenWs = document.getElementById("btn-open-workspace-explorer");
        const btnImportDb = document.getElementById("btn-import-db");

        if (btnChangeWs) {
            btnChangeWs.addEventListener("click", async () => {
                try {
                    const res = await apiFetch("/api/workspace/select", {
                        method: "POST",
                        body: JSON.stringify({}),
                    });
                    if (res.changed) {
                        updateWorkspacePathDisplay(res.workspaces_dir);
                        state.databases = res.databases || [];
                        renderDatabasesSidebar();
                        if (state.databases.length > 0) {
                            await loadDatabaseProject(state.databases[0].db_name);
                        } else {
                            createBlankProjectContract("nuevo_proyecto", "Nuevo Proyecto en Carpeta");
                        }
                        showToast(`Carpeta conectada: ${res.workspaces_dir}`);
                    }
                } catch (err) {
                    showToast(err.message);
                }
            });
        }

        if (btnOpenWs) {
            btnOpenWs.addEventListener("click", async () => {
                try {
                    await apiFetch("/api/workspace/open-folder", { method: "POST" });
                } catch (err) {
                    showToast(err.message);
                }
            });
        }

        if (btnImportDb) {
            btnImportDb.addEventListener("click", async () => {
                try {
                    const res = await apiFetch("/api/workspace/import-db", { method: "POST" });
                    if (res.imported && res.db_name) {
                        state.databases = res.databases || state.databases;
                        await loadDatabaseProject(res.db_name);
                        showToast(`Base de datos '${res.db_name}.db' abierta e introspeccionada en el Lienzo ER.`);
                    }
                } catch (err) {
                    showToast(err.message);
                }
            });
        }

        const btnSaveDbAs = document.getElementById("btn-save-db-as");
        if (btnSaveDbAs) {
            btnSaveDbAs.addEventListener("click", async () => {
                if (!state.contract) return;
                try {
                    const res = await apiFetch("/api/files/save-db-as", {
                        method: "POST",
                        body: JSON.stringify({ db_name: state.contract.db_name }),
                    });
                    if (res.saved) {
                        showToast(`Copia de base de datos guardada en: ${res.path}`);
                    }
                } catch (err) {
                    showToast(err.message);
                }
            });
        }
    }

    function bindResizablePanels() {
        const leftResizer = document.getElementById("resizer-left");
        const rightResizer = document.getElementById("resizer-right");
        const sqlResultsResizer = document.getElementById("resizer-sql-results");
        const sqlResultsSection = document.getElementById("sql-results-section");
        const sqlSubpaneDml = document.getElementById("sql-subpane-dml");
        let activeResizer = null;

        leftResizer.addEventListener("mousedown", () => {
            activeResizer = "left";
            leftResizer.classList.add("resizing");
        });

        rightResizer.addEventListener("mousedown", () => {
            activeResizer = "right";
            rightResizer.classList.add("resizing");
        });

        if (sqlResultsResizer && sqlResultsSection && sqlSubpaneDml) {
            sqlResultsResizer.addEventListener("mousedown", (e) => {
                e.preventDefault();
                activeResizer = "sql-results";
                sqlResultsResizer.classList.add("resizing");
            });
        }

        window.addEventListener("mousemove", (e) => {
            if (!activeResizer) return;
            if (activeResizer === "left") {
                const w = Math.max(210, Math.min(440, e.clientX));
                document.documentElement.style.setProperty("--sidebar-left-width", `${w}px`);
                writeStorage(STORAGE_KEYS.leftWidth, w);
            } else if (activeResizer === "right") {
                const w = Math.max(290, Math.min(560, window.innerWidth - e.clientX));
                document.documentElement.style.setProperty("--sidebar-right-width", `${w}px`);
                writeStorage(STORAGE_KEYS.rightWidth, w);
            } else if (activeResizer === "sql-results" && sqlResultsSection && sqlSubpaneDml) {
                const rect = sqlSubpaneDml.getBoundingClientRect();
                const maxH = Math.max(180, Math.round(rect.height * 0.65));
                const nextH = Math.max(100, Math.min(maxH, Math.round(rect.bottom - e.clientY)));
                sqlResultsSection.style.height = `${nextH}px`;
            }
        });

        window.addEventListener("mouseup", () => {
            if (!activeResizer) return;
            leftResizer.classList.remove("resizing");
            rightResizer.classList.remove("resizing");
            if (sqlResultsResizer) sqlResultsResizer.classList.remove("resizing");
            activeResizer = null;
        });
    }

    document.addEventListener("DOMContentLoaded", initApp);
