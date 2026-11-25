"""
Generador y Transpilador de Sentencias DDL/DML Multi-Dialecto (SQLite, MySQL/MariaDB, SQL Server, PostgreSQL).
Convierte el Contrato Maestro JSON en código SQL ejecutable, soporta claves primarias simples y compuestas,
columnas calculadas (GENERATED ALWAYS AS), restricciones CHECK, valores DEFAULT y cotejamiento (COLLATE).
"""

from __future__ import annotations
import re
from typing import Any, Dict, List, Literal, Optional, Set, Tuple

from backend.core.schema_model import (
    ColumnModel,
    MasterSchemaContract,
    RelationModel,
    TableModel,
)


SQL_RESERVED_WORDS: Set[str] = {
    "ADD", "ALL", "ALTER", "AND", "AS", "ASC", "BETWEEN", "BY", "CASE", "CHECK",
    "COLUMN", "CONSTRAINT", "CREATE", "CROSS", "CURRENT_DATE", "CURRENT_TIME",
    "CURRENT_TIMESTAMP", "DATABASE", "DEFAULT", "DELETE", "DESC", "DISTINCT",
    "DROP", "ELSE", "END", "EXISTS", "FOREIGN", "FROM", "FULL", "GROUP", "HAVING",
    "IN", "INDEX", "INNER", "INSERT", "INTO", "IS", "JOIN", "KEY", "LEFT", "LIKE",
    "LIMIT", "NOT", "NULL", "OFFSET", "ON", "OR", "ORDER", "OUTER", "PRIMARY",
    "REFERENCES", "RIGHT", "SELECT", "SET", "TABLE", "THEN", "TO", "TRIGGER",
    "UNION", "UNIQUE", "UPDATE", "USER", "USING", "VALUES", "VIEW", "WHEN",
    "WHERE", "WITH",
}


def quote_identifier(name: str, dialect: str = "sqlite", always: bool = True) -> str:
    """Escapa de forma segura un identificador SQL según el dialecto destino."""
    raw = str(name or "").strip()
    if (
        (raw.startswith('"') and raw.endswith('"'))
        or (raw.startswith("`") and raw.endswith("`"))
        or (raw.startswith("[") and raw.endswith("]"))
    ) and len(raw) >= 2:
        raw = raw[1:-1]
    if not raw:
        raise ValueError("Identificador SQL vacío no permitido.")

    needs_quote = (
        always
        or raw.upper() in SQL_RESERVED_WORDS
        or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", raw)
    )
    if not needs_quote:
        return raw

    if dialect == "mysql":
        return f"`{raw.replace('`', '``')}`"
    if dialect == "sqlserver":
        return f"[{raw.replace(']', ']]')}]"
    return f'"{raw.replace(chr(34), chr(34) * 2)}"'


def split_sql_statements(sql: str) -> List[str]:
    """Divide un script SQL multi-sentencia por ';' respetando cadenas entrecomilladas y comentarios."""
    statements: List[str] = []
    buf: List[str] = []
    in_single = False
    in_double = False
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if not in_single and not in_double and ch == "-" and nxt == "-":
            while i < n and sql[i] != "\n":
                i += 1
            continue
        if not in_single and not in_double and ch == "/" and nxt == "*":
            i += 2
            while i + 1 < n and not (sql[i] == "*" and sql[i + 1] == "/"):
                i += 1
            i += 2
            continue
        if ch == "'" and not in_double:
            if in_single and nxt == "'":
                buf.append("''")
                i += 2
                continue
            in_single = not in_single
            buf.append(ch)
        elif ch == '"' and not in_single:
            if in_double and nxt == '"':
                buf.append('""')
                i += 2
                continue
            in_double = not in_double
            buf.append(ch)
        elif ch == ";" and not in_single and not in_double:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def _extract_balanced_parens(text: str, open_idx: int) -> Optional[str]:
    """Devuelve el contenido interior de un paréntesis balanceado que abre en open_idx."""
    if open_idx >= len(text) or text[open_idx] != "(":
        return None
    depth = 1
    pos = open_idx + 1
    in_sq = False
    n = len(text)
    while pos < n and depth > 0:
        ch = text[pos]
        if ch == "'":
            if in_sq and pos + 1 < n and text[pos + 1] == "'":
                pos += 2
                continue
            in_sq = not in_sq
        elif not in_sq:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
        pos += 1
    if depth != 0:
        return None
    return text[open_idx + 1 : pos - 1].strip()


