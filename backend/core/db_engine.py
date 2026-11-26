"""
Capa de Ejecución, Introspección, Despliegue Transaccional, Escudo Preventivo y Mock Data sobre SQLite.
Gestiona los archivos .db en el directorio local workspaces/, mantiene el historial de versiones
y migraciones (ALTER TABLE), genera datos sintéticos coherentes en español y ejecuta consultas con EXPLAIN QUERY PLAN.
"""

from __future__ import annotations
from contextlib import contextmanager
import base64
import csv
from datetime import date, datetime, timedelta
import io
import json
from pathlib import Path
import re
import shutil
import sqlite3
import time
from typing import Any, Dict, Iterator, List, Literal, Optional, Tuple

from backend.core.auditor import ProactiveAuditor
from backend.core.nlp_parser import SpanishNLPParser, infer_column_type, to_singular, to_snake_case
from backend.core.schema_model import (
    ColumnModel,
    MasterSchemaContract,
    RelationModel,
    TableModel,
    ViewModel,
)
from backend.core.sql_transpiler import (
    SQLTranspiler,
    extract_table_column_constraints,
    quote_identifier,
    split_sql_statements,
)
from backend.core.tutor_engine import TutorEngine


class SQLExecutionDetailError(Exception):
    """Error estructurado de ejecución SQL con número de línea exacto, sentencia fallida, causa y estado de rollback."""

    def __init__(
        self,
        message: str,
        *,
        line: int = 1,
        statement: str = "",
        raw_error: str = "",
        hint: str = "",
        rolled_back: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.line = line
        self.statement = statement
        self.raw_error = raw_error
        self.hint = hint
        self.rolled_back = rolled_back

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": self.message,
            "line": self.line,
            "statement": self.statement,
            "raw_error": self.raw_error,
            "hint": self.hint,
            "rolled_back": self.rolled_back,
        }


def _locate_statement_line(full_sql: str, stmt: str, search_from: int = 0) -> Tuple[int, int]:
    """Devuelve (linea_1_based, nueva_posicion_busqueda) de la sentencia dentro del script original."""
    needle = stmt.strip()
    if not needle:
        return 1, search_from
    first_line = needle.splitlines()[0].strip()
    idx = full_sql.find(needle, search_from)
    if idx < 0 and first_line:
        idx = full_sql.find(first_line, search_from)
    if idx < 0:
        idx = search_from
    line_num = full_sql[:idx].count("\n") + 1
    return line_num, idx + len(first_line)


def _build_sql_error_hint(raw_msg: str) -> str:
    low = raw_msg.lower()
    if "already exists" in low:
        return (
            "La tabla o índice ya existía previamente en el archivo .db. "
            "Usa 'CREATE TABLE IF NOT EXISTS ...' o selecciona con el ratón únicamente las sentencias nuevas antes de pulsar Ejecutar SQL."
        )
    if "syntax error" in low:
        return (
            "Revisa comas faltantes o sobrantes al final de la columna anterior, paréntesis sin cerrar o palabras clave mal escritas en esta línea."
        )
    if "foreign key constraint failed" in low:
        return (
            "Integridad referencial protegida: verifica que el registro padre exista antes de insertar o que no haya registros hijos dependientes al borrar."
        )
    if "unique constraint failed" in low:
        return "Se intentó insertar o actualizar un valor duplicado en una columna marcada como UNIQUE o PRIMARY KEY."
    if "not null constraint failed" in low:
        return "Falta asignar un valor a una columna obligatoria (NOT NULL)."
    if "check constraint failed" in low:
        return "Un valor incumple una regla de validación CHECK definida en la tabla."
    if "no such table" in low:
        return "La tabla referenciada no existe todavía en la base de datos activa. Asegúrate de crearla primero o pulsar 'Aprobar y Desplegar'."
    if "no such column" in low:
        return "El nombre de columna indicado no existe en esa tabla. Revisa mayúsculas/minúsculas o posibles erratas."
    return "Revisa la sentencia indicada en esta línea y vuelve a ejecutar."


