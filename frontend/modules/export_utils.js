/**
 * Exportación de tablas del Explorador y resultados del Editor SQL a CSV, JSON y SQL.
 */

import { apiFetch, showToast, triggerFileDownload } from "./core.js";

export async function exportExplorerTable(state, fmt) {
    if (!state.contract || !state.explorer.activeTable || !state.contract.is_deployed) {
        showToast("Despliega la base de datos y selecciona una tabla para exportar.");
        return;
    }
    try {
        const url = `/api/databases/${encodeURIComponent(
            state.contract.db_name
        )}/tables/${encodeURIComponent(state.explorer.activeTable)}/export?fmt=${encodeURIComponent(fmt)}`;
        const res = await apiFetch(url);
        triggerFileDownload(res.filename, res.content, res.mime_type);
        showToast(`Exportados ${res.row_count} registros en ${res.filename}.`);
    } catch (err) {
        showToast(err.message);
    }
}

export function exportSQLResults(state, fmt) {
    const cols = state.sqlResults.columns || [];
    const rows = state.sqlResults.rows || [];
    if (!cols.length || !rows.length) {
        showToast("No hay resultados para exportar.");
        return;
    }
    const db = (state.contract && state.contract.db_name) || "consulta";
    if (fmt === "json") {
        triggerFileDownload(
            `${db}_resultados.json`,
            JSON.stringify(rows, null, 2),
            "application/json;charset=utf-8"
        );
        showToast(`Resultados exportados a ${db}_resultados.json.`);
        return;
    }
    const escCsv = (val) => {
        const s = val === null || val === undefined ? "" : String(val);
        return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const csvLines = [cols.map(escCsv).join(",")];
    rows.forEach((r) => {
        csvLines.push(cols.map((c) => escCsv(r[c])).join(","));
    });
    triggerFileDownload(`${db}_resultados.csv`, csvLines.join("\n") + "\n", "text/csv;charset=utf-8");
    showToast(`Resultados exportados a ${db}_resultados.csv.`);
}
