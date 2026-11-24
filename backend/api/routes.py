"""
Endpoints REST de SGBD-Smart (FastAPI).
Conecta el Frontend Web con el Motor NLP en español, el Contrato Maestro JSON,
el Auditor Proactivo, el Transpilador Multi-Dialecto, el Motor SQLite y el Modo Tutor.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Dict, Literal, Optional, Set
from fastapi import APIRouter, HTTPException, Query

from backend import APP_VERSION
from backend.core.db_engine import DatabaseEngine
from backend.core.nlp_parser import to_snake_case
from backend.core.schema_model import (
    AutoFixRequest,
    CellUpdateRequest,
    CreateIndexRequest,
    DeploySchemaRequest,
    MasterSchemaContract,
    MockDataRequest,
    NLPInferenceRequest,
    ParseDDLRequest,
    QueryDecomposeRequest,
    QueryExecutionRequest,
    RowInsertRequest,
    SaveDBAsRequest,
    SaveSQLRequest,
    WorkspaceSelectRequest,
)


if getattr(sys, "frozen", False):
    APP_USER_ROOT = Path.home() / "Documents" / "VarSQL"
    WORKSPACES_DIR = APP_USER_ROOT / "workspaces"
    CONFIG_PATH = APP_USER_ROOT / "varsql_config.json"
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    WORKSPACES_DIR = PROJECT_ROOT / "workspaces"
    CONFIG_PATH = PROJECT_ROOT / "varsql_config.json"

engine = DatabaseEngine(WORKSPACES_DIR, config_path=CONFIG_PATH)
NATIVE_WINDOW: Any = None
ALLOWED_SQL_PATHS: Set[Path] = set()
router = APIRouter(prefix="/api")


def _is_path_inside_dir(target: Path, base_dir: Path) -> bool:
    try:
        target.resolve().relative_to(base_dir.resolve())
        return True
    except ValueError:
        return False


def _is_allowed_sql_path(target: Path) -> bool:
    resolved = target.resolve()
    if resolved.suffix.lower() != ".sql":
        return False
    return resolved in ALLOWED_SQL_PATHS or _is_path_inside_dir(resolved, engine.workspaces_dir)


def _build_ddl_previews(contract: MasterSchemaContract) -> Dict[str, str]:
    return engine.transpiler.build_all_ddl_previews(contract)


@router.get("/health")
def health_check() -> Dict[str, Any]:
    return {
        "status": "ok",
        "version": APP_VERSION,
        "service": "VarSQL Deterministic Engine",
        "workspaces_dir": str(engine.workspaces_dir),
    }


@router.get("/databases")
def list_databases() -> Dict[str, Any]:
    return {
        "workspaces_dir": str(engine.workspaces_dir),
        "databases": engine.list_databases(),
        "challenges": engine.tutor.get_guided_challenges(),
    }


@router.post("/workspace/select")
def select_workspace_folder(payload: Optional[WorkspaceSelectRequest] = None) -> Dict[str, Any]:
    """Permite conectar SGBD-Smart a cualquier carpeta del PC mediante selector nativo o ruta explícita."""
    explicit_path = payload.path if payload else None
    chosen_path: Optional[str] = explicit_path.strip() if explicit_path else None

    if not chosen_path:
        if NATIVE_WINDOW is not None:
            try:
                import webview
                dialog_type = getattr(webview, "FileDialog", None)
                folder_mode = dialog_type.FOLDER if dialog_type else webview.FOLDER_DIALOG
                result = NATIVE_WINDOW.create_file_dialog(
                    folder_mode,
                    directory=str(engine.workspaces_dir),
                )
                if result and len(result) > 0:
                    chosen_path = str(result[0])
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"No se pudo abrir el selector de carpetas: {exc}") from exc
        else:
            raise HTTPException(
                status_code=400,
                detail="Proporciona una ruta de carpeta válida o ejecuta la aplicación en modo nativo de escritorio.",
            )

    if not chosen_path:
        return {
            "changed": False,
            "workspaces_dir": str(engine.workspaces_dir),
            "databases": engine.list_databases(),
        }

    try:
        new_dir = engine.set_workspaces_dir(Path(chosen_path))
        return {
            "changed": True,
            "workspaces_dir": str(new_dir),
            "databases": engine.list_databases(),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo conectar la carpeta '{chosen_path}': {exc}") from exc


@router.post("/workspace/open-folder")
def open_workspace_in_explorer() -> Dict[str, Any]:
    """Abre la carpeta de proyectos conectada directamente en el Explorador de Archivos de Windows."""
    try:
        folder = engine.workspaces_dir
        folder.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(str(folder))  # type: ignore[attr-defined]
        return {"opened": True, "workspaces_dir": str(folder)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo abrir la carpeta en el explorador: {exc}") from exc


@router.post("/workspace/import-db")
def import_existing_sqlite_db() -> Dict[str, Any]:
    """Abre un archivo .db / .sqlite existente desde el PC y lo carga e introspecciona en la carpeta activa."""
    if NATIVE_WINDOW is None:
        raise HTTPException(status_code=400, detail="Selector de archivos nativo disponible únicamente en la app de escritorio.")

    try:
        import webview
        dialog_type = getattr(webview, "FileDialog", None)
        open_mode = dialog_type.OPEN if dialog_type else webview.OPEN_DIALOG
        result = NATIVE_WINDOW.create_file_dialog(
            open_mode,
            directory=str(engine.workspaces_dir),
            allow_multiple=False,
            file_types=("Bases de datos SQLite (*.db;*.sqlite;*.sqlite3)", "Todos los archivos (*.*)"),
        )
        if not result or len(result) == 0:
            return {"imported": False, "databases": engine.list_databases()}

        src_file = Path(str(result[0]))
        if not src_file.exists():
            raise FileNotFoundError(f"El archivo '{src_file}' no existe.")

        clean_stem = to_snake_case(src_file.stem) or "base_importada"
        dest_file = engine.workspaces_dir / f"{clean_stem}.db"
        if src_file.resolve() != dest_file.resolve():
            shutil.copy2(src_file, dest_file)

        contract = engine.load_or_introspect_schema(clean_stem)
        return {
            "imported": True,
            "db_name": clean_stem,
            "workspaces_dir": str(engine.workspaces_dir),
            "databases": engine.list_databases(),
            "schema_contract": contract.model_dump(),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error al abrir archivo .db: {exc}") from exc


@router.post("/files/open-sql")
def open_sql_script_file() -> Dict[str, Any]:
    """Abre un archivo de script .sql desde cualquier carpeta del PC mediante el diálogo nativo."""
    if NATIVE_WINDOW is None:
        raise HTTPException(status_code=400, detail="Diálogo nativo disponible en la aplicación de escritorio.")
    try:
        import webview
        dialog_type = getattr(webview, "FileDialog", None)
        open_mode = dialog_type.OPEN if dialog_type else webview.OPEN_DIALOG
        result = NATIVE_WINDOW.create_file_dialog(
            open_mode,
            directory=str(engine.workspaces_dir),
            allow_multiple=False,
            file_types=("Scripts SQL (*.sql)", "Archivos de texto (*.txt)", "Todos los archivos (*.*)"),
        )
        if not result or len(result) == 0:
            return {"opened": False}
        file_path = Path(str(result[0])).resolve()
        if file_path.suffix.lower() == ".sql":
            ALLOWED_SQL_PATHS.add(file_path)
        content = file_path.read_text(encoding="utf-8", errors="replace")
        return {
            "opened": True,
            "filename": file_path.name,
            "path": str(file_path),
            "content": content,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error al abrir script SQL: {exc}") from exc


@router.post("/files/save-sql")
def save_sql_script_file(payload: SaveSQLRequest) -> Dict[str, Any]:
    """Crea o guarda un archivo .sql en la carpeta elegida por el usuario."""
    content = payload.content
    existing_path = payload.path
    save_as = payload.save_as
    raw_name = Path(payload.filename or "script_sql.sql").name
    suggested_name = raw_name if raw_name.lower().endswith(".sql") else f"{raw_name}.sql"

    target_path: Optional[Path] = None
    if existing_path and not save_as:
        candidate = Path(existing_path).resolve()
        if not _is_allowed_sql_path(candidate):
            raise HTTPException(
                status_code=403,
                detail="Ruta no autorizada para escritura directa. Usa 'Guardar como...' o guarda un archivo .sql dentro de la carpeta del proyecto.",
            )
        target_path = candidate
    else:
        if NATIVE_WINDOW is not None:
            try:
                import webview
                dialog_type = getattr(webview, "FileDialog", None)
                save_mode = dialog_type.SAVE if dialog_type else webview.SAVE_DIALOG
                result = NATIVE_WINDOW.create_file_dialog(
                    save_mode,
                    directory=str(engine.workspaces_dir),
                    save_filename=suggested_name,
                    file_types=("Scripts SQL (*.sql)", "Todos los archivos (*.*)"),
                )
                if not result:
                    return {"saved": False}
                chosen = result[0] if isinstance(result, (list, tuple)) else result
                if not chosen:
                    return {"saved": False}
                target_path = Path(str(chosen)).resolve()
                if target_path.suffix == "":
                    target_path = target_path.with_suffix(".sql")
                ALLOWED_SQL_PATHS.add(target_path)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"No se pudo abrir el diálogo Guardar Como: {exc}") from exc
        else:
            target_path = (engine.workspaces_dir / suggested_name).resolve()

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        return {
            "saved": True,
            "filename": target_path.name,
            "path": str(target_path),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo guardar el archivo SQL: {exc}") from exc


@router.post("/files/save-db-as")
def save_database_copy_as(payload: SaveDBAsRequest) -> Dict[str, Any]:
    """Exporta o guarda una copia del archivo .db activo en la carpeta que elija el usuario."""
    db_name = to_snake_case(payload.db_name)
    if not db_name:
        raise HTTPException(status_code=400, detail="Indica una base de datos válida.")
    src_db = engine._db_path(db_name)
    if not src_db.exists():
        raise HTTPException(status_code=400, detail=f"La base de datos '{db_name}.db' aún no ha sido desplegada.")
    if NATIVE_WINDOW is None:
        raise HTTPException(status_code=400, detail="Diálogo Guardar Como disponible en la aplicación de escritorio.")
    try:
        import webview
        dialog_type = getattr(webview, "FileDialog", None)
        save_mode = dialog_type.SAVE if dialog_type else webview.SAVE_DIALOG
        result = NATIVE_WINDOW.create_file_dialog(
            save_mode,
            directory=str(engine.workspaces_dir),
            save_filename=f"{db_name}.db",
            file_types=("Base de datos SQLite (*.db)", "Todos los archivos (*.*)"),
        )
        if not result:
            return {"saved": False}
        chosen = result[0] if isinstance(result, (list, tuple)) else result
        if not chosen:
            return {"saved": False}
        dest = Path(str(chosen))
        if dest.suffix == "":
            dest = dest.with_suffix(".db")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_db, dest)
        return {"saved": True, "filename": dest.name, "path": str(dest)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo guardar la copia .db: {exc}") from exc


@router.get("/databases/{db_name}")
def get_database_schema(db_name: str) -> Dict[str, Any]:
    try:
        contract = engine.load_or_introspect_schema(db_name)
        return {
            "schema_contract": contract.model_dump(),
            "ddl_previews": _build_ddl_previews(contract),
            "history": engine.get_version_history(db_name),
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/databases/{db_name}")
def delete_database_project(db_name: str) -> Dict[str, Any]:
    try:
        return engine.delete_database(db_name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo eliminar el proyecto '{db_name}': {exc}") from exc


@router.post("/nlp/infer")
def infer_schema_from_text(req: NLPInferenceRequest) -> Dict[str, Any]:
    try:
        contract = engine.nlp.parse_text_to_schema(
            text=req.text,
            db_name=req.db_name,
            dialect=req.dialect,
        )
        engine.auditor.audit_schema(contract)
        return {
            "schema_contract": contract.model_dump(),
            "ddl_previews": _build_ddl_previews(contract),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error al procesar la descripción: {exc}") from exc


@router.post("/schema/audit")
def audit_and_transpile_schema(contract: MasterSchemaContract) -> Dict[str, Any]:
    try:
        engine.auditor.audit_schema(contract)
        return {
            "schema_contract": contract.model_dump(),
            "ddl_previews": _build_ddl_previews(contract),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error en auditoría del esquema: {exc}") from exc


@router.post("/schema/parse-ddl")
def parse_edited_ddl_to_schema(payload: ParseDDLRequest) -> Dict[str, Any]:
    """Convierte código DDL editado manualmente por el usuario de vuelta al Contrato Maestro JSON y Lienzo ER."""
    sql_text = payload.sql.strip()
    if not sql_text:
        raise HTTPException(status_code=400, detail="El código DDL está vacío.")
    base_contract = payload.schema_contract
    try:
        updated_contract = engine.transpiler.parse_ddl_to_contract(sql_text, base_contract=base_contract)
        engine.auditor.audit_schema(updated_contract)
        return {
            "schema_contract": updated_contract.model_dump(),
            "ddl_previews": _build_ddl_previews(updated_contract),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error de sintaxis en el DDL editado: {exc}") from exc


@router.post("/schema/autofix")
def apply_auditor_autofix(req: AutoFixRequest) -> Dict[str, Any]:
    try:
        updated_contract, summary = engine.auditor.apply_auto_fix(req.schema_contract, req.alert_id)
        return {
            "summary": summary,
            "schema_contract": updated_contract.model_dump(),
            "ddl_previews": _build_ddl_previews(updated_contract),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/schema/deploy")
def approve_and_deploy_schema(req: DeploySchemaRequest) -> Dict[str, Any]:
    try:
        result = engine.deploy_schema(
            contract=req.schema_contract,
            populate_mock_data=req.populate_mock_data,
            mock_rows_per_table=req.mock_rows_per_table,
        )
        deployed_contract = MasterSchemaContract.model_validate(result["schema_contract"])
        result["ddl_previews"] = _build_ddl_previews(deployed_contract)
        result["history"] = engine.get_version_history(deployed_contract.db_name)
        result["databases"] = engine.list_databases()
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/databases/{db_name}/history")
def get_schema_version_history(db_name: str) -> Dict[str, Any]:
    return {
        "db_name": db_name,
        "history": engine.get_version_history(db_name),
    }


@router.post("/databases/{db_name}/mock")
def generate_database_mock_data(db_name: str, req: MockDataRequest) -> Dict[str, Any]:
    try:
        result = engine.generate_mock_data(db_name, rows_per_table=req.rows_per_table)
        result["databases"] = engine.list_databases()
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/databases/{db_name}/tables/{table_name}/rows")
def get_table_rows(
    db_name: str,
    table_name: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    search: str = Query(default=""),
) -> Dict[str, Any]:
    try:
        return engine.get_table_rows(db_name, table_name, page=page, page_size=page_size, search=search)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/databases/{db_name}/tables/{table_name}/export")
def export_table_rows(
    db_name: str,
    table_name: str,
    fmt: Literal["csv", "json", "sql"] = Query(default="csv"),
) -> Dict[str, Any]:
    try:
        return engine.export_table_data(db_name, table_name, fmt=fmt)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error al exportar tabla '{table_name}': {exc}") from exc


@router.get("/databases/{db_name}/fk-preview")
def get_foreign_key_preview(
    db_name: str,
    target_table: str = Query(...),
    target_column: str = Query(default="id"),
    value: str = Query(...),
) -> Dict[str, Any]:
    try:
        return engine.get_fk_parent_record(db_name, target_table, target_column, value)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/explorer/cell")
def update_explorer_cell(req: CellUpdateRequest) -> Dict[str, Any]:
    try:
        return engine.update_cell(
            db_name=req.db_name,
            table_name=req.table_name,
            pk_column=req.pk_column,
            pk_value=req.pk_value,
            pk_values=req.pk_values,
            target_column=req.target_column,
            new_value=req.new_value,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Violación de integridad o tipo al actualizar: {exc}") from exc


@router.post("/explorer/row")
def insert_explorer_row(req: RowInsertRequest) -> Dict[str, Any]:
    try:
        return engine.insert_row(req.db_name, req.table_name, req.values)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error al insertar registro: {exc}") from exc


@router.delete("/explorer/row")
def delete_explorer_row(
    db_name: str = Query(...),
    table_name: str = Query(...),
    pk_column: Optional[str] = Query(default="id"),
    pk_value: Optional[str] = Query(default=None),
    pk_values: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    try:
        parsed_pk_values: Optional[Dict[str, Any]] = None
        if pk_values:
            raw_parsed = json.loads(pk_values)
            if not isinstance(raw_parsed, dict) or not raw_parsed:
                raise ValueError("El parámetro pk_values debe ser un objeto JSON no vacío.")
            parsed_pk_values = raw_parsed
        return engine.delete_row(
            db_name=db_name,
            table_name=table_name,
            pk_column=pk_column,
            pk_value=pk_value,
            pk_values=parsed_pk_values,
        )
    except Exception as exc:
        raw_msg = str(exc)
        if "FOREIGN KEY constraint failed" in raw_msg:
            detail = (
                f"Restricción de integridad referencial al eliminar (existen registros hijos dependientes): {raw_msg}"
            )
        else:
            detail = f"Error al eliminar registro: {raw_msg}"
        raise HTTPException(status_code=400, detail=detail) from exc


@router.post("/query/execute")
def execute_sql_query(req: QueryExecutionRequest) -> Dict[str, Any]:
    try:
        return engine.execute_query(
            db_name=req.db_name,
            sql=req.sql,
            confirmed_dangerous=req.confirmed_dangerous,
            page=req.page,
            page_size=req.page_size,
        )
    except Exception as exc:
        raw_msg = str(exc)
        if "FOREIGN KEY constraint failed" in raw_msg:
            detail = (
                "Integridad Referencial Protegida (ON DELETE RESTRICT): SQLite bloqueó la operación porque existen "
                "registros dependientes en otras tablas que apuntan a estas filas. Elimina primero los registros hijos "
                "o utiliza borrado lógico (ej. UPDATE tabla SET activo = 0 WHERE id = 1)."
            )
        elif "UNIQUE constraint failed" in raw_msg:
            detail = f"Restricción UNIQUE violada: ya existe un registro con el mismo valor único ({raw_msg})."
        elif "NOT NULL constraint failed" in raw_msg:
            detail = f"Restricción NOT NULL violada: falta un valor obligatorio ({raw_msg})."
        elif "no such table" in raw_msg:
            detail = (
                f"La tabla indicada aún no existe en disco ({raw_msg}). "
                "Si estás trabajando sobre un boceto nuevo, pulsa 'Aprobar y Desplegar' primero."
            )
        else:
            detail = f"Error SQL: {raw_msg}"
        raise HTTPException(status_code=400, detail=detail) from exc


@router.post("/query/decompose")
def decompose_sql_for_tutor(payload: QueryDecomposeRequest) -> Dict[str, Any]:
    return engine.tutor.decompose_sql_query(payload.sql)


@router.post("/index/create")
def create_index_endpoint(req: CreateIndexRequest) -> Dict[str, Any]:
    try:
        res = engine.create_index_direct(
            db_name=req.db_name,
            table_name=req.table_name,
            column_name=req.column_name,
            schema_contract=req.schema_contract,
        )
        updated_contract = MasterSchemaContract.model_validate(res["schema_contract"])
        res["ddl_previews"] = _build_ddl_previews(updated_contract)
        return res
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tutor/challenges")
def get_tutor_challenges() -> Dict[str, Any]:
    return {"challenges": engine.tutor.get_guided_challenges()}