def extract_table_column_constraints(
    sql_text: str,
) -> Tuple[Dict[Tuple[str, str], str], Dict[Tuple[str, str], str]]:
    """
    Extrae expresiones GENERATED ALWAYS AS y CHECK por (tabla, columna)
    desde uno o más bloques CREATE TABLE evitando colisiones entre tablas
    y soportando paréntesis anidados (ej. CHECK (estado IN ('a','b'))).
    """
    computed_map: Dict[Tuple[str, str], str] = {}
    check_map: Dict[Tuple[str, str], str] = {}

    create_pat = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"'\[]?([a-zA-Z_][a-zA-Z0-9_]*)[`\"'\]]?\s*\(",
        flags=re.IGNORECASE,
    )
    for m in create_pat.finditer(sql_text):
        tbl_key = m.group(1).lower()
        body = _extract_balanced_parens(sql_text, m.end() - 1)
        if not body:
            continue

        for line in body.splitlines():
            m_col = re.match(r"^\s*[`\"'\[]?([a-zA-Z_][a-zA-Z0-9_]*)[`\"'\]]?\s+(.*)$", line)
            if not m_col:
                continue
            col_k = m_col.group(1).lower()
            rest = m_col.group(2)
            if col_k in ("constraint", "check", "primary", "foreign", "unique"):
                continue

            m_gen = re.search(r"\bGENERATED\s+ALWAYS\s+AS\s*\(", rest, flags=re.IGNORECASE)
            if m_gen:
                expr = _extract_balanced_parens(rest, m_gen.end() - 1)
                if expr:
                    computed_map[(tbl_key, col_k)] = expr
            else:
                m_ms = re.match(r"^AS\s*\(", rest, flags=re.IGNORECASE)
                if m_ms and col_k != "always":
                    expr = _extract_balanced_parens(rest, m_ms.end() - 1)
                    if expr:
                        computed_map[(tbl_key, col_k)] = expr

            m_chk = re.search(r"\bCHECK\s*\(", rest, flags=re.IGNORECASE)
            if m_chk:
                chk_expr = _extract_balanced_parens(rest, m_chk.end() - 1)
                if chk_expr:
                    check_map[(tbl_key, col_k)] = chk_expr

    return computed_map, check_map