class DatabaseEngine:
    """Motor de almacenamiento y orquestación SQLite local para SGBD-Smart."""

    def __init__(self, workspaces_dir: Path, config_path: Optional[Path] = None) -> None:
        self.config_path = config_path
        resolved_dir = workspaces_dir
        if config_path and config_path.exists():
            try:
                cfg = json.loads(config_path.read_text(encoding="utf-8"))
                saved_dir = cfg.get("workspaces_dir")
                if saved_dir:
                    candidate = Path(saved_dir)
                    candidate.mkdir(parents=True, exist_ok=True)
                    resolved_dir = candidate
            except Exception:
                pass
        self.workspaces_dir = resolved_dir
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)
        self.nlp = SpanishNLPParser()
        self.auditor = ProactiveAuditor()
        self.transpiler = SQLTranspiler()
        self.tutor = TutorEngine()

    def set_workspaces_dir(self, new_dir: Path) -> Path:
        """Conecta SGBD-Smart a una nueva carpeta local del PC y guarda la preferencia."""
        target = new_dir.expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        self.workspaces_dir = target
        if self.config_path:
            self.config_path.write_text(
                json.dumps({"workspaces_dir": str(target)}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return target

    def _db_path(self, db_name: str) -> Path:
        clean = to_snake_case(db_name) or "proyecto_chemysql"
        return self.workspaces_dir / f"{clean}.db"

    def _meta_path(self, db_name: str) -> Path:
        clean = to_snake_case(db_name) or "proyecto_chemysql"
        return self.workspaces_dir / f"{clean}.schema.json"

    def _history_path(self, db_name: str) -> Path:
        clean = to_snake_case(db_name) or "proyecto_chemysql"
        return self.workspaces_dir / f"{clean}.history.json"

    @contextmanager
    def _connect(self, db_file: Path) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(db_file)
        try:
            yield conn
        finally:
            conn.close()

    def ensure_demo_databases(self) -> None:
        """Crea proyectos de demostración pre-cargados si el directorio workspaces está vacío."""
        taller_db = self._db_path("taller_mecanico")
        if not taller_db.exists():
            prompt_taller = (
                "Necesito gestionar un taller mecánico donde los clientes traen varios vehículos, "
                "cada vehículo tiene reparaciones y en cada reparación se utilizan distintas piezas con un precio y stock."
            )
            contract = self.nlp.parse_text_to_schema(prompt_taller, db_name="taller_mecanico")
            # Añadir intencionalmente una columna telefono_2 en clientes o dejar índices listos para que el usuario
            # vea tanto tablas desplegadas con datos reales como sugerencias activas del auditor.
            self.auditor.audit_schema(contract)
            self.deploy_schema(contract, populate_mock_data=True, mock_rows_per_table=12)

        biblio_db = self._db_path("biblioteca_municipal")
        if not biblio_db.exists():
            prompt_biblio = (
                "Necesito gestionar una biblioteca donde los autores escriben varios libros con isbn, titulo y stock, "
                "y los socios con dni, nombre y email realizan prestamos con fecha_prestamo, fecha_vencimiento y devuelto."
            )
            contract_b = self.nlp.parse_text_to_schema(prompt_biblio, db_name="biblioteca_municipal")
            self.auditor.audit_schema(contract_b)
            self.deploy_schema(contract_b, populate_mock_data=True, mock_rows_per_table=10)

    def list_databases(self) -> List[Dict[str, Any]]:
        """Lista todas las bases de datos .db disponibles en workspaces/ con sus estadísticas."""
        items: List[Dict[str, Any]] = []
        for db_file in sorted(self.workspaces_dir.glob("*.db")):
            db_name = db_file.stem
            contract = self.load_or_introspect_schema(db_name)
            total_rows = 0
            try:
                with self._connect(db_file) as conn:
                    cur = conn.cursor()
                    for t in contract.tables:
                        try:
                            t_q = quote_identifier(t.name, "sqlite")
                            cur.execute(f"SELECT COUNT(*) FROM {t_q}")
                            total_rows += int(cur.fetchone()[0])
                        except sqlite3.Error:
                            pass
            except sqlite3.Error:
                pass

            items.append(
                {
                    "db_name": db_name,
                    "title": contract.title,
                    "description": contract.description,
                    "table_count": len(contract.tables),
                    "relation_count": len(contract.relations),
                    "alert_count": len(contract.audit_alerts),
                    "total_rows": total_rows,
                    "version": contract.version,
                    "updated_at": contract.updated_at,
                    "size_kb": round(db_file.stat().st_size / 1024, 1),
                }
            )
        return items

    def load_or_introspect_schema(self, db_name: str) -> MasterSchemaContract:
        """
        Carga el Contrato Maestro JSON de una base de datos existente o lo reconstruye
        mediante introspección directa del archivo SQLite .db.
        """
        meta_file = self._meta_path(db_name)
        db_file = self._db_path(db_name)

        if meta_file.exists():
            try:
                data = json.loads(meta_file.read_text(encoding="utf-8"))
                contract = MasterSchemaContract.model_validate(data)
                contract.is_deployed = db_file.exists()
                self.auditor.audit_schema(contract)
                return contract
            except Exception:
                pass

        if not db_file.exists():
            raise FileNotFoundError(f"La base de datos '{db_name}' no existe en workspaces/.")

        contract = self._introspect_sqlite_file(db_name, db_file)
        self.auditor.audit_schema(contract)
        meta_file.write_text(
            json.dumps(contract.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return contract

    def _introspect_sqlite_file(self, db_name: str, db_file: Path) -> MasterSchemaContract:
        """Reconstruye el Contrato Maestro JSON inspeccionando las tablas, claves e índices de un archivo .db."""
        tables: List[TableModel] = []
        relations: List[RelationModel] = []

        with self._connect(db_file) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            table_rows = cur.fetchall()
            table_names = [row[0] for row in table_rows]
            combined_ddl = "\n\n".join(row[1] for row in table_rows if row[1])
            computed_by_col, check_by_col = extract_table_column_constraints(combined_ddl)

            for idx, t_name in enumerate(table_names):
                t_q = quote_identifier(t_name, "sqlite")
                cur.execute(f"PRAGMA foreign_key_list({t_q})")
                fk_rows = cur.fetchall()
                # fk_rows: (id, seq, table, from, to, on_update, on_delete, match)
                fk_by_col: Dict[str, Dict[str, str]] = {}
                for fk in fk_rows:
                    fk_by_col[fk[3]] = {
                        "target_table": fk[2],
                        "target_column": fk[4] or "id",
                        "on_update": fk[5] or "CASCADE",
                        "on_delete": fk[6] or "RESTRICT",
                    }
                    relations.append(
                        RelationModel(
                            id=f"rel_{t_name}_{fk[3]}_{fk[2]}",
                            source_table=t_name,
                            source_column=fk[3],
                            target_table=fk[2],
                            target_column=fk[4] or "id",
                            cardinality="1:N",
                            on_delete=fk[6] if fk[6] in ("RESTRICT", "CASCADE", "SET NULL", "NO ACTION") else "RESTRICT",  # type: ignore[arg-type]
                            on_update=fk[5] if fk[5] in ("RESTRICT", "CASCADE", "SET NULL", "NO ACTION") else "CASCADE",  # type: ignore[arg-type]
                            tutor_explanation=f"Relación referencial entre {t_name}.{fk[3]} y {fk[2]}.{fk[4] or 'id'}.",
                        )
                    )

                cur.execute(f"PRAGMA index_list({t_q})")
                idx_rows = cur.fetchall()
                unique_cols = set()
                explicit_indexes: List[str] = []
                for idx_row in idx_rows:
                    idx_name = idx_row[1]
                    is_unique_idx = bool(idx_row[2])
                    idx_q = quote_identifier(idx_name, "sqlite")
                    cur.execute(f"PRAGMA index_info({idx_q})")
                    idx_cols = [r[2] for r in cur.fetchall() if r[2]]
                    if len(idx_cols) == 1:
                        if is_unique_idx:
                            unique_cols.add(idx_cols[0])
                        if not idx_name.startswith("sqlite_autoindex"):
                            explicit_indexes.append(idx_cols[0])

                cur.execute(f"PRAGMA table_xinfo({t_q})")
                col_rows = cur.fetchall()
                # table_xinfo: (cid, name, type, notnull, dflt_value, pk, hidden)
                cols: List[ColumnModel] = []
                pk_pairs: List[Tuple[int, str]] = []
                for cr in col_rows:
                    c_name = cr[1]
                    raw_type = cr[2] or "VARCHAR"
                    c_notnull = bool(cr[3])
                    c_default = str(cr[4]).strip("'") if cr[4] is not None else None
                    c_pk_ord = int(cr[5] or 0)
                    c_pk = c_pk_ord > 0
                    c_hidden = int(cr[6] or 0) if len(cr) > 6 else 0
                    if c_pk:
                        pk_pairs.append((c_pk_ord, c_name))

                    c_type = raw_type
                    c_len: Optional[int] = None
                    m_len = re.match(r"^(VARCHAR|CHAR)\s*\(\s*(\d+)\s*\)$", raw_type.strip(), flags=re.IGNORECASE)
                    if m_len:
                        c_type = m_len.group(1).upper()
                        c_len = int(m_len.group(2))

                    fk_info = fk_by_col.get(c_name)
                    sem = infer_column_type(c_name)
                    col_key = (t_name.lower(), c_name.lower())
                    comp_expr = computed_by_col.get(col_key) if c_hidden in (2, 3) else None
                    if c_hidden in (2, 3) and not comp_expr:
                        comp_expr = "/* calculada */"

                    cols.append(
                        ColumnModel(
                            name=c_name,
                            data_type=c_type,
                            length=c_len,
                            nullable=not c_notnull and not c_pk,
                            default_value=c_default,
                            is_pk=c_pk,
                            is_fk=fk_info is not None,
                            is_unique=c_name in unique_cols and not c_pk,
                            auto_increment=c_pk and c_name.lower() == "id" and "INT" in c_type.upper(),
                            check_constraint=check_by_col.get(col_key),
                            computed_expression=comp_expr,
                            computed_storage="STORED" if c_hidden == 3 else "VIRTUAL",
                            fk_target_table=fk_info["target_table"] if fk_info else None,
                            fk_target_column=fk_info["target_column"] if fk_info else None,
                            description=f"Columna {c_name} de {t_name}",
                            tutor_explanation=str(sem["tutor_explanation"]),
                        )
                    )

                pk_pairs.sort(key=lambda x: x[0])
                pk_list = [name for _, name in pk_pairs]
                if len(pk_list) > 1:
                    for c in cols:
                        c.auto_increment = False

                tables.append(
                    TableModel(
                        name=t_name,
                        description=f"Tabla introspeccionada desde {db_name}.db",
                        position_x=60.0 + (idx % 3) * 370.0,
                        position_y=60.0 + (idx // 3) * 330.0,
                        primary_key=pk_list,
                        columns=cols,
                        indexes=explicit_indexes,
                        tutor_explanation=f"Tabla '{t_name}' almacenada físicamente en SQLite.",
                    )
                )

            cur.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='view' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            views: List[ViewModel] = []
            for v_idx, (v_name, v_sql) in enumerate(cur.fetchall()):
                m_as = re.search(r"\bAS\b\s+(.+)$", v_sql or "", flags=re.IGNORECASE | re.DOTALL)
                sel_sql = m_as.group(1).strip().rstrip(";") if m_as else (v_sql or "")
                v_cols: List[str] = []
                try:
                    cur.execute(f"PRAGMA table_info({quote_identifier(v_name, 'sqlite')})")
                    v_cols = [r[1] for r in cur.fetchall() if r[1]]
                except sqlite3.Error:
                    pass
                views.append(
                    ViewModel(
                        name=v_name,
                        select_sql=sel_sql,
                        columns=v_cols,
                        description=f"Vista virtual en {db_name}.db",
                        position_x=60.0 + (v_idx % 3) * 340.0,
                        position_y=420.0 + (v_idx // 3) * 210.0,
                    )
                )

        return MasterSchemaContract(
            db_name=db_name,
            title=db_name.replace("_", " ").title(),
            description=f"Base de datos SQLite local ({db_name}.db)",
            dialect="sqlite",
            is_deployed=True,
            version=1,
            tables=tables,
            views=views,
            relations=relations,
        )

    def deploy_schema(
        self,
        contract: MasterSchemaContract,
        populate_mock_data: bool = False,
        mock_rows_per_table: int = 12,
        confirmed_destructive: bool = False,
    ) -> Dict[str, Any]:
        """
        Valida la consistencia del esquema, detecta migraciones destructivas sobre tablas pobladas,
        crea respaldo automático .db.bak antes de modificar estructuras existentes, registra la versión,
        materializa las tablas en SQLite dentro de una transacción segura y opcionalmente genera Mock Data.
        """
        clean_db = to_snake_case(contract.db_name) or "proyecto_sgbd"
        contract.db_name = clean_db
        self.auditor.audit_schema(contract)

        db_file = self._db_path(clean_db)
        meta_file = self._meta_path(clean_db)

        old_contract: Optional[MasterSchemaContract] = None
        if meta_file.exists():
            try:
                old_contract = MasterSchemaContract.model_validate(
                    json.loads(meta_file.read_text(encoding="utf-8"))
                )
            except Exception:
                old_contract = None
        elif db_file.exists():
            try:
                old_contract = self._introspect_sqlite_file(clean_db, db_file)
            except Exception:
                old_contract = None

        migration_diff = self.transpiler.generate_migration_diff(old_contract, contract)

        # Escudo Pre-Migración: si se van a eliminar tablas o columnas que ya contienen registros en disco,
        # exigir confirmación explícita antes de ejecutar la migración.
        if old_contract and db_file.exists() and migration_diff.get("is_destructive") and not confirmed_destructive:
            affected_tables_check = set(migration_diff.get("dropped_tables", []))
            for dc in migration_diff.get("dropped_columns", []):
                affected_tables_check.add(dc["table"])

            affected_rows = 0
            with self._connect(db_file) as conn_chk:
                cur_chk = conn_chk.cursor()
                for t_chk in affected_tables_check:
                    try:
                        cur_chk.execute(f"SELECT COUNT(*) FROM {quote_identifier(t_chk, 'sqlite')}")
                        affected_rows += int(cur_chk.fetchone()[0])
                    except sqlite3.Error:
                        pass

            if affected_rows > 0:
                return {
                    "requires_migration_confirmation": True,
                    "migration_warning": {
                        "db_name": clean_db,
                        "affected_rows": affected_rows,
                        "dropped_tables": migration_diff.get("dropped_tables", []),
                        "dropped_columns": migration_diff.get("dropped_columns", []),
                        "summary": migration_diff.get("summary", ""),
                    },
                    "schema_contract": contract.model_dump(),
                }

        # Crear respaldo automático .db.bak antes de aplicar cambios estructurales sobre una BD existente
        backup_path: Optional[str] = None
        if old_contract and db_file.exists() and migration_diff.get("alter_statements"):
            backup_file = self._create_pre_migration_backup(clean_db, db_file, old_contract.version)
            if backup_file:
                backup_path = str(backup_file)

        if old_contract:
            contract.version = old_contract.version + 1
        else:
            contract.version = 1

        ddl_bundle = self.transpiler.transpile_ddl(contract, "sqlite", force_idempotent=True)

        # Si la base de datos ya existía y es una evolución de esquema, aplicar migraciones
        # (CREATE TABLE, ALTER TABLE ADD COLUMN o reconstrucción transaccional de tabla) sin perder datos
        with self._connect(db_file) as conn:
            conn.execute("PRAGMA foreign_keys = OFF;")
            cur = conn.cursor()
            try:
                if old_contract and migration_diff["alter_statements"]:
                    for stmt in migration_diff["alter_statements"]:
                        try:
                            cur.execute(stmt)
                        except sqlite3.OperationalError as op_exc:
                            msg = str(op_exc).lower()
                            if "duplicate column name" in msg or "already exists" in msg:
                                continue
                            raise
                # Asegurar que todas las tablas e índices del contrato estén creados
                for stmt in ddl_bundle["statements"]:
                    cur.execute(stmt)
                conn.commit()
            except Exception as exc:
                conn.rollback()
                raise RuntimeError(f"Error transaccional al desplegar esquema: {exc}") from exc
            finally:
                conn.execute("PRAGMA foreign_keys = ON;")

        contract.is_deployed = True
        contract.updated_at = datetime.now().isoformat(timespec="seconds")

        # Guardar Contrato Maestro JSON actualizado
        meta_file.write_text(
            json.dumps(contract.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Registrar instantánea en el historial de versiones
        self._append_version_history(clean_db, contract, migration_diff)

        mock_summary = None
        if populate_mock_data:
            mock_summary = self.generate_mock_data(clean_db, rows_per_table=mock_rows_per_table)

        return {
            "requires_migration_confirmation": False,
            "db_name": clean_db,
            "db_path": str(db_file),
            "backup_path": backup_path,
            "version": contract.version,
            "schema_contract": contract.model_dump(),
            "ddl_executed": ddl_bundle["full_sql"],
            "migration": migration_diff,
            "mock_data": mock_summary,
        }

    def _create_pre_migration_backup(self, clean_db: str, db_file: Path, old_version: int) -> Optional[Path]:
        """Guarda una copia automática .db.bak en workspaces/backups/ antes de migrar (conserva las últimas 5)."""
        try:
            backups_dir = self.workspaces_dir / "backups"
            backups_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak_file = backups_dir / f"{clean_db}_v{old_version}_{stamp}.db.bak"
            shutil.copy2(db_file, bak_file)
            existing_baks = sorted(
                backups_dir.glob(f"{clean_db}_v*.db.bak"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for stale in existing_baks[5:]:
                try:
                    stale.unlink()
                except OSError:
                    pass
            return bak_file
        except Exception:
            return None

    def save_schema_layout(self, contract: MasterSchemaContract) -> Dict[str, Any]:
        """
        Persiste coordenadas X/Y del Lienzo ER y diagram_layout (posiciones Chen/Tablas y verbos)
        en .schema.json sin alterar la versión SQLite ni marcar como pendiente si ya estaba desplegado.
        """
        clean_db = to_snake_case(contract.db_name) or "proyecto_chemysql"
        meta_file = self._meta_path(clean_db)
        db_file = self._db_path(clean_db)
        if meta_file.exists():
            try:
                saved_contract = MasterSchemaContract.model_validate(
                    json.loads(meta_file.read_text(encoding="utf-8"))
                )
                pos_by_name = {t.name: (t.position_x, t.position_y) for t in contract.tables}
                for tbl in saved_contract.tables:
                    if tbl.name in pos_by_name:
                        tbl.position_x, tbl.position_y = pos_by_name[tbl.name]
                vpos_by_name = {v.name: (v.position_x, v.position_y) for v in (contract.views or [])}
                for vw in saved_contract.views:
                    if vw.name in vpos_by_name:
                        vw.position_x, vw.position_y = vpos_by_name[vw.name]
                saved_contract.diagram_layout = dict(contract.diagram_layout or {})
                saved_contract.ddl_style = contract.ddl_style
                if contract.ddl_identifier:
                    saved_contract.ddl_identifier = contract.ddl_identifier
                saved_contract.is_deployed = db_file.exists()
                meta_file.write_text(
                    json.dumps(saved_contract.model_dump(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                return {"saved": True, "db_name": clean_db, "is_deployed": saved_contract.is_deployed}
            except Exception:
                pass
        return {"saved": False, "db_name": clean_db, "is_deployed": False}

    def export_project_bundle(
        self,
        contract: MasterSchemaContract,
        include_data: bool = True,
    ) -> Dict[str, Any]:
        """
        Empaqueta el proyecto completo en formato portable .chemysql (JSON):
        incluye el Contrato Maestro (con posiciones ER, Chen/Paso a Tablas, verbos, reglas y notas),
        el historial completo de migraciones y opcionalmente la base SQLite .db embebida en Base64.
        """
        from backend import APP_VERSION

        clean_db = to_snake_case(contract.db_name) or "proyecto_chemysql"
        contract.db_name = clean_db
        hist_file = self._history_path(clean_db)
        raw_history: List[Dict[str, Any]] = []
        if hist_file.exists():
            try:
                raw_history = json.loads(hist_file.read_text(encoding="utf-8"))
            except Exception:
                raw_history = []

        db_file = self._db_path(clean_db)
        sqlite_b64: Optional[str] = None
        if include_data and db_file.exists() and db_file.stat().st_size <= 25 * 1024 * 1024:
            sqlite_b64 = base64.b64encode(db_file.read_bytes()).decode("ascii")

        bundle = {
            "format": "chemysql-project",
            "format_version": 1,
            "app_version": APP_VERSION,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "schema_contract": contract.model_dump(),
            "history": raw_history,
            "sqlite_db_base64": sqlite_b64,
        }
        content = json.dumps(bundle, ensure_ascii=False, indent=2)
        return {
            "filename": f"{clean_db}.chemysql",
            "mime_type": "application/json;charset=utf-8",
            "content": content,
            "has_embedded_db": sqlite_b64 is not None,
        }

    def import_project_bundle(self, raw_content: str) -> Dict[str, Any]:
        """
        Restaura un archivo .chemysql (o .schema.json) en la carpeta activa de workspaces/,
        reconstruyendo el Contrato Maestro, su maquetación ER/Chen/Tablas, historial y archivo .db.
        """
        data = json.loads(raw_content)
        if not isinstance(data, dict):
            raise ValueError("El archivo de proyecto no contiene un objeto JSON válido.")

        if data.get("format") == "chemysql-project" and "schema_contract" in data:
            contract = MasterSchemaContract.model_validate(data["schema_contract"])
            history = data.get("history") if isinstance(data.get("history"), list) else []
            sqlite_b64 = data.get("sqlite_db_base64")
        else:
            contract = MasterSchemaContract.model_validate(data)
            history = []
            sqlite_b64 = None

        clean_db = to_snake_case(contract.db_name) or "proyecto_importado"
        contract.db_name = clean_db
        db_file = self._db_path(clean_db)
        meta_file = self._meta_path(clean_db)
        hist_file = self._history_path(clean_db)

        restored_db = False
        if isinstance(sqlite_b64, str) and sqlite_b64.strip():
            db_bytes = base64.b64decode(sqlite_b64.encode("ascii"))
            if not db_bytes.startswith(b"SQLite format 3\x00"):
                raise ValueError("El bloque binario embebido no es una base de datos SQLite válida.")
            if db_file.exists():
                self._create_pre_migration_backup(clean_db, db_file, contract.version)
            db_file.write_bytes(db_bytes)
            restored_db = True

        contract.is_deployed = db_file.exists()
        self.auditor.audit_schema(contract)

        meta_file.write_text(
            json.dumps(contract.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if history:
            hist_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

        return {
            "imported": True,
            "db_name": clean_db,
            "restored_sqlite_db": restored_db,
            "schema_contract": contract.model_dump(),
            "ddl_previews": self.transpiler.build_all_ddl_previews(contract),
            "history": self.get_version_history(clean_db),
            "databases": self.list_databases(),
        }

    def _append_version_history(
        self,
        db_name: str,
        contract: MasterSchemaContract,
        migration_diff: Dict[str, Any],
    ) -> None:
        hist_file = self._history_path(db_name)
        history: List[Dict[str, Any]] = []
        if hist_file.exists():
            try:
                history = json.loads(hist_file.read_text(encoding="utf-8"))
            except Exception:
                history = []

        history.append(
            {
                "version_id": contract.version,
                "timestamp": contract.updated_at,
                "summary": migration_diff["summary"],
                "changes": migration_diff["changes"],
                "ddl_statements": migration_diff["alter_statements"],
                "table_count": len(contract.tables),
                "relation_count": len(contract.relations),
                "schema_snapshot": contract.model_dump(),
            }
        )
        hist_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_version_history(self, db_name: str) -> List[Dict[str, Any]]:
        hist_file = self._history_path(db_name)
        if not hist_file.exists():
            return []
        try:
            history = json.loads(hist_file.read_text(encoding="utf-8"))
            return list(reversed(history))
        except Exception:
            return []

    def delete_database(self, db_name: str) -> Dict[str, Any]:
        """Elimina completamente un proyecto (.db, .schema.json y .history.json) de workspaces/."""
        clean = to_snake_case(db_name)
        if not clean:
            raise ValueError("Nombre de base de datos no válido.")
        deleted_files: List[str] = []
        for path in (self._db_path(clean), self._meta_path(clean), self._history_path(clean)):
            if path.exists():
                path.unlink()
                deleted_files.append(path.name)
        return {
            "deleted": True,
            "db_name": clean,
            "deleted_files": deleted_files,
            "databases": self.list_databases(),
        }

    def generate_mock_data(self, db_name: str, rows_per_table: int = 12) -> Dict[str, Any]:
        """
        Generador determinista de datos sintéticos coherentes en español (Mock Data).
        Respeta orden topológico de tablas, claves foráneas reales, restricciones UNIQUE y tipos semánticos.
        """
        contract = self.load_or_introspect_schema(db_name)
        db_file = self._db_path(db_name)
        ordered_tables = self.transpiler._topological_sort_tables(contract.tables, contract.relations)

        inserted_counts: Dict[str, int] = {}
        parent_ids_by_table: Dict[str, List[int]] = {}

        with self._connect(db_file) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            cur = conn.cursor()

            for tbl in ordered_tables:
                # Obtener valores de PK ya existentes para calcular offset
                pk_col = tbl.primary_key[0] if tbl.primary_key else next((c.name for c in tbl.columns if c.is_pk), "id")
                tbl_q = quote_identifier(tbl.name, "sqlite")
                existing_count = 0
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {tbl_q}")
                    existing_count = int(cur.fetchone()[0])
                except sqlite3.Error:
                    existing_count = 0
                start_offset = existing_count + 1

                # Omitir columnas autoincrementales y columnas calculadas/generadas (GENERATED ALWAYS AS)
                insertable_cols = [
                    c for c in tbl.columns
                    if not (c.is_pk and c.auto_increment) and not c.computed_expression
                ]
                if not insertable_cols:
                    continue

                col_names_q = [quote_identifier(c.name, "sqlite") for c in insertable_cols]
                placeholders = ", ".join(["?"] * len(col_names_q))
                insert_sql = f"INSERT INTO {tbl_q} ({', '.join(col_names_q)}) VALUES ({placeholders})"

                target_rows = rows_per_table * 2 if tbl.is_associative else rows_per_table
                inserted_for_tbl = 0
                used_pairs: set = set()

                for row_idx in range(start_offset, start_offset + target_rows):
                    row_values: List[Any] = []
                    skip_row = False
                    fk_pair_tracker: List[Any] = []

                    for col in insertable_cols:
                        if col.is_fk and col.fk_target_table:
                            tgt_col = col.fk_target_column or "id"
                            cache_key = f"{col.fk_target_table}.{tgt_col}"
                            candidate_parent_ids = parent_ids_by_table.get(cache_key, [])
                            if not candidate_parent_ids:
                                try:
                                    tgt_t_q = quote_identifier(col.fk_target_table, "sqlite")
                                    tgt_c_q = quote_identifier(tgt_col, "sqlite")
                                    cur.execute(f"SELECT {tgt_c_q} FROM {tgt_t_q} LIMIT 200")
                                    candidate_parent_ids = [r[0] for r in cur.fetchall() if r[0] is not None]
                                except sqlite3.Error:
                                    candidate_parent_ids = []
                                parent_ids_by_table[cache_key] = candidate_parent_ids
                            if not candidate_parent_ids:
                                skip_row = True
                                break
                            chosen_fk = candidate_parent_ids[(row_idx + len(fk_pair_tracker)) % len(candidate_parent_ids)]
                            fk_pair_tracker.append(chosen_fk)
                            row_values.append(chosen_fk)
                        else:
                            val = self._synthesize_column_value(tbl.name, col, row_idx)
                            row_values.append(val)

                    if skip_row:
                        continue
                    if tbl.is_associative and len(fk_pair_tracker) >= 2:
                        pair_key = tuple(fk_pair_tracker[:2])
                        if pair_key in used_pairs:
                            fk_cols_only = [c for c in insertable_cols if c.is_fk]
                            if len(fk_cols_only) >= 2:
                                second_fk_col = fk_cols_only[1]
                                cache_key2 = f"{second_fk_col.fk_target_table}.{second_fk_col.fk_target_column or 'id'}"
                                cand_ids = parent_ids_by_table.get(cache_key2, [])
                                if cand_ids:
                                    alt_id = cand_ids[(row_idx * 3 + 1) % len(cand_ids)]
                                    fk_pos = [i for i, c in enumerate(insertable_cols) if c.is_fk][1]
                                    row_values[fk_pos] = alt_id
                                    pair_key = (fk_pair_tracker[0], alt_id)
                        used_pairs.add(pair_key)

                    try:
                        cur.execute(insert_sql, row_values)
                        inserted_for_tbl += 1
                    except sqlite3.IntegrityError:
                        continue

                try:
                    pk_q = quote_identifier(pk_col, "sqlite")
                    cur.execute(f"SELECT {pk_q} FROM {tbl_q}")
                    parent_ids_by_table[f"{tbl.name}.{pk_col}"] = [r[0] for r in cur.fetchall() if r[0] is not None]
                except sqlite3.Error:
                    pass
                inserted_counts[tbl.name] = inserted_for_tbl

            conn.commit()

        return {
            "db_name": db_name,
            "inserted_by_table": inserted_counts,
            "total_inserted": sum(inserted_counts.values()),
            "synthetic_notice": "Datos sintéticos generados determinísticamente respetando integridad referencial y restricciones UNIQUE.",
        }

    def _synthesize_column_value(
        self, table_name: str, col: ColumnModel, idx: int
    ) -> Any:
        c = col.name.lower()
        t = table_name.lower()
        ut = col.data_type.upper()

        nombres_persona = [
            "Elena Martínez",
            "Carlos Mendoza",
            "Lucía Fernández",
            "Javier Ortega",
            "Sofía Navarro",
            "Miguel Ángel Ruiz",
            "Carmen Salgado",
            "Alejandro Torres",
            "Paula Domínguez",
            "David Herrera",
            "Valeria Castro",
            "Daniel Morales",
            "Irene Delgado",
            "Pablo Serrano",
            "Clara Giménez",
            "Adrián Molina",
        ]
        marcas_vehiculo = [
            ("Toyota", "Corolla Hybrid"),
            ("Volkswagen", "Golf TDI"),
            ("Seat", "León FR"),
            ("Renault", "Clio E-Tech"),
            ("Peugeot", "3008 Allure"),
            ("Ford", "Focus ST-Line"),
            ("Hyundai", "Tucson Maxx"),
            ("Mazda", "CX-5 Zenith"),
            ("Audi", "A3 Sportback"),
            ("BMW", "Serie 3 320d"),
            ("Kia", "Sportage Drive"),
            ("Volvo", "XC40 Recharge"),
        ]
        piezas_taller = [
            ("Kit Pastillas de Freno Cerámicas", "Juego delantero de alta fricción homologado ECE-R90", 68.50),
            ("Filtro de Aceite Sintético LongLife", "Cartucho filtrante microporoso con válvula antirretorno", 18.90),
            ("Batería AGM Start-Stop 70Ah", "Batería de arranque en frío 760A libre de mantenimiento", 145.00),
            ("Amortiguador Hidráulico Gas Delantero", "Columna McPherson presurizada de doble tubo", 112.40),
            ("Correa de Distribución Reforzada + Bomba", "Kit completo de sincronización con tensor metálico", 215.80),
            ("Bujía de Encendido Iridio Laser", "Electrodo central de iridio de alta durabilidad", 24.50),
            ("Disco de Freno Ventilado 300mm", "Disco tratado térmicamente contra alabeo", 89.00),
            ("Embrague Bimasa Completo", "Plato de presión, disco orgánico y cojinete hidráulico", 340.00),
            ("Radiador de Refrigeración Aluminio", "Núcleo soldado de alto caudal térmico", 164.25),
            ("Sensor Sonda Lambda Banda Ancha", "Sonda de oxígeno pre-catalizador de 5 hilos", 96.70),
            ("Alternador Trifásico 140A", "Generador con regulador electrónico integrado", 228.00),
            ("Filtro de Habitáculo Carbón Activo", "Retención de polen, partículas PM2.5 y gases", 26.30),
        ]
        diagnosticos_taller = [
            "Sustitución de pastillas y discos delanteros por vibración en frenada; purgado de circuito DOT4.",
            "Revisión periódica de 60.000 km: cambio de aceite 5W30, filtro de aire, polen y reseteo de intervalo.",
            "Fallo de arranque en frío: comprobación de caída de tensión y reemplazo de batería AGM 70Ah.",
            "Cambio de kit de distribución completo y bomba de agua preventiva; ajuste de tensión nominal.",
            "Ruido en suspensión delantera derecha: sustitución de pareja de amortiguadores y alineado láser.",
            "Testigo de gestión motor activo (P0135): reemplazo de sonda lambda primaria y borrado de códigos DTC.",
        ]
        libros_catalogo = [
            ("Cien años de soledad", "Editorial Sudamericana"),
            ("El laberinto de los espíritus", "Planeta"),
            ("Sistemas de Bases de Datos Relacionales", "Reverté Técnica"),
            ("El nombre de la rosa", "Lumen"),
            ("Ficciones y Artificios", "Alianza Editorial"),
            ("Arquitectura Limpia de Software", "Anaya Multimedia"),
            ("La sombra del viento", "Booket"),
            ("Rayuela", "Alfaguara"),
            ("Diseño de Algoritmos y Grafos", "McGraw-Hill"),
            ("Crónica de una muerte anunciada", "Debolsillo"),
            ("Los detectives salvajes", "Anagrama"),
            ("Teoría Relacional de E.F. Codd", "Prensa Universitaria"),
        ]
        especialidades_medicas = [
            "Cardiología Clínica",
            "Traumatología y Ortopedia",
            "Dermatología Avanzada",
            "Medicina Interna",
            "Neurología",
            "Pediatría",
            "Oftalmología",
        ]
        ciudades = ["Madrid", "Barcelona", "Valencia", "Sevilla", "Bilbao", "Zaragoza", "Málaga", "Valladolid"]

        # Valores CHAR(n) acotados (ej. CHAR(1) cubierta='S', CHAR(3) cod_instalacion='I01', CHAR(9) dni/telefono)
        if ut == "CHAR" and col.length:
            if col.length == 1:
                if col.default_value:
                    return str(col.default_value).strip("'\"")[:1]
                return "S" if idx % 2 == 1 else "N"
            if col.length <= 5:
                prefix = (table_name[0] if table_name else "C").upper()
                return f"{prefix}{idx:0{col.length - 1}d}"[: col.length]
            if "telefono" in c and col.length == 9:
                return f"6{(idx * 17) % 10}{(idx * 31) % 10}{100 + (idx * 43) % 899:03d}{200 + (idx * 67) % 799:03d}"[:9]

        # Identificadores únicos y códigos
        if "dni" in c or "nif" in c or "cif" in c:
            letras = "TRWAGMYFPDXBNJZSQVHLCKE"
            num = 34000000 + idx * 1379 + (abs(hash(table_name)) % 900)
            return f"{num}{letras[num % 23]}"[:9]

        if "matricula" in c and "vehic" in t:
            consonantes = ["BCD", "FGH", "JKL", "MNP", "RST", "VWX"]
            num = 1040 + (idx * 273) % 8900
            letras_mat = consonantes[idx % len(consonantes)]
            return f"{num:04d}-{letras_mat}"

        if "isbn" in c:
            return f"978-84-{2040 + idx:04d}-{110 + idx * 7:03d}-{idx % 9}"

        if "codigo" in c or "sku" in c or "referencia" in c:
            prefix = table_name[:3].upper()
            return f"{prefix}-2026-{idx:04d}"

        if "email" in c or "correo" in c:
            person = nombres_persona[(idx - 1) % len(nombres_persona)]
            slug = to_snake_case(person).replace("_", ".")
            return f"{slug}.{idx}@dominio-chemysql.es"

        if "username" in c:
            person = nombres_persona[(idx - 1) % len(nombres_persona)]
            return f"{to_snake_case(person)}_{idx}"

        if "telefono" in c:
            return f"+34 6{(idx * 17) % 10}{(idx * 31) % 10} {100 + (idx * 43) % 899:03d} {200 + (idx * 67) % 799:03d}"

        if "marca" in c:
            return marcas_vehiculo[(idx - 1) % len(marcas_vehiculo)][0]

        if "modelo" in c:
            return marcas_vehiculo[(idx - 1) % len(marcas_vehiculo)][1]

        if "titulo" in c:
            if "libro" in t:
                return libros_catalogo[(idx - 1) % len(libros_catalogo)][0]
            return f"Título de {to_singular(table_name).title()} #{idx}"

        if "editorial" in c:
            return libros_catalogo[(idx - 1) % len(libros_catalogo)][1]

        if "especialidad" in c:
            return especialidades_medicas[(idx - 1) % len(especialidades_medicas)]

        if "ciudad" in c or "nacionalidad" in c:
            return ciudades[(idx - 1) % len(ciudades)]

        if "nombre" in c:
            if "pieza" in t or "producto" in t:
                return piezas_taller[(idx - 1) % len(piezas_taller)][0]
            if "categoria" in t:
                cats = ["Frenos y Fricción", "Motor y Filtración", "Sistema Eléctrico", "Suspensión y Dirección", "Transmisión", "Climatización"]
                return cats[(idx - 1) % len(cats)]
            if "departamento" in t:
                depts = ["Ingeniería de Datos", "Operaciones y Logística", "Atención al Cliente", "Finanzas y Contabilidad", "I+D+i"]
                return depts[(idx - 1) % len(depts)]
            return nombres_persona[(idx - 1) % len(nombres_persona)]

        if "diagnostico" in c or "descripcion" in c or "observaciones" in c or "motivo" in c:
            if "pieza" in t or "producto" in t:
                return piezas_taller[(idx - 1) % len(piezas_taller)][1]
            if "reparacion" in t:
                return diagnosticos_taller[(idx - 1) % len(diagnosticos_taller)]
            return f"Registro técnico verificado para {to_singular(table_name)} #{idx} en operación normal."

        if "metodo_pago" in c:
            metodos = ["Tarjeta Corporativa", "Transferencia SEPA", "Efectivo", "Domiciliación Bancaria"]
            return metodos[(idx - 1) % len(metodos)]

        if "estado" in c or "tipo" in c or "etiqueta" in c:
            estados = ["Completado", "En Proceso", "Verificado", "Prioritario"]
            return estados[(idx - 1) % len(estados)]

        # Booleanos
        if ut == "BOOLEAN" or c in ("activo", "pagado", "disponible", "devuelto", "completado", "confirmado", "principal"):
            return 1 if (idx % 4 != 0) else 0

        # Clave primaria numérica explícita no autoincremental (ej. cod_instalacion, cod_pista, num_socio)
        if col.is_pk and any(tok in ut for tok in ("INT", "SMALLINT", "TINYINT", "BIGINT")):
            return idx

        # Horas (TIME) — solo cuando es tipo TIME o columna de reloj (no num_horas ni precio_hora)
        if ut == "TIME" or (
            "hora" in c
            and not any(tok in ut for tok in ("INT", "DECIMAL", "NUMERIC", "FLOAT", "REAL"))
            and not c.startswith(("num_", "precio_", "coste_", "tarifa_"))
        ):
            hour = 8 + (idx % 12)
            minute = 0 if (idx % 2 == 0) else 30
            return f"{hour:02d}:{minute:02d}:00"

        # Fechas
        if "DATE" in ut or "fecha" in c:
            base_d = date(2026, 1, 15) + timedelta(days=(idx * 9) % 300)
            if "TIME" in ut or "registro" in c:
                return f"{base_d.isoformat()} {9 + (idx % 9):02d}:{(idx * 15) % 60:02d}:00"
            return base_d.isoformat()

        # Importes monetarios / Decimales (respetando escalas como DECIMAL(4,1) o DECIMAL(5,2))
        if "DECIMAL" in ut or "NUMERIC" in ut or "FLOAT" in ut or "REAL" in ut:
            if "largo" in c:
                return round(20.0 + (idx % 25) * 1.5, 1)
            if "ancho" in c:
                return round(10.0 + (idx % 15) * 1.0, 1)
            if "cuota" in c:
                return round(25.0 + (idx % 6) * 5.0, 2)
            if "pieza" in t and "precio" in c:
                return piezas_taller[(idx - 1) % len(piezas_taller)][2]
            return round(15.0 + (idx * 11.25) % 90.0, 2)

        # Enteros (respetando CHECK como num_horas <= 3 o BETWEEN 1 AND 3)
        if "INT" in ut:
            if "hora" in c or "TINYINT" in ut:
                return 1 + (idx % 3)
            if "anio" in c:
                return 2016 + (idx % 11)
            if "kilometraje" in c:
                return 18500 + (idx * 14200) % 195000
            if "stock" in c:
                return 6 + (idx * 7) % 85
            if "cantidad" in c:
                return 1 + (idx % 4)
            return idx

        return f"{col.name.title()} {idx}"

    def get_table_rows(
        self,
        db_name: str,
        table_name: str,
        page: int = 1,
        page_size: int = 25,
        search: str = "",
    ) -> Dict[str, Any]:
        """Obtiene los registros paginados de una tabla o vista junto con sus metadatos."""
        contract = self.load_or_introspect_schema(db_name)
        tbl = next((t for t in contract.tables if t.name == table_name), None)
        vw = None if tbl else next((v for v in (contract.views or []) if v.name == table_name), None)
        if not tbl and not vw:
            raise ValueError(f"La tabla o vista '{table_name}' no existe en '{db_name}'.")

        db_file = self._db_path(db_name)
        offset = max(0, (page - 1) * page_size)
        target_name = tbl.name if tbl else vw.name  # type: ignore[union-attr]
        tbl_q = quote_identifier(target_name, "sqlite")

        with self._connect(db_file) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            if tbl:
                col_names_for_search = [c.name for c in tbl.columns]
            else:
                if vw and vw.columns:
                    col_names_for_search = list(vw.columns)
                else:
                    cur.execute(f"SELECT * FROM {tbl_q} LIMIT 0")
                    col_names_for_search = [d[0] for d in (cur.description or [])]

            where_clause = ""
            params: List[Any] = []
            if search.strip() and col_names_for_search:
                like_parts = [
                    f"CAST({quote_identifier(cname, 'sqlite')} AS TEXT) LIKE ?"
                    for cname in col_names_for_search
                ]
                where_clause = " WHERE " + " OR ".join(like_parts)
                params = [f"%{search.strip()}%"] * len(col_names_for_search)

            cur.execute(f"SELECT COUNT(*) FROM {tbl_q}{where_clause}", params)
            total_rows = int(cur.fetchone()[0])

            cur.execute(
                f"SELECT * FROM {tbl_q}{where_clause} LIMIT ? OFFSET ?",
                params + [page_size, offset],
            )
            fetched = cur.fetchall()
            rows = [dict(r) for r in fetched]
            if vw and not col_names_for_search and cur.description:
                col_names_for_search = [d[0] for d in cur.description]

        col_payload = (
            [c.model_dump() for c in tbl.columns]
            if tbl
            else [
                {
                    "name": cname,
                    "data_type": "VIEW",
                    "nullable": True,
                    "is_pk": False,
                    "is_fk": False,
                    "is_unique": False,
                }
                for cname in col_names_for_search
            ]
        )

        return {
            "db_name": db_name,
            "table_name": target_name,
            "is_view": vw is not None,
            "view_select_sql": vw.select_sql if vw else None,
            "columns": col_payload,
            "rows": rows,
            "total_rows": total_rows,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total_rows + page_size - 1) // page_size),
        }

    def _resolve_valid_table_and_cols(
        self, db_name: str, table_name: str, required_cols: List[str]
    ) -> Tuple[TableModel, Dict[str, ColumnModel]]:
        contract = self.load_or_introspect_schema(db_name)
        tbl = next((t for t in contract.tables if t.name == table_name), None)
        if not tbl:
            if any(v.name == table_name for v in (contract.views or [])):
                raise ValueError(
                    f"La vista '{table_name}' es una consulta virtual de solo lectura; modifica los datos en sus tablas base."
                )
            raise ValueError(f"La tabla '{table_name}' no existe en '{db_name}'.")
        col_map = {c.name: c for c in tbl.columns}
        for col_name in required_cols:
            if col_name not in col_map:
                raise ValueError(f"La columna '{col_name}' no existe en la tabla '{table_name}'.")
        return tbl, col_map

    def get_fk_parent_record(
        self, db_name: str, target_table: str, target_column: str, value: Any
    ) -> Dict[str, Any]:
        """
        Previsualización instantánea de Clave Foránea para el Explorador de Datos Relacional:
        devuelve el registro completo de la tabla padre sin que el usuario tenga que escribir un JOIN.
        """
        self._resolve_valid_table_and_cols(db_name, target_table, [target_column])
        db_file = self._db_path(db_name)
        tbl_q = quote_identifier(target_table, "sqlite")
        col_q = quote_identifier(target_column, "sqlite")
        with self._connect(db_file) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                f"SELECT * FROM {tbl_q} WHERE {col_q} = ? LIMIT 1",
                (value,),
            )
            row = cur.fetchone()
            if not row:
                return {
                    "found": False,
                    "target_table": target_table,
                    "target_column": target_column,
                    "value": value,
                }
            record = dict(row)
            # Construir título resumen legible
            headline = next(
                (
                    str(record[k])
                    for k in ("nombre", "titulo", "matricula", "codigo", "dni", "email")
                    if k in record and record[k]
                ),
                f"{to_singular(target_table).title()} #{value}",
            )
            return {
                "found": True,
                "target_table": target_table,
                "target_column": target_column,
                "value": value,
                "headline": headline,
                "record": record,
            }

    def update_cell(
        self,
        db_name: str,
        table_name: str,
        target_column: str,
        new_value: Any,
        pk_column: Optional[str] = None,
        pk_value: Any = None,
        pk_values: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Actualiza una celda desde la cuadrícula del Explorador Relacional soportando PK simples y compuestas."""
        pk_map = pk_values if pk_values else ({pk_column: pk_value} if pk_column else {})
        if not pk_map:
            raise ValueError("Se requiere al menos una columna de clave primaria para actualizar el registro.")

        self._resolve_valid_table_and_cols(db_name, table_name, [target_column] + list(pk_map.keys()))
        tbl_q = quote_identifier(table_name, "sqlite")
        col_q = quote_identifier(target_column, "sqlite")
        where_parts = [f"{quote_identifier(k, 'sqlite')} = ?" for k in pk_map.keys()]
        params = [new_value] + list(pk_map.values())

        db_file = self._db_path(db_name)
        with self._connect(db_file) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            cur = conn.cursor()
            cur.execute(
                f"UPDATE {tbl_q} SET {col_q} = ? WHERE {' AND '.join(where_parts)}",
                params,
            )
            conn.commit()
        return {
            "updated": True,
            "table_name": table_name,
            "pk_value": pk_value if pk_value is not None else next(iter(pk_map.values())),
            "pk_values": pk_map,
            "column": target_column,
        }

    def insert_row(self, db_name: str, table_name: str, values: Dict[str, Any]) -> Dict[str, Any]:
        """Inserta un nuevo registro desde el Explorador de Datos Relacional."""
        clean_vals = {k: v for k, v in values.items() if v is not None and str(v).strip() != ""}
        if not clean_vals:
            raise ValueError("No se proporcionaron valores para insertar.")
        cols = list(clean_vals.keys())
        self._resolve_valid_table_and_cols(db_name, table_name, cols)
        tbl_q = quote_identifier(table_name, "sqlite")
        cols_q = [quote_identifier(c, "sqlite") for c in cols]
        placeholders = ", ".join(["?"] * len(cols))
        db_file = self._db_path(db_name)
        with self._connect(db_file) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            cur = conn.cursor()
            cur.execute(
                f"INSERT INTO {tbl_q} ({', '.join(cols_q)}) VALUES ({placeholders})",
                [clean_vals[c] for c in cols],
            )
            new_id = cur.lastrowid
            conn.commit()
        return {"inserted": True, "new_id": new_id}

    def delete_row(
        self,
        db_name: str,
        table_name: str,
        pk_column: Optional[str] = None,
        pk_value: Any = None,
        pk_values: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Elimina un registro puntual por clave primaria (simple o compuesta) respetando integridad referencial."""
        pk_map = pk_values if pk_values else ({pk_column: pk_value} if pk_column else {})
        if not pk_map:
            raise ValueError("Se requiere al menos una columna de clave primaria para eliminar el registro.")

        self._resolve_valid_table_and_cols(db_name, table_name, list(pk_map.keys()))
        tbl_q = quote_identifier(table_name, "sqlite")
        where_parts = [f"{quote_identifier(k, 'sqlite')} = ?" for k in pk_map.keys()]
        db_file = self._db_path(db_name)
        with self._connect(db_file) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            cur = conn.cursor()
            cur.execute(
                f"DELETE FROM {tbl_q} WHERE {' AND '.join(where_parts)}",
                list(pk_map.values()),
            )
            conn.commit()
        return {
            "deleted": True,
            "pk_value": pk_value if pk_value is not None else next(iter(pk_map.values())),
            "pk_values": pk_map,
        }

    def create_index_direct(
        self,
        db_name: str,
        table_name: str,
        column_name: str,
        schema_contract: Optional[MasterSchemaContract] = None,
    ) -> Dict[str, Any]:
        """Crea un índice óptimo en un clic tanto en la base de datos SQLite real como en el Contrato Maestro JSON."""
        idx_name = f"idx_{table_name}_{column_name}"
        idx_q = quote_identifier(idx_name, "sqlite", always=False)
        tbl_q = quote_identifier(table_name, "sqlite")
        col_q = quote_identifier(column_name, "sqlite")
        ddl = f"CREATE INDEX IF NOT EXISTS {idx_q} ON {tbl_q} ({col_q});"

        db_file = self._db_path(db_name)
        if db_file.exists():
            with self._connect(db_file) as conn:
                conn.execute(ddl)
                conn.commit()

        contract = schema_contract or self.load_or_introspect_schema(db_name)
        tbl = next((t for t in contract.tables if t.name.lower() == table_name.lower()), None)
        if tbl and column_name not in tbl.indexes:
            tbl.indexes.append(column_name)
        self.auditor.audit_schema(contract)

        meta_file = self._meta_path(db_name)
        if db_file.exists():
            meta_file.write_text(
                json.dumps(contract.model_dump(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        return {
            "created": True,
            "index_name": idx_name,
            "ddl": ddl,
            "schema_contract": contract.model_dump(),
        }

    def _normalize_sql_for_sqlite(self, stmt: str) -> str:
        """
        Adapta sintaxis clásica de MySQL/PostgreSQL a SQLite para que el editor funcione
        como un SGBD estándar sin fricciones (AUTO_INCREMENT, ENGINE=InnoDB, CHARSET, COLLATE, SHOW TABLES, DESCRIBE).
        """
        s = stmt.strip()
        upper = s.upper()

        if re.match(r"^SHOW\s+TABLES\b", upper):
            return "SELECT name AS tabla FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"

        m_desc = re.match(r"^(?:DESCRIBE|DESC)\s+[`\"'\[]?([a-zA-Z0-9_]+)[`\"'\]]?$", s, flags=re.IGNORECASE)
        if m_desc:
            return f"PRAGMA table_info({quote_identifier(m_desc.group(1), 'sqlite')})"

        if re.match(r"^(?:CREATE|ALTER)\s+TABLE\b", upper):
            # Eliminar opciones finales de tabla propias de MySQL: ENGINE=InnoDB DEFAULT CHARSET=... COLLATE=...
            s = re.sub(
                r"\)\s*(?:ENGINE\s*=\s*\w+|DEFAULT\s+CHARSET\s*=\s*\w+|CHARACTER\s+SET\s+\w+|COLLATE\s*=?\s*\w+|AUTO_INCREMENT\s*=\s*\d+|\s)+$",
                ")",
                s,
                flags=re.IGNORECASE,
            )
            # Eliminar CHARACTER SET / COLLATE a nivel de columna
            s = re.sub(r"\bCHARACTER\s+SET\s+[a-zA-Z0-9_]+\b", "", s, flags=re.IGNORECASE)
            s = re.sub(r"\bCOLLATE\s+[a-zA-Z0-9_]+\b", "", s, flags=re.IGNORECASE)
            s = re.sub(r"\bUNSIGNED\b", "", s, flags=re.IGNORECASE)
            # Traducir AUTO_INCREMENT a sintaxis válida SQLite
            s = re.sub(
                r"\b(?:INT|INTEGER|BIGINT|SMALLINT|TINYINT)\s+AUTO_INCREMENT\s+PRIMARY\s+KEY\b",
                "INTEGER PRIMARY KEY AUTOINCREMENT",
                s,
                flags=re.IGNORECASE,
            )
            s = re.sub(
                r"\b(?:INT|INTEGER|BIGINT|SMALLINT|TINYINT)\s+PRIMARY\s+KEY\s+AUTO_INCREMENT\b",
                "INTEGER PRIMARY KEY AUTOINCREMENT",
                s,
                flags=re.IGNORECASE,
            )
            s = re.sub(r"\bAUTO_INCREMENT\b", "AUTOINCREMENT", s, flags=re.IGNORECASE)
            # Traducir SERIAL PRIMARY KEY de PostgreSQL
            s = re.sub(r"\bSERIAL\s+PRIMARY\s+KEY\b", "INTEGER PRIMARY KEY AUTOINCREMENT", s, flags=re.IGNORECASE)

        return s

    def export_table_data(
        self,
        db_name: str,
        table_name: str,
        fmt: Literal["csv", "json", "sql"] = "csv",
    ) -> Dict[str, Any]:
        """Exporta todos los registros de una tabla o vista en formato CSV, JSON o script SQL."""
        contract = self.load_or_introspect_schema(db_name)
        tbl = next((t for t in contract.tables if t.name == table_name), None)
        vw = None if tbl else next((v for v in (contract.views or []) if v.name == table_name), None)
        if not tbl and not vw:
            raise ValueError(f"La tabla o vista '{table_name}' no existe en '{db_name}'.")

        target_name = tbl.name if tbl else vw.name  # type: ignore[union-attr]
        db_file = self._db_path(db_name)
        tbl_q = quote_identifier(target_name, "sqlite")
        with self._connect(db_file) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(f"SELECT * FROM {tbl_q}")
            fetched = cur.fetchall()
            rows = [dict(r) for r in fetched]
            col_names = [c.name for c in tbl.columns] if tbl else [d[0] for d in (cur.description or [])]

        if fmt == "json":
            content = json.dumps(rows, ensure_ascii=False, indent=2)
            return {
                "filename": f"{db_name}_{target_name}.json",
                "mime_type": "application/json;charset=utf-8",
                "content": content,
                "row_count": len(rows),
            }

        if fmt == "sql":
            if vw:
                ddl_vw = self.transpiler._build_create_view(vw, "sqlite", use_idempotent=False)
                return {
                    "filename": f"{db_name}_{vw.name}_view.sql",
                    "mime_type": "text/sql;charset=utf-8",
                    "content": ddl_vw + "\n",
                    "row_count": len(rows),
                }
            assert tbl is not None
            insertable_cols = [c.name for c in tbl.columns if not c.computed_expression]
            cols_sql = ", ".join(quote_identifier(c, "sqlite", always=False) for c in insertable_cols)
            tbl_ddl_q = quote_identifier(tbl.name, "sqlite", always=False)
            lines = [f"-- Exportación SQL de '{db_name}.{tbl.name}' ({len(rows)} registros)"]
            for row in rows:
                vals_sql = []
                for c in insertable_cols:
                    v = row.get(c)
                    if v is None:
                        vals_sql.append("NULL")
                    elif isinstance(v, (int, float)) and not isinstance(v, bool):
                        vals_sql.append(str(v))
                    else:
                        escaped = str(v).replace("'", "''")
                        vals_sql.append(f"'{escaped}'")
                lines.append(f"INSERT INTO {tbl_ddl_q} ({cols_sql}) VALUES ({', '.join(vals_sql)});")
            return {
                "filename": f"{db_name}_{tbl.name}.sql",
                "mime_type": "text/sql;charset=utf-8",
                "content": "\n".join(lines) + "\n",
                "row_count": len(rows),
            }

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=col_names, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        return {
            "filename": f"{db_name}_{target_name}.csv",
            "mime_type": "text/csv;charset=utf-8",
            "content": buf.getvalue(),
            "row_count": len(rows),
        }

    def export_full_database_sql(
        self,
        contract: MasterSchemaContract,
        dialect: Literal["sqlite", "mysql", "postgresql", "sqlserver"] = "sqlite",
        include_data: bool = True,
    ) -> Dict[str, Any]:
        """
        Exporta la base de datos completa en un único script .sql listo para ejecutar:
        1. DDL completo adaptado al dialecto destino en orden topológico (padres antes que hijas).
        2. Sentencias INSERT INTO en el mismo orden topológico omitiendo columnas calculadas,
           adaptando literales booleanos y IDENTITY_INSERT en SQL Server cuando hay datos en .db.
        """
        ddl_bundle = self.transpiler.transpile_ddl(contract, dialect)
        sections: List[str] = [ddl_bundle["full_sql"]]
        total_rows = 0

        db_file = self._db_path(contract.db_name)
        if include_data and db_file.exists():
            table_map = {t.name: t for t in contract.tables}
            data_blocks: List[str] = []

            with self._connect(db_file) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()

                for t_name in ddl_bundle["table_order"]:
                    tbl = table_map.get(t_name)
                    if not tbl:
                        continue
                    try:
                        cur.execute(f"SELECT * FROM {quote_identifier(t_name, 'sqlite')}")
                        rows = [dict(r) for r in cur.fetchall()]
                    except sqlite3.Error:
                        continue

                    if not rows:
                        continue

                    insertable_cols = [c for c in tbl.columns if not c.computed_expression]
                    if not insertable_cols:
                        continue

                    tbl_q = quote_identifier(tbl.name, dialect, always=False)
                    cols_sql = ", ".join(
                        quote_identifier(c.name, dialect, always=False) for c in insertable_cols
                    )
                    has_identity = dialect == "sqlserver" and any(
                        c.is_pk and c.auto_increment and len(tbl.primary_key) <= 1 for c in insertable_cols
                    )

                    lines: List[str] = [f"-- Datos de '{tbl.name}' ({len(rows)} registros)"]
                    if has_identity:
                        lines.append(f"SET IDENTITY_INSERT {tbl_q} ON;")

                    for row in rows:
                        vals_sql: List[str] = []
                        for col in insertable_cols:
                            v = row.get(col.name)
                            if v is None:
                                vals_sql.append("NULL")
                            elif col.data_type.upper() == "BOOLEAN":
                                truthy = str(v).strip().upper() in ("1", "TRUE", "T", "S", "YES")
                                if dialect == "postgresql":
                                    vals_sql.append("TRUE" if truthy else "FALSE")
                                else:
                                    vals_sql.append("1" if truthy else "0")
                            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                                vals_sql.append(str(v))
                            else:
                                escaped = str(v).replace("'", "''")
                                vals_sql.append(f"'{escaped}'")
                        lines.append(f"INSERT INTO {tbl_q} ({cols_sql}) VALUES ({', '.join(vals_sql)});")

                    if has_identity:
                        lines.append(f"SET IDENTITY_INSERT {tbl_q} OFF;\nGO")
                    elif dialect == "sqlserver":
                        lines.append("GO")

                    total_rows += len(rows)
                    data_blocks.append("\n".join(lines))

            if data_blocks:
                sections.append(
                    "-- ============================================================================\n"
                    f"-- VOLCADO DE DATOS EN ORDEN TOPOLÓGICO ({total_rows} registros totales)\n"
                    "-- ============================================================================\n\n"
                    + "\n\n".join(data_blocks)
                )

        content = "\n\n".join(sections) + "\n"
        clean_db = to_snake_case(contract.db_name) or "esquema"
        suffix = "completo" if (include_data and total_rows > 0) else "ddl"
        return {
            "filename": f"{clean_db}_{dialect}_{suffix}.sql",
            "mime_type": "text/sql;charset=utf-8",
            "content": content,
            "table_count": len(contract.tables),
            "row_count": total_rows,
        }

    def execute_query(
        self,
        db_name: str,
        sql: str,
        confirmed_dangerous: bool = False,
        page: int = 1,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """
        Ejecuta una consulta o script SQL multi-sentencia sobre el motor SQLite protegida por:
        1. Compatibilidad clásica DBMS (CREATE DATABASE, USE, SHOW DATABASES, SHOW TABLES, DESCRIBE, DDL MySQL/PostgreSQL).
        2. El Escudo Anti-Desastres (bloqueando UPDATE/DELETE sin WHERE y DROP/TRUNCATE con conteo exacto de impacto).
        3. El Analizador Dinámico de EXPLAIN QUERY PLAN (detectando Full Table Scans y ofreciendo índice en 1 clic).
        4. El Desglosador Lógico Paso a Paso del Modo Tutor y sincronización automática del Lienzo ER tras DDL.
        """
        statements = split_sql_statements(sql)
        if not statements:
            raise ValueError("El editor SQL está vacío. Escribe una sentencia SQL válida para ejecutar.")

        current_db = to_snake_case(db_name) or "proyecto_sgbd"

        # 1. Revisar cada sentencia con el Escudo Anti-Desastres antes de ejecutar
        if not confirmed_dangerous:
            for stmt in statements:
                safety = self.auditor.inspect_sql_safety(stmt)
                if safety.get("is_dangerous"):
                    target_table = safety.get("target_table", "")
                    affected_rows = 0
                    dependent_impacts: List[Dict[str, Any]] = []
                    db_file_check = self._db_path(current_db)
                    if db_file_check.exists():
                        contract = self.load_or_introspect_schema(current_db)
                        with self._connect(db_file_check) as conn:
                            cur = conn.cursor()
                            try:
                                cur.execute(f"SELECT COUNT(*) FROM {quote_identifier(target_table, 'sqlite')}")
                                affected_rows = int(cur.fetchone()[0])
                            except sqlite3.Error:
                                affected_rows = 0

                            for rel in contract.relations:
                                if rel.target_table.lower() == target_table.lower():
                                    dep_count = 0
                                    try:
                                        src_t_q = quote_identifier(rel.source_table, "sqlite")
                                        src_c_q = quote_identifier(rel.source_column, "sqlite")
                                        cur.execute(
                                            f"SELECT COUNT(*) FROM {src_t_q} WHERE {src_c_q} IS NOT NULL"
                                        )
                                        dep_count = int(cur.fetchone()[0])
                                    except sqlite3.Error:
                                        pass
                                    dependent_impacts.append(
                                        {
                                            "child_table": rel.source_table,
                                            "fk_column": rel.source_column,
                                            "on_delete_policy": rel.on_delete,
                                            "dependent_rows": dep_count,
                                        }
                                    )

                    return {
                        "blocked_by_shield": True,
                        "shield_report": {
                            **safety,
                            "affected_rows": affected_rows,
                            "dependent_tables": dependent_impacts,
                            "total_dependent_rows": sum(d["dependent_rows"] for d in dependent_impacts),
                            "safe_alternative": (
                                f"{stmt.strip().rstrip(';')} WHERE id = 1;"
                                if "WITHOUT_WHERE" in str(safety.get("statement_type"))
                                else f"SELECT * FROM {target_table} LIMIT 20;"
                            ),
                        },
                        "tutor_breakdown": self.tutor.decompose_sql_query(stmt),
                    }

        # 2. Ejecución atómica secuencial de todas las sentencias del script
        # Mantenemos una transacción abierta (isolation_level=None + BEGIN) por archivo .db para que,
        # si una sentencia posterior falla, SQLite haga ROLLBACK completo incluso de los CREATE TABLE previos.
        start_t = time.perf_counter()
        explain_steps: List[Dict[str, Any]] = []
        index_recommendations: List[Dict[str, Any]] = []
        columns: List[str] = []
        rows: List[Dict[str, Any]] = []
        rowcount = 0
        is_select = False
        schema_updated = False
        switched_db: Optional[str] = None
        execution_log: List[str] = []
        last_stmt_for_tutor = statements[-1]

        safe_page = max(1, int(page or 1))
        safe_page_size = max(1, min(1000, int(page_size or 100)))
        total_pages = 1
        truncated = False

        tx_conns: Dict[str, sqlite3.Connection] = {}
        tx_dirty: Set[str] = set()
        search_cursor = 0

        def get_tx_conn(target_db: str) -> sqlite3.Connection:
            if target_db in tx_conns:
                return tx_conns[target_db]
            db_file_target = self._db_path(target_db)
            conn_tx = sqlite3.connect(db_file_target, isolation_level=None)
            conn_tx.row_factory = sqlite3.Row
            conn_tx.execute("PRAGMA foreign_keys = ON;")
            tx_conns[target_db] = conn_tx
            return conn_tx

        try:
            for raw_stmt in statements:
                stmt_line, search_cursor = _locate_statement_line(sql, raw_stmt, search_cursor)

                # 2a. CREATE DATABASE <nombre> ...
                m_create_db = re.match(
                    r"^CREATE\s+DATABASE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"'\[]?([a-zA-Z0-9_]+)[`\"'\]]?",
                    raw_stmt,
                    flags=re.IGNORECASE,
                )
                if m_create_db:
                    new_db_slug = to_snake_case(m_create_db.group(1))
                    get_tx_conn(new_db_slug)
                    current_db = new_db_slug
                    switched_db = new_db_slug
                    schema_updated = True
                    execution_log.append(f"Base de datos '{new_db_slug}.db' creada correctamente.")
                    continue

                # 2b. USE <nombre>
                m_use_db = re.match(
                    r"^USE\s+[`\"'\[]?([a-zA-Z0-9_]+)[`\"'\]]?$",
                    raw_stmt.strip(),
                    flags=re.IGNORECASE,
                )
                if m_use_db:
                    target_db_slug = to_snake_case(m_use_db.group(1))
                    get_tx_conn(target_db_slug)
                    current_db = target_db_slug
                    switched_db = target_db_slug
                    schema_updated = True
                    execution_log.append(f"Contexto cambiado a la base de datos '{target_db_slug}.db'.")
                    continue

                # 2c. SHOW DATABASES
                if re.match(r"^SHOW\s+DATABASES\b", raw_stmt.strip(), flags=re.IGNORECASE):
                    all_dbs = self.list_databases()
                    is_select = True
                    columns = ["base_de_datos", "tablas", "filas", "tamano_kb"]
                    rows = [
                        {
                            "base_de_datos": f"{d['db_name']}.db",
                            "tablas": d["table_count"],
                            "filas": d["total_rows"],
                            "tamano_kb": d["size_kb"],
                        }
                        for d in all_dbs
                    ]
                    rowcount = len(rows)
                    execution_log.append(f"Listado de {rowcount} bases de datos locales.")
                    continue

                # 2d. Sentencias SQL estándar (DDL / DML / SELECT)
                norm_stmt = self._normalize_sql_for_sqlite(raw_stmt)
                upper_norm = norm_stmt.strip().upper()
                conn = get_tx_conn(current_db)
                cur = conn.cursor()

                stmt_is_select = upper_norm.startswith(("SELECT", "PRAGMA", "EXPLAIN", "WITH"))
                stmt_is_ddl = upper_norm.startswith(("CREATE", "ALTER", "DROP"))

                if not stmt_is_select and current_db not in tx_dirty:
                    conn.execute("BEGIN")
                    tx_dirty.add(current_db)

                if upper_norm.startswith("SELECT"):
                    try:
                        explain_steps = []
                        cur.execute(f"EXPLAIN QUERY PLAN {norm_stmt}")
                        for r in cur.fetchall():
                            r_dict = dict(r)
                            explain_steps.append(
                                {
                                    "id": r_dict.get("id", 0),
                                    "parent": r_dict.get("parent", 0),
                                    "detail": r_dict.get("detail", ""),
                                    "is_full_scan": "SCAN" in str(r_dict.get("detail", "")).upper()
                                    and "USING INDEX" not in str(r_dict.get("detail", "")).upper(),
                                }
                            )
                        index_recommendations = self.auditor.analyze_query_plan(norm_stmt, explain_steps)
                    except sqlite3.Error:
                        pass

                try:
                    cur.execute(norm_stmt)
                except sqlite3.Error as sql_exc:
                    rolled_back = False
                    for db_k in list(tx_dirty):
                        try:
                            tx_conns[db_k].execute("ROLLBACK")
                            rolled_back = True
                        except sqlite3.Error:
                            pass
                    tx_dirty.clear()
                    raw_msg = str(sql_exc)
                    snippet = raw_stmt.strip()
                    if len(snippet) > 260:
                        snippet = snippet[:260] + "..."
                    raise SQLExecutionDetailError(
                        f"Error SQL en línea {stmt_line}: {raw_msg}",
                        line=stmt_line,
                        statement=snippet,
                        raw_error=raw_msg,
                        hint=_build_sql_error_hint(raw_msg),
                        rolled_back=rolled_back,
                    ) from sql_exc

                if stmt_is_select and cur.description:
                    is_select = True
                    columns = [col[0] for col in cur.description]
                    fetched = cur.fetchall()
                    rowcount = len(fetched)
                    total_pages = max(1, (rowcount + safe_page_size - 1) // safe_page_size)
                    effective_page = min(safe_page, total_pages)
                    start_idx = (effective_page - 1) * safe_page_size
                    rows = [dict(r) for r in fetched[start_idx : start_idx + safe_page_size]]
                    truncated = rowcount > len(rows)
                    safe_page = effective_page
                    last_stmt_for_tutor = norm_stmt
                    execution_log.append(f"Consulta SELECT completada ({rowcount} filas).")
                else:
                    affected = cur.rowcount if cur.rowcount >= 0 else 0
                    rowcount += affected
                    if stmt_is_ddl:
                        schema_updated = True
                        execution_log.append(f"Sentencia DDL ejecutada: {norm_stmt.splitlines()[0][:70]}")
                    else:
                        execution_log.append(f"Sentencia DML ejecutada ({affected} filas afectadas).")

            # Confirmar todas las transacciones pendientes al finalizar sin errores
            for db_k in list(tx_dirty):
                tx_conns[db_k].execute("COMMIT")
            tx_dirty.clear()
        finally:
            for c_tx in tx_conns.values():
                try:
                    c_tx.close()
                except Exception:
                    pass

        elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)

        result: Dict[str, Any] = {
            "blocked_by_shield": False,
            "is_select": is_select,
            "columns": columns,
            "rows": rows,
            "row_count": rowcount,
            "page": safe_page,
            "page_size": safe_page_size,
            "total_pages": total_pages,
            "truncated": truncated,
            "elapsed_ms": elapsed_ms,
            "explain_plan": explain_steps,
            "index_recommendations": index_recommendations,
            "tutor_breakdown": self.tutor.decompose_sql_query(last_stmt_for_tutor),
            "execution_log": execution_log,
            "active_db_name": current_db,
            "switched_db": switched_db,
            "schema_updated": schema_updated,
        }

        if schema_updated:
            # Re-introspeccionar el archivo .db preservando metadatos visuales previos si existían
            db_file = self._db_path(current_db)
            meta_file = self._meta_path(current_db)
            prev_contract: Optional[MasterSchemaContract] = None
            if meta_file.exists():
                try:
                    prev_contract = MasterSchemaContract.model_validate(
                        json.loads(meta_file.read_text(encoding="utf-8"))
                    )
                except Exception:
                    prev_contract = None

            fresh_contract = self._introspect_sqlite_file(current_db, db_file)
            if prev_contract:
                fresh_contract.title = prev_contract.title
                fresh_contract.ddl_identifier = prev_contract.ddl_identifier
                fresh_contract.ddl_style = prev_contract.ddl_style
                fresh_contract.collation = prev_contract.collation
                fresh_contract.source_prompt = prev_contract.source_prompt
                fresh_contract.diagram_layout = dict(prev_contract.diagram_layout or {})
                prev_tbls = {t.name.lower(): t for t in prev_contract.tables}
                for tbl in fresh_contract.tables:
                    old_t = prev_tbls.get(tbl.name.lower())
                    if old_t:
                        tbl.position_x = old_t.position_x
                        tbl.position_y = old_t.position_y
                        tbl.is_associative = old_t.is_associative
                        tbl.is_historical = old_t.is_historical
                        tbl.functional_dependencies = list(old_t.functional_dependencies or [])
                        if old_t.description and "introspeccionada" not in old_t.description:
                            tbl.description = old_t.description
                prev_vws = {v.name.lower(): v for v in (prev_contract.views or [])}
                for vw in fresh_contract.views:
                    old_v = prev_vws.get(vw.name.lower())
                    if old_v:
                        vw.position_x = old_v.position_x
                        vw.position_y = old_v.position_y
                        if old_v.description and "Vista virtual en" not in old_v.description:
                            vw.description = old_v.description

            self.auditor.audit_schema(fresh_contract)
            meta_file.write_text(
                json.dumps(fresh_contract.model_dump(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            result["schema_contract"] = fresh_contract.model_dump()
            result["ddl_previews"] = self.transpiler.build_all_ddl_previews(fresh_contract)
            result["databases"] = self.list_databases()

        return result
