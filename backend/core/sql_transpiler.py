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
    ViewModel,
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
        force_idempotent: bool = False,
    ) -> Dict[str, Any]:
        target_dialect = dialect or contract.dialect or "sqlite"
        use_idempotent = bool(force_idempotent or getattr(contract, "ddl_style", "standard") == "idempotent")
        ordered_tables = self._topological_sort_tables(contract.tables, contract.relations)
        rel_map: Dict[Tuple[str, str], RelationModel] = {
            (r.source_table, r.source_column): r for r in contract.relations
        }
        unsafe_mssql_fks = (
            self._find_mssql_unsafe_cascade_fks(contract.tables, contract.relations)
            if target_dialect == "sqlserver"
            else set()
        )

        db_ident_raw = (contract.ddl_identifier or "").strip()
        if not db_ident_raw:
            clean_title = (contract.title or "").strip()
            if clean_title and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", clean_title):
                db_ident_raw = clean_title
            else:
                db_ident_raw = contract.db_name
        db_q = quote_identifier(db_ident_raw, target_dialect, always=False)

        collation = contract.collation
        style_tag = "IDEMPOTENTE (IF NOT EXISTS)" if use_idempotent else "ESTÁNDAR"
        header_lines = [
            "-- ============================================================================",
            f"-- ChemySQL DDL Transpilado | Proyecto: {contract.title} ({contract.db_name})",
            f"-- Dialecto Destino: {target_dialect.upper()} | Estilo: {style_tag} | Versión: v{contract.version}",
        ]
        if collation:
            header_lines.append(f"-- Cotejamiento (Collation): {collation}")
        header_lines.append("-- ============================================================================")

        preamble_stmts: List[str] = []
        if target_dialect == "sqlite":
            preamble_stmts.append("PRAGMA foreign_keys = ON;")
        elif target_dialect == "mysql":
            mysql_coll = self._resolve_collation(collation, "mysql")
            if use_idempotent:
                preamble_stmts.append(
                    f"CREATE DATABASE IF NOT EXISTS {db_q} CHARACTER SET utf8mb4 COLLATE {mysql_coll};"
                )
                preamble_stmts.append(f"USE {db_q};")
                preamble_stmts.append("SET FOREIGN_KEY_CHECKS = 1;")
            else:
                preamble_stmts.append(
                    f"CREATE DATABASE {db_q} CHARACTER SET utf8mb4 COLLATE {mysql_coll};"
                )
                preamble_stmts.append(f"USE {db_q};")
        elif target_dialect == "sqlserver":
            mssql_coll = self._resolve_collation(collation, "sqlserver")
            escaped_db_lit = db_ident_raw.replace("'", "''")
            if use_idempotent:
                preamble_stmts.append(
                    f"IF DB_ID(N'{escaped_db_lit}') IS NULL\n    CREATE DATABASE {db_q} COLLATE {mssql_coll};\nGO"
                )
            else:
                preamble_stmts.append(
                    f"CREATE DATABASE {db_q} COLLATE {mssql_coll};\nGO"
                )
            preamble_stmts.append(f"USE {db_q};\nGO")
        elif target_dialect == "postgresql":
            pg_lines = [
                f"-- Ejecutar conectado a la base de datos {db_q} (UTF-8)",
                "SET client_encoding = 'UTF8';",
            ]
            preamble_stmts.append("\n".join(pg_lines))

        statements: List[str] = []
        for tbl in ordered_tables:
            create_stmt = self._build_create_table(
                tbl,
                rel_map,
                target_dialect,
                collation,
                use_idempotent=use_idempotent,
                unsafe_mssql_fks=unsafe_mssql_fks,
            )
            statements.append(create_stmt)

            tbl_q = quote_identifier(tbl.name, target_dialect, always=False)
            for idx_col in tbl.indexes:
                if any(c.name == idx_col for c in tbl.columns):
                    raw_idx_name = f"idx_{tbl.name}_{idx_col}"
                    idx_name = quote_identifier(raw_idx_name, target_dialect, always=False)
                    col_q = quote_identifier(idx_col, target_dialect, always=False)
                    if target_dialect in ("sqlite", "postgresql") and use_idempotent:
                        statements.append(
                            f"CREATE INDEX IF NOT EXISTS {idx_name} ON {tbl_q} ({col_q});"
                        )
                    elif target_dialect == "sqlserver":
                        if use_idempotent:
                            esc_idx = raw_idx_name.replace("'", "''")
                            esc_tbl = tbl.name.replace("'", "''")
                            statements.append(
                                f"IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'{esc_idx}' AND object_id = OBJECT_ID(N'{esc_tbl}'))\n"
                                f"    CREATE INDEX {idx_name} ON {tbl_q} ({col_q});\nGO"
                            )
                        else:
                            statements.append(
                                f"CREATE INDEX {idx_name} ON {tbl_q} ({col_q});\nGO"
                            )
                    else:
                        statements.append(
                            f"CREATE INDEX {idx_name} ON {tbl_q} ({col_q});"
                        )

        for vw in getattr(contract, "views", []) or []:
            vw_stmt = self._build_create_view(vw, target_dialect, use_idempotent=use_idempotent)
            if vw_stmt:
                statements.append(vw_stmt)

        full_script = "\n\n".join(["\n".join(header_lines)] + preamble_stmts + statements)
        return {
            "dialect": target_dialect,
            "full_sql": full_script,
            "statements": statements,
            "table_order": [t.name for t in ordered_tables],
        }

    def _build_create_view(
        self,
        view: ViewModel,
        dialect: str,
        use_idempotent: bool = False,
    ) -> str:
        sel = (view.select_sql or "").strip().rstrip(";")
        if not sel:
            return ""
        v_q = quote_identifier(view.name, dialect, always=False)
        desc = (view.description or "").strip()
        comment = f"-- Vista: {view.name} — {desc}\n" if desc else ""
        if dialect == "sqlite":
            ine = "IF NOT EXISTS " if use_idempotent else ""
            return f"{comment}CREATE VIEW {ine}{v_q} AS\n{sel};"
        if dialect in ("mysql", "postgresql"):
            or_rep = "OR REPLACE " if use_idempotent else ""
            return f"{comment}CREATE {or_rep}VIEW {v_q} AS\n{sel};"
        if dialect == "sqlserver":
            or_alt = "OR ALTER " if use_idempotent else ""
            return f"{comment}CREATE {or_alt}VIEW {v_q} AS\n{sel};\nGO"
        return f"{comment}CREATE VIEW {v_q} AS\n{sel};"

    def _find_mssql_unsafe_cascade_fks(
        self,
        tables: List[TableModel],
        relations: List[RelationModel],
    ) -> Set[Tuple[str, str]]:
        """
        Detecta claves foráneas que provocarían el error T-SQL 1785 en SQL Server
        ('may cause cycles or multiple cascade paths'):
        - FKs auto-referenciales (reflexivas)
        - Tablas a las que convergen >= 2 rutas desde un mismo ancestro común.
        """
        unsafe: Set[Tuple[str, str]] = set()
        parents_of: Dict[str, List[Tuple[str, str]]] = {}
        for tbl in tables:
            for col in tbl.columns:
                if col.is_fk and col.fk_target_table:
                    if tbl.name.lower() == col.fk_target_table.lower():
                        unsafe.add((tbl.name, col.name))
                    else:
                        parents_of.setdefault(tbl.name, []).append((col.name, col.fk_target_table))

        def all_ancestors(start_tbl: str) -> Set[str]:
            seen: Set[str] = set()
            stack = [p for _, p in parents_of.get(start_tbl, [])]
            while stack:
                cur_p = stack.pop()
                if cur_p in seen:
                    continue
                seen.add(cur_p)
                for _, gp in parents_of.get(cur_p, []):
                    if gp not in seen:
                        stack.append(gp)
            return seen

        for tbl_name, fk_list in parents_of.items():
            if len(fk_list) < 2:
                continue
            reachable_per_fk: List[Tuple[str, Set[str]]] = []
            for col_name, direct_parent in fk_list:
                anc = {direct_parent} | all_ancestors(direct_parent)
                reachable_per_fk.append((col_name, anc))
            seen_ancestors: Set[str] = set()
            for col_name, anc_set in reachable_per_fk:
                if seen_ancestors & anc_set:
                    unsafe.add((tbl_name, col_name))
                seen_ancestors |= anc_set

        return unsafe

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
        use_idempotent: bool = False,
        unsafe_mssql_fks: Optional[Set[Tuple[str, str]]] = None,
    ) -> str:
        pk_cols = self._get_table_pk_columns(table)
        is_composite_pk = len(pk_cols) > 1

        col_defs: List[str] = []
        constraints: List[str] = []
        notes: List[str] = []

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
                    mssql_del = "NO ACTION" if on_del == "RESTRICT" else on_del
                    mssql_upd = "NO ACTION" if on_upd == "RESTRICT" else on_upd
                    if unsafe_mssql_fks and (table.name, col.name) in unsafe_mssql_fks:
                        if mssql_del != "NO ACTION" or mssql_upd != "NO ACTION":
                            notes.append(
                                f"-- [T-SQL] FK '{table.name}.{col.name}' ajustada a NO ACTION para evitar ciclos o múltiples rutas de cascada"
                            )
                            mssql_del = "NO ACTION"
                            mssql_upd = "NO ACTION"
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
        desc_clean = (table.description or "").strip()
        show_comment = bool(desc_clean) and not desc_clean.endswith("sincronizada desde código DDL")
        comment_lines: List[str] = []
        if show_comment:
            comment_lines.append(f"-- Tabla: {table.name} — {desc_clean}")
        comment_lines.extend(notes)
        comment = ("\n".join(comment_lines) + "\n") if comment_lines else ""
        tbl_q = quote_identifier(table.name, dialect, always=False)
        if_not_exists = "IF NOT EXISTS " if use_idempotent else ""

        if dialect == "mysql":
            mysql_coll = self._resolve_collation(collation, "mysql")
            suffix = f" ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE={mysql_coll};"
            return f"{comment}CREATE TABLE {if_not_exists}{tbl_q} (\n{body}\n){suffix}"
        if dialect == "sqlserver":
            if use_idempotent:
                esc_tbl = table.name.replace("'", "''")
                return (
                    f"{comment}IF OBJECT_ID(N'{esc_tbl}', N'U') IS NULL\n"
                    f"CREATE TABLE {tbl_q} (\n{body}\n);\nGO"
                )
            return f"{comment}CREATE TABLE {tbl_q} (\n{body}\n);\nGO"
        return f"{comment}CREATE TABLE {if_not_exists}{tbl_q} (\n{body}\n);"

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
                persisted = " PERSISTED" if col.computed_storage == "STORED" else ""
                return f"    {col_q} AS ({expr}){persisted}"
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
                    elif dialect in ("sqlite", "sqlserver", "mysql") and upper_def in ("TRUE", "FALSE"):
                        def_val = "1" if upper_def == "TRUE" else "0"
                elif dialect == "sqlserver" and upper_def == "CURRENT_DATE":
                    def_val = "CAST(GETDATE() AS DATE)"
                elif dialect in ("postgresql", "sqlite") and upper_def == "GETDATE()":
                    def_val = "CURRENT_TIMESTAMP"
                parts.append(f"DEFAULT {def_val}")
            else:
                clean_str = def_val.strip("'\"").replace("'", "''")
                if dialect == "mysql" and sql_type.upper() == "TEXT":
                    parts.append(f"DEFAULT ('{clean_str}')")
                else:
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
        if ut == "FLOAT":
            if dialect == "postgresql":
                return "DOUBLE PRECISION"
            return "FLOAT"
        if ut == "TEXT":
            if dialect == "sqlserver":
                return "NVARCHAR(MAX)"
            return "TEXT"
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
            ddl_info = self.transpile_ddl(new_contract, "sqlite", force_idempotent=True)
            return {
                "summary": f"Despliegue inicial del esquema con {len(new_contract.tables)} tablas.",
                "alter_statements": ddl_info["statements"],
                "changes": [f"Creada tabla '{t.name}' ({len(t.columns)} columnas)" for t in new_contract.tables],
                "dropped_tables": [],
                "dropped_columns": [],
                "rebuilt_tables": [],
                "is_destructive": False,
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
        dropped_tables: List[str] = []
        dropped_columns: List[Dict[str, str]] = []
        rebuilt_tables: List[str] = []

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
                new_col_names = {c.name for c in new_tbl.columns}
                for old_col_name in old_cols:
                    if old_col_name not in new_col_names:
                        dropped_columns.append({"table": t_name, "column": old_col_name})

                if self._table_needs_rebuild(old_tbl, new_tbl, old_rel_map, new_rel_map):
                    rebuilt_tables.append(t_name)
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
                dropped_tables.append(old_tbl.name)

        old_views = {v.name: v for v in (getattr(old_contract, "views", []) or [])}
        new_views = {v.name: v for v in (getattr(new_contract, "views", []) or [])}
        for old_v_name in old_views:
            if old_v_name not in new_views:
                vq = quote_identifier(old_v_name, "sqlite", always=False)
                alter_statements.append(f"DROP VIEW IF EXISTS {vq};")
                changes.append(f"Vista eliminada: '{old_v_name}'")
        for new_v_name, new_vw in new_views.items():
            vq = quote_identifier(new_v_name, "sqlite", always=False)
            clean_sel = new_vw.select_sql.strip().rstrip(";")
            if new_v_name not in old_views:
                alter_statements.append(f"CREATE VIEW IF NOT EXISTS {vq} AS {clean_sel};")
                changes.append(f"Nueva vista creada: '{new_v_name}'")
            elif old_views[new_v_name].select_sql.strip().rstrip(";") != clean_sel:
                alter_statements.append(f"DROP VIEW IF EXISTS {vq};")
                alter_statements.append(f"CREATE VIEW {vq} AS {clean_sel};")
                changes.append(f"Vista actualizada: '{new_v_name}'")

        summary = "; ".join(changes) if changes else "Actualización de metadatos y políticas de relación."
        return {
            "summary": summary,
            "alter_statements": alter_statements,
            "changes": changes,
            "dropped_tables": dropped_tables,
            "dropped_columns": dropped_columns,
            "rebuilt_tables": rebuilt_tables,
            "is_destructive": bool(dropped_tables or dropped_columns),
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
        DEFAULT y columnas calculadas), lee CREATE DATABASE / USE / COLLATE, detecta si el usuario
        prefiere estilo limpio o IF NOT EXISTS y preserva posiciones X/Y y metadatos semánticos.
        """
        import sqlite3
        from datetime import datetime
        from backend.core.nlp_parser import to_snake_case

        parsed_ddl_ident: Optional[str] = base_contract.ddl_identifier if base_contract else None
        parsed_db_name: str = base_contract.db_name if base_contract else "esquema_ddl"
        parsed_title: str = base_contract.title if base_contract else "Esquema Editado en DDL"
        parsed_collation: Optional[str] = base_contract.collation if base_contract else None
        saw_if_not_exists = False
        saw_ddl_create = False

        # Normalizar sintaxis MySQL / SQL Server / PostgreSQL a SQLite para parseo determinista
        cleaned_stmts: List[str] = []
        raw_text = re.sub(r"^\s*GO\s*$", ";", sql_text, flags=re.IGNORECASE | re.MULTILINE)
        for chunk in split_sql_statements(raw_text):
            # Quitar líneas de comentario iniciales del bloque antes de clasificarlo
            body_lines = []
            for ln in chunk.splitlines():
                if ln.strip().startswith("--"):
                    continue
                body_lines.append(ln)
            no_comments = "\n".join(body_lines).strip()
            if not no_comments:
                continue
            upper = no_comments.upper()

            # Capturar CREATE DATABASE [IF NOT EXISTS] <nombre> [... COLLATE <coll>]
            m_cdb = re.match(
                r"^(?:IF\s+DB_ID\s*\([^)]+\)\s+IS\s+NULL\s+)?CREATE\s+DATABASE\s+(IF\s+NOT\s+EXISTS\s+)?[`\"'\[]?([A-Za-z0-9_]+)[`\"'\]]?(.*)$",
                no_comments,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if m_cdb:
                saw_ddl_create = True
                if m_cdb.group(1) or upper.startswith("IF DB_ID"):
                    saw_if_not_exists = True
                raw_ident = m_cdb.group(2).strip()
                if raw_ident:
                    parsed_ddl_ident = raw_ident
                    parsed_db_name = to_snake_case(raw_ident) or parsed_db_name
                    parsed_title = raw_ident.replace("_", " ") if "_" in raw_ident else raw_ident
                m_coll = re.search(r"\bCOLLATE\s*=?\s*([A-Za-z0-9_]+)", m_cdb.group(3) or "", flags=re.IGNORECASE)
                if m_coll:
                    parsed_collation = m_coll.group(1)
                continue

            m_use = re.match(r"^USE\s+[`\"'\[]?([A-Za-z0-9_]+)[`\"'\]]?$", no_comments, flags=re.IGNORECASE)
            if m_use:
                raw_ident = m_use.group(1).strip()
                if raw_ident and not parsed_ddl_ident:
                    parsed_ddl_ident = raw_ident
                    parsed_db_name = to_snake_case(raw_ident) or parsed_db_name
                    parsed_title = raw_ident.replace("_", " ") if "_" in raw_ident else raw_ident
                continue

            if upper.startswith(("IF DB_ID", "SET FOREIGN_KEY_CHECKS", "SET CLIENT_ENCODING", "PRAGMA")):
                continue

            # Extraer COLLATE a nivel de tabla si no se había detectado aún
            if not parsed_collation:
                m_tbl_coll = re.search(r"\)\s*[^;]*?\bCOLLATE\s*=\s*([A-Za-z0-9_]+)", no_comments, flags=re.IGNORECASE)
                if m_tbl_coll:
                    parsed_collation = m_tbl_coll.group(1)

            # Detectar IF OBJECT_ID(...) IS NULL CREATE TABLE ... de SQL Server
            stmt = no_comments
            if re.match(r"^IF\s+OBJECT_ID\s*\([^)]+\)\s+IS\s+NULL\s+CREATE\s+TABLE\b", stmt, flags=re.IGNORECASE):
                saw_ddl_create = True
                saw_if_not_exists = True
                stmt = re.sub(r"^IF\s+OBJECT_ID\s*\([^)]+\)\s+IS\s+NULL\s+", "", stmt, flags=re.IGNORECASE)
            elif re.match(r"^IF\s+NOT\s+EXISTS\s*\(\s*SELECT\b.+?\)\s*CREATE\s+INDEX\b", stmt, flags=re.IGNORECASE | re.DOTALL):
                saw_if_not_exists = True
                stmt = re.sub(r"^IF\s+NOT\s+EXISTS\s*\(\s*SELECT\b.+?\)\s*", "", stmt, flags=re.IGNORECASE | re.DOTALL)
            elif upper.startswith("CREATE TABLE"):
                saw_ddl_create = True
                if re.match(r"^CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\b", stmt, flags=re.IGNORECASE):
                    saw_if_not_exists = True
            elif re.match(r"^CREATE\s+(?:OR\s+(?:REPLACE|ALTER)\s+)?VIEW\b", stmt, flags=re.IGNORECASE):
                saw_ddl_create = True
                if re.match(r"^CREATE\s+OR\s+(?:REPLACE|ALTER)\s+VIEW\b|^CREATE\s+VIEW\s+IF\s+NOT\s+EXISTS\b", stmt, flags=re.IGNORECASE):
                    saw_if_not_exists = True
                stmt = re.sub(
                    r"^CREATE\s+OR\s+(?:REPLACE|ALTER)\s+VIEW\b",
                    "CREATE VIEW IF NOT EXISTS",
                    stmt,
                    flags=re.IGNORECASE,
                )

            # Adaptar sintaxis de otros dialectos
            stmt = re.sub(
                r"\)\s*(?:ENGINE\s*=\s*\w+|DEFAULT\s+CHARSET\s*=\s*\w+|CHARACTER\s+SET\s+\w+|COLLATE\s*=?\s*\w+|AUTO_INCREMENT\s*=\s*\d+|\s)+$",
                ")",
                stmt,
                flags=re.IGNORECASE,
            )
            stmt = re.sub(r"\bNVARCHAR\s*\(\s*MAX\s*\)", "TEXT", stmt, flags=re.IGNORECASE)
            stmt = re.sub(r"\bDOUBLE\s+PRECISION\b", "FLOAT", stmt, flags=re.IGNORECASE)
            stmt = re.sub(r"\bDATETIME2\b", "DATETIME", stmt, flags=re.IGNORECASE)
            stmt = re.sub(r"\bDEFAULT\s*\(\s*'([^']*)'\s*\)", r"DEFAULT '\1'", stmt, flags=re.IGNORECASE)
            stmt = re.sub(r"\bINT\s+IDENTITY\s*\(\s*\d+\s*,\s*\d+\s*\)\s+PRIMARY\s+KEY\b", "INTEGER PRIMARY KEY AUTOINCREMENT", stmt, flags=re.IGNORECASE)
            stmt = re.sub(r"\b(?:INT|INTEGER)\s+AUTO_INCREMENT\s+PRIMARY\s+KEY\b", "INTEGER PRIMARY KEY AUTOINCREMENT", stmt, flags=re.IGNORECASE)
            stmt = re.sub(r"\bSERIAL\s+PRIMARY\s+KEY\b", "INTEGER PRIMARY KEY AUTOINCREMENT", stmt, flags=re.IGNORECASE)
            # SQL Server computed column: col AS (expr) [PERSISTED] -> col DECIMAL(10,2) GENERATED ALWAYS AS (expr) VIRTUAL/STORED
            if "GENERATED ALWAYS AS" not in stmt.upper():
                stmt = re.sub(
                    r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\(([^)]+)\)\s+PERSISTED\b",
                    r"\1 DECIMAL(10,2) GENERATED ALWAYS AS (\2) STORED",
                    stmt,
                    flags=re.IGNORECASE,
                )
                stmt = re.sub(
                    r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\(([^)]+)\)",
                    r"\1 DECIMAL(10,2) GENERATED ALWAYS AS (\2) VIRTUAL",
                    stmt,
                    flags=re.IGNORECASE,
                )
            cleaned_stmts.append(stmt)

        old_tables_by_low: Dict[str, TableModel] = {}
        old_views_by_low: Dict[str, ViewModel] = {}
        old_rels_by_pair: Dict[Tuple[str, str], RelationModel] = {}
        if base_contract:
            for t in base_contract.tables:
                old_tables_by_low[t.name.lower()] = t
            for v in getattr(base_contract, "views", []) or []:
                old_views_by_low[v.name.lower()] = v
            for r in base_contract.relations:
                old_rels_by_pair[(r.source_table.lower(), r.source_column.lower())] = r

        if saw_ddl_create:
            parsed_style: Literal["standard", "idempotent"] = "idempotent" if saw_if_not_exists else "standard"
        else:
            parsed_style = base_contract.ddl_style if base_contract else "standard"

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
                old_tbl = old_tables_by_low.get(t_name.lower())
                old_cols_by_low: Dict[str, ColumnModel] = (
                    {c.name.lower(): c for c in old_tbl.columns} if old_tbl else {}
                )

                t_q = quote_identifier(t_name, "sqlite")
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

                cur.execute(f"PRAGMA foreign_key_list({t_q})")
                fk_by_col: Dict[str, Dict[str, str]] = {}
                for fk in cur.fetchall():
                    src_col_name = fk[3]
                    tgt_tbl_name = fk[2]
                    tgt_col_name = fk[4] or "id"
                    fk_by_col[src_col_name] = {
                        "target_table": tgt_tbl_name,
                        "target_column": tgt_col_name,
                        "on_update": fk[5] or "CASCADE",
                        "on_delete": fk[6] or "RESTRICT",
                    }
                    prev_rel = old_rels_by_pair.get((t_name.lower(), src_col_name.lower()))
                    inferred_card: Literal["1:1", "1:N", "N:M"] = "1:N"
                    if prev_rel and prev_rel.target_table.lower() == tgt_tbl_name.lower():
                        inferred_card = prev_rel.cardinality
                    elif src_col_name in unique_cols:
                        inferred_card = "1:1"
                    elif old_tbl and old_tbl.is_associative:
                        inferred_card = "N:M"

                    relations.append(
                        RelationModel(
                            id=prev_rel.id if prev_rel else f"rel_{t_name}_{src_col_name}_{tgt_tbl_name}",
                            source_table=t_name,
                            source_column=src_col_name,
                            target_table=tgt_tbl_name,
                            target_column=tgt_col_name,
                            cardinality=inferred_card,
                            on_delete=fk[6] if fk[6] in ("RESTRICT", "CASCADE", "SET NULL", "NO ACTION") else "RESTRICT",  # type: ignore[arg-type]
                            on_update=fk[5] if fk[5] in ("RESTRICT", "CASCADE", "SET NULL", "NO ACTION") else "CASCADE",  # type: ignore[arg-type]
                            via_table=prev_rel.via_table if prev_rel else (t_name if (old_tbl and old_tbl.is_associative) else None),
                            tutor_explanation=(
                                prev_rel.tutor_explanation
                                if (prev_rel and prev_rel.tutor_explanation)
                                else f"Relación referencial entre {t_name}.{src_col_name} y {tgt_tbl_name}.{tgt_col_name}."
                            ),
                        )
                    )

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
                    elif raw_type.strip().upper() == "BIT":
                        c_type = "BOOLEAN"

                    fk_info = fk_by_col.get(c_name)
                    col_key = (t_name.lower(), c_name.lower())
                    comp_expr = computed_by_col.get(col_key) if c_hidden in (2, 3) else None
                    old_col = old_cols_by_low.get(c_name.lower())

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
                            description=(
                                old_col.description
                                if (old_col and old_col.description and "editada desde código DDL" not in old_col.description)
                                else f"Atributo '{c_name}' de {t_name}"
                            ),
                            tutor_explanation=(
                                old_col.tutor_explanation
                                if (old_col and old_col.tutor_explanation)
                                else f"Columna '{c_name}' ({raw_type}) sincronizada desde el código DDL."
                            ),
                        )
                    )

                pk_pairs.sort(key=lambda x: x[0])
                pk_list = [name for _, name in pk_pairs]
                pos_x, pos_y = (
                    (old_tbl.position_x, old_tbl.position_y)
                    if old_tbl
                    else (20.0 + (idx % 3) * 324.0, 20.0 + (idx // 3) * 288.0)
                )
                preserved_desc = (
                    old_tbl.description
                    if (old_tbl and old_tbl.description and not old_tbl.description.endswith("sincronizada desde código DDL"))
                    else ""
                )

                tables.append(
                    TableModel(
                        name=t_name,
                        description=preserved_desc,
                        is_associative=old_tbl.is_associative if old_tbl else False,
                        is_historical=old_tbl.is_historical if old_tbl else False,
                        position_x=pos_x,
                        position_y=pos_y,
                        primary_key=pk_list,
                        columns=cols,
                        indexes=explicit_indexes,
                        functional_dependencies=list(old_tbl.functional_dependencies) if old_tbl else [],
                        tutor_explanation=(
                            old_tbl.tutor_explanation
                            if (old_tbl and old_tbl.tutor_explanation)
                            else f"Tabla '{t_name}' definida en el esquema relacional."
                        ),
                    )
                )

            cur.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='view' AND name NOT LIKE 'sqlite_%'"
            )
            view_rows = cur.fetchall()
            views: List[ViewModel] = []
            for v_idx, (v_name, v_sql) in enumerate(view_rows):
                old_vw = old_views_by_low.get(v_name.lower())
                m_as = re.search(r"\bAS\b\s+(.+)$", v_sql or "", flags=re.IGNORECASE | re.DOTALL)
                sel_sql = m_as.group(1).strip().rstrip(";") if m_as else (v_sql or "")
                v_cols: List[str] = []
                try:
                    cur.execute(f"PRAGMA table_info({quote_identifier(v_name, 'sqlite')})")
                    v_cols = [r[1] for r in cur.fetchall() if r[1]]
                except sqlite3.Error:
                    pass
                vx, vy = (
                    (old_vw.position_x, old_vw.position_y)
                    if old_vw
                    else (60.0 + (v_idx % 3) * 320.0, 420.0 + (v_idx // 3) * 200.0)
                )
                views.append(
                    ViewModel(
                        name=v_name,
                        select_sql=sel_sql,
                        columns=v_cols,
                        description=old_vw.description if old_vw else "",
                        position_x=vx,
                        position_y=vy,
                    )
                )
        finally:
            conn.close()

        return MasterSchemaContract(
            db_name=parsed_db_name,
            ddl_identifier=parsed_ddl_ident,
            ddl_style=parsed_style,
            title=parsed_title,
            description=base_contract.description if base_contract else "",
            source_prompt=base_contract.source_prompt if base_contract else "",
            dialect=base_contract.dialect if base_contract else "sqlite",
            collation=parsed_collation,
            is_deployed=False,
            version=base_contract.version if base_contract else 1,
            updated_at=datetime.now().isoformat(timespec="seconds"),
            tables=tables,
            views=views,
            relations=relations,
            audit_alerts=[],
            tutor_metadata=base_contract.tutor_metadata if base_contract else {},
            diagram_layout=base_contract.diagram_layout if base_contract else {},
        )
