/**
 * Sistema de Internacionalización (i18n) ES / EN para ChemySQL.
 * Permite arrancar con el idioma elegido en el instalador de Windows (language.txt)
 * y alternar en vivo entre Español e Inglés desde la barra de estado.
 */

export const LANG_STORAGE_KEY = "chemysql_lang";

export const TRANSLATIONS = {
    es: {
        // Cabecera
        btnNewProject: "Nuevo Proyecto",
        btnToggleNlp: "Texto a Esquema",
        btnMockData: "Mock Data",
        btnApproveDeploy: "Aprobar y Desplegar",
        btnModeStandard: "Modo Estándar",
        btnModeTutor: "Modo Tutor",
        // Barra NLP
        nlpTitle: "Motor de Inferencia Sintáctica y Heurística (Español / English → JSON Maestro)",
        nlpPresetsLabel: "Plantillas rápidas:",
        nlpClose: "Plegar",
        nlpRunBtn: "Generar Boceto Estructural",
        nlpPlaceholder: "Describe tu proyecto en español o inglés (texto libre o especificación estructurada Tabla/Table)...",
        // Panel Izquierdo
        tabProjects: "Proyectos",
        tabChallenges: "Retos",
        tabVersions: "Versiones",
        connectedFolder: "Carpeta Conectada",
        openInPc: "Ver en PC",
        openProject: "Abrir .chemysql",
        saveProject: "Guardar .chemysql",
        changeFolder: "Cambiar Carpeta",
        openDb: "Importar .db",
        saveDbAs: "Exportar .db",
        projectsInFolder: "Proyectos en Carpeta",
        btnNewShort: "+ Nuevo",
        // Pestañas Centrales
        viewCanvas: "Lienzo ER",
        viewRelational: "Diagrama Relacional",
        viewExplorer: "Explorador de Datos",
        viewSql: "Editor SQL Dual",
        // Lienzo ER
        btnAddTable: "Nueva Tabla",
        btnAddView: "Nueva Vista",
        btnAddRelation: "Vincular Tablas (FK)",
        btnAutoLayout: "Reorganizar Plano",
        btnCenter: "Centrar",
        // Diagrama Relacional
        relChen: "Conceptual (Chen)",
        relTables: "Paso a Tablas (Claves)",
        relHideAttrs: "Ocultar Atributos",
        relShowAttrs: "Mostrar Atributos",
        relShowWeakFk: "Mostrar FK Débil",
        relHideWeakFk: "Ocultar FK Débil",
        relShowPhysical: "Mostrar Tipos / FK",
        relHidePhysical: "Ocultar Tipos / FK",
        relReset: "Reorganizar",
        relExportSvg: "Exportar SVG",
        relExportPng: "Exportar PNG",
        // Explorador
        expAddRow: "+ Nuevo Registro",
        expSearchPh: "Filtrar registros...",
        expPrev: "← Anterior",
        expNext: "Siguiente →",
        // Editor SQL Dual
        sqlSubDdl: "Estructura (DDL Completo)",
        sqlSubDml: "Consultas (DML / SELECT)",
        btnCopyDdl: "Copiar Script",
        btnDownloadDdl: "Guardar DDL .sql",
        btnExportFullSql: "Exportar BD + Datos (.sql)",
        btnApplyDdl: "Aplicar Cambios al Esquema",
        btnNewSql: "Nuevo .sql",
        btnOpenSql: "Abrir .sql",
        btnSaveSql: "Guardar .sql",
        btnSaveSqlAs: "Guardar como...",
        btnExecSql: "Ejecutar SQL",
        resultsHeading: "Resultados de la Consulta",
        readyToRun: "Listo para ejecutar",
        // Panel Derecho
        tabAuditor: "Auditor",
        tabInspector: "Inspector",
        tabTutor: "Tutor",
        auditorHeading: "Diagnóstico de Normalización, Claves y Rendimiento",
        // Diagnóstico Error SQL en Inspector
        errTitle: "Diagnóstico de Error SQL",
        errLinePrefix: "Línea",
        errRollbackBadge: "ROLLBACK atómico aplicado · Sin tablas a medias",
        errHintLabel: "Causa probable y solución:",
        errStmtLabel: "Sentencia con error:",
        errJumpBtn: "Ir a la línea en el editor",
        errSelectionNotice: "Ejecutando únicamente la selección sombreada...",
        // Barra de Estado
        statusModeStd: "Modo Estándar",
        statusModeTut: "Modo Tutor",
        statusThemeDark: "Tema Oscuro",
        statusThemeLight: "Tema Claro",
    },
    en: {
        // Header
        btnNewProject: "New Project",
        btnToggleNlp: "Text to Schema",
        btnMockData: "Mock Data",
        btnApproveDeploy: "Approve & Deploy",
        btnModeStandard: "Standard Mode",
        btnModeTutor: "Tutor Mode",
        // NLP Bar
        nlpTitle: "Syntactic & Heuristic Inference Engine (English / Español → Master JSON)",
        nlpPresetsLabel: "Quick templates:",
        nlpClose: "Collapse",
        nlpRunBtn: "Generate Schema Draft",
        nlpPlaceholder: "Describe your database in English or Spanish (free text or structured Table specification)...",
        // Left Sidebar
        tabProjects: "Projects",
        tabChallenges: "Challenges",
        tabVersions: "Versions",
        connectedFolder: "Connected Folder",
        openInPc: "Open Folder",
        openProject: "Open .chemysql",
        saveProject: "Save .chemysql",
        changeFolder: "Change Folder",
        openDb: "Import .db",
        saveDbAs: "Export .db",
        projectsInFolder: "Projects in Folder",
        btnNewShort: "+ New",
        // Center Views
        viewCanvas: "ER Canvas",
        viewRelational: "Relational Diagram",
        viewExplorer: "Data Explorer",
        viewSql: "Dual SQL Editor",
        // ER Canvas
        btnAddTable: "New Table",
        btnAddView: "New View",
        btnAddRelation: "Link Tables (FK)",
        btnAutoLayout: "Auto Layout",
        btnCenter: "Center",
        // Relational Diagram
        relChen: "Conceptual (Chen)",
        relTables: "Table Mapping (Keys)",
        relHideAttrs: "Hide Attributes",
        relShowAttrs: "Show Attributes",
        relShowWeakFk: "Show Weak FK",
        relHideWeakFk: "Hide Weak FK",
        relShowPhysical: "Show Types / FK",
        relHidePhysical: "Hide Types / FK",
        relReset: "Reorganize",
        relExportSvg: "Export SVG",
        relExportPng: "Export PNG",
        // Data Explorer
        expAddRow: "+ New Row",
        expSearchPh: "Filter records...",
        expPrev: "← Previous",
        expNext: "Next →",
        // Dual SQL Editor
        sqlSubDdl: "Structure (Full DDL)",
        sqlSubDml: "Queries (DML / SELECT)",
        btnCopyDdl: "Copy Script",
        btnDownloadDdl: "Save DDL .sql",
        btnExportFullSql: "Export DB + Data (.sql)",
        btnApplyDdl: "Apply Changes to Schema",
        btnNewSql: "New .sql",
        btnOpenSql: "Open .sql",
        btnSaveSql: "Save .sql",
        btnSaveSqlAs: "Save as...",
        btnExecSql: "Run SQL",
        resultsHeading: "Query Results",
        readyToRun: "Ready to run",
        // Right Sidebar
        tabAuditor: "Auditor",
        tabInspector: "Inspector",
        tabTutor: "Tutor",
        auditorHeading: "Normalization, Keys & Performance Diagnostics",
        // Inspector SQL Error Diagnostic
        errTitle: "SQL Error Diagnostic",
        errLinePrefix: "Line",
        errRollbackBadge: "Atomic ROLLBACK applied · No partial tables left",
        errHintLabel: "Likely cause & fix:",
        errStmtLabel: "Failing statement:",
        errJumpBtn: "Jump to error line in editor",
        errSelectionNotice: "Running highlighted SQL selection...",
        // Statusbar
        statusModeStd: "Standard Mode",
        statusModeTut: "Tutor Mode",
        statusThemeDark: "Dark Theme",
        statusThemeLight: "Light Theme",
    },
};