class SQLTranspiler:
    """Transpilador determinista de esquemas multi-dialecto y migraciones incrementales."""

    def build_all_ddl_previews(self, contract: MasterSchemaContract) -> Dict[str, str]:
        return {
            "sqlite": self.transpile_ddl(contract, "sqlite")["full_sql"],
            "mysql": self.transpile_ddl(contract, "mysql")["full_sql"],
            "sqlserver": self.transpile_ddl(contract, "sqlserver")["full_sql"],
            "postgresql": self.transpile_ddl(contract, "postgresql")["full_sql"],
        }

    def transpile_ddl(
        self,
        contract: MasterSchemaContract,
        dialect: Optional[Literal["sqlite", "mysql", "postgresql", "sqlserver"]] = None,
    ) -> Dict[str, Any]:
        target_dialect = dialect or contract.dialect or "sqlite"
        ordered_tables = self._topological_sort_tables(contract.tables, contract.relations)
        rel_map: Dict[Tuple[str, str], RelationModel] = {
            (r.source_table, r.source_column): r for r in contract.relations
        }

        collation = contract.collation
        header_lines = [
            "-- ============================================================================",
            f"-- ChemySQL DDL Transpilado | Proyecto: {contract.title} ({contract.db_name})",
            f"-- Dialecto Destino: {target_dialect.upper()} | Versión de Esquema: v{contract.version}",
        ]
        if collation:
            header_lines.append(f"-- Cotejamiento (Collation): {collation}")
        header_lines.append("-- ============================================================================")

        preamble_stmts: List[str] = []
        if target_dialect == "sqlite":
            preamble_stmts.append("PRAGMA foreign_keys = ON;")
        elif target_dialect == "mysql":
            mysql_coll = self._resolve_collation(collation, "mysql")
            preamble_stmts.append(
                f"CREATE DATABASE IF NOT EXISTS {contract.db_name} CHARACTER SET utf8mb4 COLLATE {mysql_coll};"
            )
            preamble_stmts.append(f"USE {contract.db_name};")
            preamble_stmts.append("SET FOREIGN_KEY_CHECKS = 1;")
        elif target_dialect == "sqlserver":
            mssql_coll = self._resolve_collation(collation, "sqlserver")
            preamble_stmts.append(
                f"CREATE DATABASE {contract.db_name} COLLATE {mssql_coll};\nGO"
            )
            preamble_stmts.append(f"USE {contract.db_name};\nGO")
        elif target_dialect == "postgresql":
            preamble_stmts.append(f"-- Ejecutar conectado a la base de datos '{contract.db_name}'")

        statements: List[str] = []
        for tbl in ordered_tables:
            create_stmt = self._build_create_table(tbl, rel_map, target_dialect, collation)
            statements.append(create_stmt)

            tbl_q = quote_identifier(tbl.name, target_dialect, always=False)
            for idx_col in tbl.indexes:
                if any(c.name == idx_col for c in tbl.columns):
                    idx_name = quote_identifier(f"idx_{tbl.name}_{idx_col}", target_dialect, always=False)
                    col_q = quote_identifier(idx_col, target_dialect, always=False)
                    if target_dialect in ("sqlite", "postgresql"):
                        statements.append(
                            f"CREATE INDEX IF NOT EXISTS {idx_name} ON {tbl_q} ({col_q});"
                        )
                    elif target_dialect == "sqlserver":
                        statements.append(
                            f"CREATE INDEX {idx_name} ON {tbl_q} ({col_q});\nGO"
                        )
                    else:
                        statements.append(
                            f"CREATE INDEX {idx_name} ON {tbl_q} ({col_q});"
                        )

        full_script = "\n\n".join(["\n".join(header_lines)] + preamble_stmts + statements)
        return {
            "dialect": target_dialect,
            "full_sql": full_script,
            "statements": statements,
            "table_order": [t.name for t in ordered_tables],
        }

    def _resolve_collation(self, collation: Optional[str], dialect: str) -> str:
        raw = (collation or "").strip()
        upper = raw.upper()
        if dialect == "mysql":
            if "UTF8MB4" in upper:
                return raw
            if "AI" in upper and "CI" in upper:
                return "utf8mb4_0900_ai_ci"
            return "utf8mb4_spanish_ci"
        if dialect == "sqlserver":
            if "MODERN_SPANISH" in upper:
                return raw
            if not raw or "AI" in upper:
                return "Modern_Spanish_CI_AI"
            return "Modern_Spanish_CI_AS"
        return raw or "NOCASE"

    def _get_table_pk_columns(self, table: TableModel) -> List[str]:
        if table.primary_key:
            return list(table.primary_key)
        return [c.name for c in table.columns if c.is_pk]

    def _build_create_table(
        self,
        table: TableModel,
        rel_map: Dict[Tuple[str, str], RelationModel],
        dialect: str,
        collation: Optional[str],
    ) -> str:
        pk_cols = self._get_table_pk_columns(table)
        is_composite_pk = len(pk_cols) > 1

        col_defs: List[str] = []
        constraints: List[str] = []

        for col in table.columns:
            col_defs.append(
                self._format_column_def(
                    col,
                    dialect=dialect,
                    is_composite_pk=is_composite_pk,
                    collation=collation,
                )
            )

        if is_composite_pk:
            pk_list = ", ".join(quote_identifier(p, dialect, always=False) for p in pk_cols)
            constraints.append(f"    CONSTRAINT PK_{table.name} PRIMARY KEY ({pk_list})")

        for col in table.columns:
            if col.is_fk and col.fk_target_table:
                rel = rel_map.get((table.name, col.name))
                on_del = rel.on_delete if rel else "RESTRICT"
                on_upd = rel.on_update if rel else "CASCADE"
                target_col = col.fk_target_column or "id"
                col_q = quote_identifier(col.name, dialect, always=False)
                tgt_tbl_q = quote_identifier(col.fk_target_table, dialect, always=False)
                tgt_col_q = quote_identifier(target_col, dialect, always=False)
                if dialect == "sqlserver":
                    # SQL Server usa NO ACTION en lugar de RESTRICT
                    mssql_del = "NO ACTION" if on_del == "RESTRICT" else on_del
                    mssql_upd = "NO ACTION" if on_upd == "RESTRICT" else on_upd
                    constraints.append(
                        f"    CONSTRAINT FK_{table.name}_{col.name} FOREIGN KEY ({col_q}) "
                        f"REFERENCES {tgt_tbl_q}({tgt_col_q}) "
                        f"ON DELETE {mssql_del} ON UPDATE {mssql_upd}"
                    )
                else:
                    constraints.append(
                        f"    CONSTRAINT FK_{table.name}_{col.name} FOREIGN KEY ({col_q}) "
                        f"REFERENCES {tgt_tbl_q}({tgt_col_q}) "
                        f"ON DELETE {on_del} ON UPDATE {on_upd}"
                    )

        all_lines = col_defs + constraints
        body = ",\n".join(all_lines)
        comment = f"-- Tabla: {table.name} — {table.description}\n" if table.description else ""
        tbl_q = quote_identifier(table.name, dialect, always=False)

        if dialect == "mysql":
            mysql_coll = self._resolve_collation(collation, "mysql")
            suffix = f" ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE={mysql_coll};"
            return f"{comment}CREATE TABLE IF NOT EXISTS {tbl_q} (\n{body}\n){suffix}"
        if dialect == "sqlserver":
            return f"{comment}CREATE TABLE {tbl_q} (\n{body}\n);\nGO"
        return f"{comment}CREATE TABLE IF NOT EXISTS {tbl_q} (\n{body}\n);"

    def _format_column_def(
        self,
        col: ColumnModel,
        dialect: str,
        is_composite_pk: bool = False,
        collation: Optional[str] = None,
    ) -> str:
        col_q = quote_identifier(col.name, dialect, always=False)
        # 1. Columna calculada / generada (GENERATED ALWAYS AS)
        if col.computed_expression:
            expr = col.computed_expression.strip()
            sql_type = self._map_type_for_dialect(col.data_type, col.length, dialect)
            if dialect == "sqlserver":
                return f"    {col_q} AS ({expr})"
            if dialect == "postgresql":
                return f"    {col_q} {sql_type} GENERATED ALWAYS AS ({expr}) STORED"
            storage = col.computed_storage or "VIRTUAL"
            return f"    {col_q} {sql_type} GENERATED ALWAYS AS ({expr}) {storage}"

        # 2. Clave primaria simple autoincremental
        if col.is_pk and not is_composite_pk and col.auto_increment:
            if dialect == "sqlite":
                return f"    {col_q} INTEGER PRIMARY KEY AUTOINCREMENT"
            if dialect == "mysql":
                return f"    {col_q} INT AUTO_INCREMENT PRIMARY KEY"
            if dialect == "sqlserver":
                return f"    {col_q} INT IDENTITY(1,1) PRIMARY KEY"
            if dialect == "postgresql":
                return f"    {col_q} SERIAL PRIMARY KEY"

        sql_type = self._map_type_for_dialect(col.data_type, col.length, dialect)
        parts = [f"    {col_q}", sql_type]

        # Cotejamiento NOCASE en columnas de texto SQLite cuando el esquema pide CI
        if (
            dialect == "sqlite"
            and collation
            and ("CI" in collation.upper() or "NOCASE" in collation.upper())
            and any(t in sql_type.upper() for t in ("VARCHAR", "CHAR", "TEXT"))
        ):
            parts.append("COLLATE NOCASE")

        if not col.nullable or col.is_pk:
            parts.append("NOT NULL")

        if col.is_pk and not is_composite_pk:
            parts.append("PRIMARY KEY")

        if col.is_unique and not col.is_pk:
            parts.append("UNIQUE")

        if col.default_value is not None and str(col.default_value).strip() != "":
            def_val = str(col.default_value).strip()
            upper_def = def_val.upper()
            is_sql_func = upper_def in (
                "CURRENT_TIMESTAMP",
                "CURRENT_DATE",
                "CURRENT_TIME",
                "GETDATE()",
                "NOW()",
                "TRUE",
                "FALSE",
                "NULL",
            ) or (def_val.startswith("(") and def_val.endswith(")"))
            if is_sql_func or re.match(r"^-?\d+(\.\d+)?$", def_val):
                if col.data_type.upper() == "BOOLEAN":
                    if dialect == "postgresql":
                        def_val = "TRUE" if upper_def in ("1", "TRUE") else "FALSE"
                    elif dialect in ("sqlite", "sqlserver") and upper_def in ("TRUE", "FALSE"):
                        def_val = "1" if upper_def == "TRUE" else "0"
                parts.append(f"DEFAULT {def_val}")
            else:
                clean_str = def_val.strip("'\"").replace("'", "''")
                parts.append(f"DEFAULT '{clean_str}'")

        if col.check_constraint:
            chk = col.check_constraint.strip()
            if chk.startswith("(") and chk.endswith(")"):
                chk = chk[1:-1].strip()
            parts.append(f"CHECK ({chk})")

        return " ".join(parts)

    def _map_type_for_dialect(self, data_type: str, length: Optional[int], dialect: str) -> str:
        ut = data_type.upper().strip()
        if ut == "VARCHAR":
            size = length or 150
            return f"VARCHAR({size})"
        if ut == "CHAR":
            size = length or 10
            return f"CHAR({size})"
        if ut.startswith("DECIMAL"):
            if dialect == "postgresql":
                return ut.replace("DECIMAL", "NUMERIC")
            return ut
        if ut == "TINYINT":
            if dialect == "postgresql":
                return "SMALLINT"
            return "TINYINT"
        if ut == "DATETIME":
            if dialect == "postgresql":
                return "TIMESTAMP"
            if dialect == "sqlserver":
                return "DATETIME2"
            return "DATETIME"
        if ut == "BOOLEAN":
            if dialect == "sqlite":
                return "INTEGER"
            if dialect == "sqlserver":
                return "BIT"
            return "BOOLEAN"
        return ut

    def _topological_sort_tables(
        self, tables: List[TableModel], relations: List[RelationModel]
    ) -> List[TableModel]:
        """Ordena las tablas de modo que las tablas padre se creen antes que las tablas hijas."""
        table_map = {t.name: t for t in tables}
        deps: Dict[str, Set[str]] = {t.name: set() for t in tables}

        for tbl in tables:
            for col in tbl.columns:
                if col.is_fk and col.fk_target_table and col.fk_target_table in table_map:
                    if col.fk_target_table != tbl.name:
                        deps[tbl.name].add(col.fk_target_table)

        for rel in relations:
            if rel.source_table in deps and rel.target_table in table_map:
                if rel.source_table != rel.target_table:
                    deps[rel.source_table].add(rel.target_table)

        ordered: List[TableModel] = []
        visited: Set[str] = set()

        while len(ordered) < len(tables):
            progressed = False
            for tbl in tables:
                if tbl.name in visited:
                    continue
                if deps[tbl.name].issubset(visited):
                    ordered.append(tbl)
                    visited.add(tbl.name)
                    progressed = True
            if not progressed:
                for tbl in tables:
                    if tbl.name not in visited:
                        ordered.append(tbl)
                        visited.add(tbl.name)

        return ordered

    def _table_needs_rebuild(
        self,
        old_tbl: TableModel,
        new_tbl: TableModel,
        old_rel_map: Dict[Tuple[str, str], RelationModel],
        new_rel_map: Dict[Tuple[str, str], RelationModel],
    ) -> bool:
        """Determina si una tabla SQLite requiere reconstrucción transaccional (drop/alter col, PK o FK)."""
        if self._get_table_pk_columns(old_tbl) != self._get_table_pk_columns(new_tbl):
            return True

        old_cols = {c.name: c for c in old_tbl.columns}
        new_cols = {c.name: c for c in new_tbl.columns}

        # Alguna columna fue eliminada
        if any(name not in new_cols for name in old_cols):
            return True

        # Alguna columna existente cambió tipo, nulabilidad, unicidad, default, check, expresión o FK
        for name, old_c in old_cols.items():
            new_c = new_cols[name]
            if (
                old_c.data_type.upper() != new_c.data_type.upper()
                or old_c.length != new_c.length
                or old_c.nullable != new_c.nullable
                or old_c.is_pk != new_c.is_pk
                or old_c.is_unique != new_c.is_unique
                or (old_c.default_value or "") != (new_c.default_value or "")
                or (old_c.check_constraint or "") != (new_c.check_constraint or "")
                or (old_c.computed_expression or "") != (new_c.computed_expression or "")
                or old_c.is_fk != new_c.is_fk
                or old_c.fk_target_table != new_c.fk_target_table
                or (old_c.fk_target_column or "id") != (new_c.fk_target_column or "id")
            ):
                return True

            old_rel = old_rel_map.get((old_tbl.name, name))
            new_rel = new_rel_map.get((new_tbl.name, name))
            if (old_rel is None) != (new_rel is None):
                return True
            if old_rel and new_rel and (
                old_rel.on_delete != new_rel.on_delete or old_rel.on_update != new_rel.on_update
            ):
                return True

        return False

    def generate_migration_diff(
        self,
        old_contract: Optional[MasterSchemaContract],
        new_contract: MasterSchemaContract,
    ) -> Dict[str, Any]:
        """
        Compara una versión anterior del esquema con la nueva versión aprobada
        y genera sentencias de migración real en SQLite:
        - CREATE TABLE en orden topológico para tablas nuevas
        - ALTER TABLE ADD COLUMN para columnas añadidas sin cambios destructivos
        - Reconstrucción transaccional de tabla (RENAME -> CREATE -> INSERT SELECT -> DROP)
          para columnas eliminadas/modificadas o cambios en PK/FK sin perder datos
        - CREATE INDEX / DROP INDEX para índices añadidos o eliminados
        - DROP TABLE en orden topológico inverso para tablas eliminadas
        """
        if not old_contract:
            ddl_info = self.transpile_ddl(new_contract, "sqlite")
            return {
                "summary": f"Despliegue inicial del esquema con {len(new_contract.tables)} tablas.",
                "alter_statements": ddl_info["statements"],
                "changes": [f"Creada tabla '{t.name}' ({len(t.columns)} columnas)" for t in new_contract.tables],
            }

        old_tables = {t.name: t for t in old_contract.tables}
        new_tables = {t.name: t for t in new_contract.tables}
        old_rel_map: Dict[Tuple[str, str], RelationModel] = {
            (r.source_table, r.source_column): r for r in old_contract.relations
        }
        new_rel_map: Dict[Tuple[str, str], RelationModel] = {
            (r.source_table, r.source_column): r for r in new_contract.relations
        }

        ordered_new = self._topological_sort_tables(new_contract.tables, new_contract.relations)
        ordered_old = self._topological_sort_tables(old_contract.tables, old_contract.relations)

        alter_statements: List[str] = []
        changes: List[str] = []

        for new_tbl in ordered_new:
            t_name = new_tbl.name
            tbl_q = quote_identifier(t_name, "sqlite", always=False)
            if t_name not in old_tables:
                stmt = self._build_create_table(new_tbl, new_rel_map, "sqlite", new_contract.collation)
                alter_statements.append(stmt)
                changes.append(f"Nueva tabla añadida: '{t_name}'")
                for idx_col in new_tbl.indexes:
                    idx_name = quote_identifier(f"idx_{t_name}_{idx_col}", "sqlite", always=False)
                    col_q = quote_identifier(idx_col, "sqlite", always=False)
                    alter_statements.append(
                        f"CREATE INDEX IF NOT EXISTS {idx_name} ON {tbl_q} ({col_q});"
                    )
            else:
                old_tbl = old_tables[t_name]
                old_cols = {c.name: c for c in old_tbl.columns}

                if self._table_needs_rebuild(old_tbl, new_tbl, old_rel_map, new_rel_map):
                    tmp_name = f"__chemysql_tmp_{t_name}"
                    tmp_q = quote_identifier(tmp_name, "sqlite")
                    tbl_q_strict = quote_identifier(t_name, "sqlite")

                    alter_statements.append(f"DROP TABLE IF EXISTS {tmp_q};")
                    alter_statements.append(f"ALTER TABLE {tbl_q_strict} RENAME TO {tmp_q};")
                    alter_statements.append(
                        self._build_create_table(new_tbl, new_rel_map, "sqlite", new_contract.collation)
                    )

                    common_cols = [
                        c.name
                        for c in new_tbl.columns
                        if c.name in old_cols and not c.computed_expression
                    ]
                    if common_cols:
                        cols_csv = ", ".join(quote_identifier(c, "sqlite") for c in common_cols)
                        alter_statements.append(
                            f"INSERT INTO {tbl_q_strict} ({cols_csv}) SELECT {cols_csv} FROM {tmp_q};"
                        )
                    alter_statements.append(f"DROP TABLE {tmp_q};")

                    for idx_col in new_tbl.indexes:
                        idx_name = quote_identifier(f"idx_{t_name}_{idx_col}", "sqlite", always=False)
                        col_q = quote_identifier(idx_col, "sqlite", always=False)
                        alter_statements.append(
                            f"CREATE INDEX IF NOT EXISTS {idx_name} ON {tbl_q} ({col_q});"
                        )
                    changes.append(f"Tabla reconstruida preservando datos: '{t_name}'")
                else:
                    for col in new_tbl.columns:
                        if col.name not in old_cols:
                            col_def = self._format_column_def(col, "sqlite", collation=new_contract.collation).strip()
                            if "NOT NULL" in col_def and "DEFAULT" not in col_def and not col.computed_expression:
                                default_fallback = "0" if "INT" in col_def or "DECIMAL" in col_def else "''"
                                col_def += f" DEFAULT {default_fallback}"
                            alter_stmt = f"ALTER TABLE {tbl_q} ADD COLUMN {col_def};"
                            alter_statements.append(alter_stmt)
                            changes.append(f"Columna añadida: '{t_name}.{col.name}' ({col.data_type})")

                    old_idx_set = set(old_tbl.indexes)
                    new_idx_set = set(new_tbl.indexes)
                    for idx_col in new_tbl.indexes:
                        if idx_col not in old_idx_set:
                            idx_name = quote_identifier(f"idx_{t_name}_{idx_col}", "sqlite", always=False)
                            col_q = quote_identifier(idx_col, "sqlite", always=False)
                            alter_statements.append(
                                f"CREATE INDEX IF NOT EXISTS {idx_name} ON {tbl_q} ({col_q});"
                            )
                            changes.append(f"Índice creado: 'idx_{t_name}_{idx_col}' sobre '{t_name}({idx_col})'")
                    for old_idx_col in old_tbl.indexes:
                        if old_idx_col not in new_idx_set:
                            idx_name = quote_identifier(f"idx_{t_name}_{old_idx_col}", "sqlite", always=False)
                            alter_statements.append(f"DROP INDEX IF EXISTS {idx_name};")
                            changes.append(f"Índice eliminado: 'idx_{t_name}_{old_idx_col}'")

        for old_tbl in reversed(ordered_old):
            if old_tbl.name not in new_tables:
                old_q = quote_identifier(old_tbl.name, "sqlite", always=False)
                alter_statements.append(f"DROP TABLE IF EXISTS {old_q};")
                changes.append(f"Tabla eliminada: '{old_tbl.name}'")

        summary = "; ".join(changes) if changes else "Actualización de metadatos y políticas de relación."
        return {
            "summary": summary,
            "alter_statements": alter_statements,
            "changes": changes,
        }

    def parse_ddl_to_contract(
        self,
        sql_text: str,
        base_contract: Optional[MasterSchemaContract] = None,
    ) -> MasterSchemaContract:
        """
        Sincronización bidireccional (Código DDL -> Contrato Maestro JSON):
        Ejecuta el DDL editado por el usuario en una instancia SQLite en memoria (:memory:),
        extrae la estructura real (tablas, columnas, PK simples/compuestas, FK, UNIQUE, CHECK,
        DEFAULT y columnas calculadas) y preserva las posiciones X/Y del Lienzo ER.
        """
        import sqlite3
        from datetime import datetime

        # Normalizar sintaxis MySQL / SQL Server / PostgreSQL a SQLite para parseo determinista
        cleaned_stmts: List[str] = []
        raw_text = re.sub(r"\bGO\b", ";", sql_text, flags=re.IGNORECASE)
        for chunk in split_sql_statements(raw_text):
            no_comments = chunk.strip()
            if not no_comments:
                continue
            upper = no_comments.upper()
            if upper.startswith(("CREATE DATABASE", "IF DB_ID", "USE ", "SET FOREIGN_KEY_CHECKS", "PRAGMA")):
                continue
            # Adaptar sintaxis de otros dialectos
            stmt = re.sub(
                r"\)\s*(?:ENGINE\s*=\s*\w+|DEFAULT\s+CHARSET\s*=\s*\w+|CHARACTER\s+SET\s+\w+|COLLATE\s*=?\s*\w+|AUTO_INCREMENT\s*=\s*\d+|\s)+$",
                ")",
                no_comments,
                flags=re.IGNORECASE,
            )
            stmt = re.sub(r"\bINT\s+IDENTITY\s*\(\s*\d+\s*,\s*\d+\s*\)\s+PRIMARY\s+KEY\b", "INTEGER PRIMARY KEY AUTOINCREMENT", stmt, flags=re.IGNORECASE)
            stmt = re.sub(r"\b(?:INT|INTEGER)\s+AUTO_INCREMENT\s+PRIMARY\s+KEY\b", "INTEGER PRIMARY KEY AUTOINCREMENT", stmt, flags=re.IGNORECASE)
            stmt = re.sub(r"\bSERIAL\s+PRIMARY\s+KEY\b", "INTEGER PRIMARY KEY AUTOINCREMENT", stmt, flags=re.IGNORECASE)
            # SQL Server computed column: col AS (expr) -> col DECIMAL(10,2) GENERATED ALWAYS AS (expr) VIRTUAL (sin tocar GENERATED ALWAYS AS)
            if "GENERATED ALWAYS AS" not in stmt.upper():
                stmt = re.sub(
                    r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\(([^)]+)\)",
                    r"\1 DECIMAL(10,2) GENERATED ALWAYS AS (\2) VIRTUAL",
                    stmt,
                    flags=re.IGNORECASE,
                )
            cleaned_stmts.append(stmt)

        old_positions: Dict[str, Tuple[float, float]] = {}
        if base_contract:
            for t in base_contract.tables:
                old_positions[t.name.lower()] = (t.position_x, t.position_y)

        # Extraer expresiones GENERATED ALWAYS AS y CHECK por (tabla, columna) sin colisiones
        computed_by_col, check_by_col = extract_table_column_constraints(sql_text)

        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("PRAGMA foreign_keys = OFF;")
            cur = conn.cursor()
            for stmt in cleaned_stmts:
                cur.execute(stmt)

            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            table_names = [row[0] for row in cur.fetchall()]

            tables: List[TableModel] = []
            relations: List[RelationModel] = []

            for idx, t_name in enumerate(table_names):
                t_q = quote_identifier(t_name, "sqlite")
                cur.execute(f"PRAGMA foreign_key_list({t_q})")
                fk_by_col: Dict[str, Dict[str, str]] = {}
                for fk in cur.fetchall():
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
                unique_cols: Set[str] = set()
                explicit_indexes: List[str] = []
                for idx_row in cur.fetchall():
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
                cols: List[ColumnModel] = []
                pk_pairs: List[Tuple[int, str]] = []
                for cr in cur.fetchall():
                    c_name = cr[1]
                    raw_type = cr[2] or "VARCHAR"
                    c_notnull = bool(cr[3])
                    c_default = str(cr[4]).strip("'") if cr[4] is not None else None
                    c_pk_ord = int(cr[5] or 0)
                    c_pk = c_pk_ord > 0
                    c_hidden = int(cr[6] or 0) if len(cr) > 6 else 0
                    if c_pk:
                        pk_pairs.append((c_pk_ord, c_name))

                    # Separar VARCHAR(50) / CHAR(9) en data_type + length
                    c_type = raw_type
                    c_len: Optional[int] = None
                    m_len = re.match(r"^(VARCHAR|CHAR)\s*\(\s*(\d+)\s*\)$", raw_type.strip(), flags=re.IGNORECASE)
                    if m_len:
                        c_type = m_len.group(1).upper()
                        c_len = int(m_len.group(2))

                    fk_info = fk_by_col.get(c_name)
                    col_key = (t_name.lower(), c_name.lower())
                    comp_expr = computed_by_col.get(col_key) if c_hidden in (2, 3) else None

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
                            description=f"Columna {c_name} editada desde código DDL",
                            tutor_explanation=f"Columna '{c_name}' ({raw_type}) sincronizada desde el código DDL.",
                        )
                    )

                pk_pairs.sort(key=lambda x: x[0])
                pk_list = [name for _, name in pk_pairs]
                pos_x, pos_y = old_positions.get(
                    t_name.lower(), (20.0 + (idx % 3) * 324.0, 20.0 + (idx // 3) * 288.0)
                )

                tables.append(
                    TableModel(
                        name=t_name,
                        description=f"Tabla {t_name} sincronizada desde código DDL",
                        position_x=pos_x,
                        position_y=pos_y,
                        primary_key=pk_list,
                        columns=cols,
                        indexes=explicit_indexes,
                        tutor_explanation=f"Tabla '{t_name}' actualizada directamente desde el editor DDL.",
                    )
                )
        finally:
            conn.close()

        return MasterSchemaContract(
            db_name=base_contract.db_name if base_contract else "esquema_ddl",
            title=base_contract.title if base_contract else "Esquema Editado en DDL",
            description=base_contract.description if base_contract else "",
            source_prompt=base_contract.source_prompt if base_contract else "",
            dialect=base_contract.dialect if base_contract else "sqlite",
            collation=base_contract.collation if base_contract else None,
            is_deployed=False,
            version=base_contract.version if base_contract else 1,
            updated_at=datetime.now().isoformat(timespec="seconds"),
            tables=tables,
            relations=relations,
            audit_alerts=[],
            tutor_metadata=base_contract.tutor_metadata if base_contract else {},
        )
