/**
 * Utilidades base, estado inicial, persistencia localStorage y cliente HTTP de ChemySQL.
 */

export const STORAGE_KEYS = {
    theme: "chemysql_theme",
    mode: "chemysql_mode",
    leftWidth: "chemysql_left_width",
    rightWidth: "chemysql_right_width",
};

export const NLP_PRESETS = {
    taller: {
        db_name: "taller_mecanico",
        text: "Necesito gestionar un taller mecánico donde los clientes traen varios vehículos, cada vehículo tiene reparaciones y en cada reparación se utilizan distintas piezas con un precio y stock.",
    },
    clinica_1fn: {
        db_name: "clinica_medica",
        text: "Necesito una clinica donde los pacientes con dni, nombre, telefono_1 y telefono_2 agendan citas con fecha_hora, diagnostico y coste en float atendidas por medicos con codigo, nombre y especialidad.",
    },
    biblioteca: {
        db_name: "biblioteca_municipal",
        text: "Necesito gestionar una biblioteca donde los autores escriben varios libros con isbn, titulo y stock, y los socios con dni, nombre y email realizan prestamos con fecha_prestamo, fecha_vencimiento y devuelto.",
    },
    comercio: {
        db_name: "comercio_facturacion",
        text: "Necesito una tienda donde los clientes realizan pedidos que incluyen distintos productos con precio y stock, y cada cliente recibe facturas con fecha_emision, subtotal, total y pagado.",
    },
};

export function createInitialState() {
    return {
        mode: "standard", // 'standard' | 'tutor'
        theme: "dark",
        activeDbName: "",
        contract: null,
        ddlPreviews: { sqlite: "", postgresql: "", mysql: "", sqlserver: "" },
        activeDialect: "sqlite",
        activeSqlSubtab: "ddl",
        databases: [],
        challenges: [],
        history: [],
        selectedElement: null,
        explorer: {
            activeTable: "",
            page: 1,
            pageSize: 25,
            search: "",
            columns: [],
            rows: [],
            totalPages: 1,
            totalRows: 0,
        },
        pendingDangerousSql: "",
        activeSqlFile: {
            filename: "consulta_actual.sql",
            path: null,
        },
        sqlResults: {
            lastSql: "",
            page: 1,
            pageSize: 100,
            totalPages: 1,
            columns: [],
            rows: [],
        },
    };
}

export function escapeHtml(str) {
    return String(str === null || str === undefined ? "" : str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

export function showToast(message) {
    const container = document.getElementById("toast-container");
    if (!container) return;
    const item = document.createElement("div");
    item.className = "toast-item";
    item.textContent = message;
    container.appendChild(item);
    setTimeout(() => {
        item.remove();
    }, 4200);
}

export async function apiFetch(url, options = {}) {
    const headers = Object.assign({ "Content-Type": "application/json" }, options.headers || {});
    const response = await fetch(url, Object.assign({}, options, { headers }));
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        const err = new Error(data.detail || `Error HTTP ${response.status}`);
        if (data.sql_error) {
            err.sqlError = data.sql_error;
        }
        throw err;
    }
    return data;
}

export function readStorage(key, fallback = null) {
    try {
        const v = window.localStorage.getItem(key);
        return v !== null ? v : fallback;
    } catch (_err) {
        return fallback;
    }
}

export function writeStorage(key, value) {
    try {
        window.localStorage.setItem(key, String(value));
    } catch (_err) {
        // Ignorar si localStorage no está disponible
    }
}

export function triggerFileDownload(filename, content, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}