export function t(key, lang = "es") {
    const dict = TRANSLATIONS[lang] || TRANSLATIONS.es;
    return dict[key] || TRANSLATIONS.es[key] || key;
}

function setSpanText(selector, text) {
    const el = document.querySelector(selector);
    if (!el) return;
    const span = el.querySelector("span:not(.tab-counter):not(.tab-badge-amber)");
    if (span) {
        span.textContent = text;
    } else {
        el.textContent = text;
    }
}

export function applyLanguageToDOM(lang = "es") {
    const l = lang === "en" ? "en" : "es";
    document.documentElement.lang = l;

    setSpanText("#btn-new-project", t("btnNewProject", l));
    setSpanText("#btn-toggle-nlp-bar", t("btnToggleNlp", l));
    setSpanText("#btn-generate-mock", t("btnMockData", l));
    setSpanText("#btn-approve-deploy", t("btnApproveDeploy", l));
    setSpanText("#btn-mode-standard", t("btnModeStandard", l));
    setSpanText("#btn-mode-tutor", t("btnModeTutor", l));

    const nlpTitle = document.querySelector(".nlp-section-title");
    if (nlpTitle) nlpTitle.textContent = t("nlpTitle", l);
    const presetLbl = document.querySelector(".preset-label");
    if (presetLbl) presetLbl.textContent = t("nlpPresetsLabel", l);
    setSpanText("#btn-close-nlp-bar", t("nlpClose", l));
    setSpanText("#btn-run-nlp-inference", t("nlpRunBtn", l));
    const nlpInput = document.getElementById("nlp-prompt-input");
    if (nlpInput) nlpInput.placeholder = t("nlpPlaceholder", l);

    setSpanText('[data-left-tab="explorer-tree"]', t("tabProjects", l));
    setSpanText('[data-left-tab="tutor-challenges"]', t("tabChallenges", l));
    setSpanText('[data-left-tab="version-history"]', t("tabVersions", l));

    const folderLbl = document.querySelector(".workspace-folder-label");
    if (folderLbl) folderLbl.textContent = t("connectedFolder", l);
    setSpanText("#btn-open-workspace-explorer", t("openInPc", l));
    setSpanText("#btn-open-project", t("openProject", l));
    setSpanText("#btn-save-project", t("saveProject", l));
    setSpanText("#btn-change-workspace", t("changeFolder", l));
    setSpanText("#btn-import-db", t("openDb", l));
    setSpanText("#btn-save-db-as", t("saveDbAs", l));
    const projHead = document.querySelector("#left-tab-explorer-tree .sidebar-heading");
    if (projHead) projHead.textContent = t("projectsInFolder", l);
    setSpanText("#btn-sidebar-new-project", t("btnNewShort", l));

    setSpanText('[data-center-view="canvas"]', t("viewCanvas", l));
    setSpanText('[data-center-view="relational"]', t("viewRelational", l));
    setSpanText('[data-center-view="explorer"]', t("viewExplorer", l));
    setSpanText('[data-center-view="sql"]', t("viewSql", l));

    setSpanText("#btn-canvas-add-table", t("btnAddTable", l));
    setSpanText("#btn-canvas-add-view", t("btnAddView", l));
    setSpanText("#btn-canvas-add-relation", t("btnAddRelation", l));
    setSpanText("#btn-canvas-autolayout", t("btnAutoLayout", l));
    setSpanText("#btn-zoom-reset", t("btnCenter", l));

    setSpanText('[data-reldiag-mode="chen"]', t("relChen", l));
    setSpanText('[data-reldiag-mode="tables"]', t("relTables", l));
    setSpanText("#btn-reldiag-reset", t("relReset", l));
    setSpanText("#btn-reldiag-export-svg", t("relExportSvg", l));
    setSpanText("#btn-reldiag-export-png", t("relExportPng", l));
    setSpanText("#btn-reldiag-fit", t("btnCenter", l));

    setSpanText("#btn-explorer-add-row", t("expAddRow", l));
    const expSearch = document.getElementById("explorer-search-input");
    if (expSearch) expSearch.placeholder = t("expSearchPh", l);
    setSpanText("#btn-page-prev", t("expPrev", l));
    setSpanText("#btn-page-next", t("expNext", l));

    setSpanText('[data-sql-subtab="ddl"]', t("sqlSubDdl", l));
    setSpanText('[data-sql-subtab="dml"]', t("sqlSubDml", l));
    setSpanText("#btn-copy-ddl", t("btnCopyDdl", l));
    setSpanText("#btn-download-ddl", t("btnDownloadDdl", l));
    setSpanText("#btn-export-full-sql", t("btnExportFullSql", l));
    setSpanText("#btn-apply-ddl-edits", t("btnApplyDdl", l));
    setSpanText("#btn-new-sql-file", t("btnNewSql", l));
    setSpanText("#btn-open-sql-file", t("btnOpenSql", l));
    setSpanText("#btn-save-sql-file", t("btnSaveSql", l));
    setSpanText("#btn-save-sql-as", t("btnSaveSqlAs", l));
    setSpanText("#btn-execute-sql", t("btnExecSql", l));
    const resHead = document.getElementById("sql-results-title");
    if (resHead) resHead.textContent = t("resultsHeading", l);

    setSpanText('[data-right-tab="auditor"]', t("tabAuditor", l));
    setSpanText('[data-right-tab="inspector"]', t("tabInspector", l));
    setSpanText('[data-right-tab="tutor"]', t("tabTutor", l));
    const audHead = document.querySelector("#right-tab-auditor .sidebar-heading");
    if (audHead) audHead.textContent = t("auditorHeading", l);

    const langBtn = document.getElementById("btn-lang-toggle");
    if (langBtn) {
        langBtn.textContent = l === "en" ? "EN · ES" : "ES · EN";
    }
}
