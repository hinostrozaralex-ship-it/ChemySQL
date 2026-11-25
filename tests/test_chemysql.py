"""
Suite de pruebas automatizadas de ChemySQL.
Cubre: NLP Parser, Auditor Proactivo, Transpilador Multi-Dialecto, Migraciones Reales,
Tutor Engine, DatabaseEngine (SQLite) y seguridad de endpoints REST.

Ejecución:
  python -m unittest discover -s tests -v
  pytest -v
"""

from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
VENV_SITE = ROOT_DIR / ".venv" / "Lib" / "site-packages"
if VENV_SITE.exists() and str(VENV_SITE) not in sys.path:
    sys.path.insert(0, str(VENV_SITE))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import HTTPException

from backend import APP_VERSION
from backend.api import routes
from backend.core.auditor import ProactiveAuditor
from backend.core.db_engine import DatabaseEngine
from backend.core.nlp_parser import SpanishNLPParser
from backend.core.schema_model import ColumnModel, MasterSchemaContract, SaveSQLRequest
from backend.core.sql_transpiler import SQLTranspiler, split_sql_statements
from backend.core.tutor_engine import TutorEngine


class TestNLPParser(unittest.TestCase):
    def setUp(self) -> None:
        self.nlp = SpanishNLPParser()

    def test_free_text_taller_infers_entities_and_nm(self) -> None:
        prompt = (
            "Necesito gestionar un taller mecánico donde los clientes traen varios vehículos, "
            "cada vehículo tiene reparaciones y en cada reparación se utilizan distintas piezas con un precio y stock."
        )
        contract = self.nlp.parse_text_to_schema(prompt)
        names = {t.name for t in contract.tables}
        self.assertTrue({"clientes", "vehiculos", "reparaciones", "piezas", "reparacion_piezas"}.issubset(names))
        self.assertTrue(any(r.cardinality == "N:M" for r in contract.relations))

    def test_structured_spec_composite_pk_and_computed(self) -> None:
        spec = """
        Crear una base de datos llamada polideportivo.
        Tabla pista:
        - cod_pista: CHAR(4), clave primaria, NOT NULL.
        - largo: DECIMAL(5,2), NOT NULL.
        - ancho: DECIMAL(5,2), NOT NULL.
        - superficie: columna calculada como el producto de largo * ancho.
        Tabla reserva:
        - cod_pista: CHAR(4), clave foranea que referencia a cod_pista de tabla pista.
        - fecha: DATE, NOT NULL.
        - num_horas: TINYINT, CHECK (num_horas BETWEEN 1 AND 3).
        La clave primaria de reserva es una clave primaria compuesta (cod_pista, fecha).
        """
        contract = self.nlp.parse_text_to_schema(spec)
        self.assertEqual(contract.db_name, "polideportivo")
        t_pista = next(t for t in contract.tables if t.name == "pista")
        t_res = next(t for t in contract.tables if t.name == "reserva")
        self.assertEqual(t_res.primary_key, ["cod_pista", "fecha"])
        sup_col = next(c for c in t_pista.columns if c.name == "superficie")
        self.assertEqual(sup_col.computed_expression, "largo * ancho")
        hrs_col = next(c for c in t_res.columns if c.name == "num_horas")
        self.assertIn("BETWEEN 1 AND 3", hrs_col.check_constraint or "")


class TestProactiveAuditor(unittest.TestCase):
    def setUp(self) -> None:
        self.nlp = SpanishNLPParser()
        self.auditor = ProactiveAuditor()

    def test_1fn_and_money_float_autofix(self) -> None:
        prompt = (
            "Necesito una clinica donde los pacientes con dni, nombre, telefono_1 y telefono_2 "
            "agendan citas con fecha_hora y coste en float."
        )
        contract = self.nlp.parse_text_to_schema(prompt)
        alerts = self.auditor.audit_schema(contract)
        ids = [a.id for a in alerts]
        self.assertTrue(any("audit_1fn_rep_pacientes" in i for i in ids))
        self.assertTrue(any("audit_type_money_citas_coste" in i for i in ids))

        fn_alert = next(a for a in alerts if "audit_1fn_rep_pacientes" in a.id)
        updated, _ = self.auditor.apply_auto_fix(contract, fn_alert.id)
        self.assertTrue(any(t.name == "paciente_telefonos" for t in updated.tables))

    def test_disaster_shield_catches_cte_and_trivial_where(self) -> None:
        self.assertTrue(self.auditor.inspect_sql_safety("DELETE FROM clientes;")["is_dangerous"])
        self.assertTrue(
            self.auditor.inspect_sql_safety("WITH x AS (SELECT 1) DELETE FROM clientes;")["is_dangerous"]
        )
        self.assertTrue(
            self.auditor.inspect_sql_safety("UPDATE clientes SET activo = 0 WHERE id = 1 OR 1 = 1;")["is_dangerous"]
        )
        self.assertFalse(
            self.auditor.inspect_sql_safety("DELETE FROM clientes WHERE id = 5;")["is_dangerous"]
        )


class TestTranspilerAndTutor(unittest.TestCase):
    def setUp(self) -> None:
        self.tr = SQLTranspiler()
        self.tutor = TutorEngine()

    def test_split_sql_statements_respects_quotes_and_comments(self) -> None:
        sql = """
        -- comentario con ; dentro
        CREATE TABLE demo (id INTEGER PRIMARY KEY, txt VARCHAR(20) DEFAULT 'a;b');
        /* bloque ; interno */
        SELECT 'x;y' AS val;
        """
        stmts = split_sql_statements(sql)
        self.assertEqual(len(stmts), 2)
        self.assertIn("'a;b'", stmts[0])
        self.assertIn("'x;y'", stmts[1])

    def test_parse_ddl_no_collision_and_sqlserver_defaults(self) -> None:
        ddl = """
        CREATE TABLE "order" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            estado VARCHAR(20) CHECK (estado IN ('ok','err')),
            activo BOOLEAN DEFAULT TRUE,
            a INTEGER,
            b INTEGER,
            total INTEGER GENERATED ALWAYS AS (a + b) VIRTUAL
        );
        CREATE TABLE pagos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            estado VARCHAR(20) CHECK (estado IN ('pagado','pendiente')),
            x INTEGER,
            y INTEGER,
            total INTEGER GENERATED ALWAYS AS (x * y) STORED
        );
        """
        contract = self.tr.parse_ddl_to_contract(ddl)
        t_ord = next(t for t in contract.tables if t.name == "order")
        t_pag = next(t for t in contract.tables if t.name == "pagos")
        self.assertEqual(next(c for c in t_ord.columns if c.name == "estado").check_constraint, "estado IN ('ok','err')")
        self.assertEqual(next(c for c in t_pag.columns if c.name == "estado").check_constraint, "estado IN ('pagado','pendiente')")
        self.assertEqual(next(c for c in t_ord.columns if c.name == "total").computed_expression, "a + b")
        self.assertEqual(next(c for c in t_pag.columns if c.name == "total").computed_expression, "x * y")

        mssql = self.tr.transpile_ddl(contract, "sqlserver")["full_sql"]
        self.assertIn("[order]", mssql)
        self.assertIn("BIT", mssql)
        self.assertIn("DEFAULT 1", mssql)

    def test_tutor_join_visualizer_all_join_types(self) -> None:
        self.assertEqual(
            self.tutor.decompose_sql_query("SELECT * FROM a RIGHT JOIN b ON a.id = b.a_id")["join_visualizer"]["type"],
            "RIGHT JOIN",
        )
        self.assertEqual(
            self.tutor.decompose_sql_query("SELECT * FROM a FULL OUTER JOIN b ON a.id = b.a_id")["join_visualizer"]["type"],
            "FULL JOIN",
        )
        self.assertEqual(
            self.tutor.decompose_sql_query("SELECT * FROM a CROSS JOIN b")["join_visualizer"]["type"],
            "CROSS JOIN",
        )


class TestDatabaseEngineAndMigrations(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.engine = DatabaseEngine(Path(self.tmp_dir.name))
        self.tr = SQLTranspiler()

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_real_sqlite_table_rebuild_migration_preserves_data(self) -> None:
        ddl_v1 = """
        CREATE TABLE clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre VARCHAR(100) NOT NULL,
            obsoleta VARCHAR(50),
            cuota FLOAT
        );
        """
        c1 = self.tr.parse_ddl_to_contract(ddl_v1)
        c1.db_name = "mig_test"
        self.engine.deploy_schema(c1, populate_mock_data=False)
        self.engine.insert_row("mig_test", "clientes", {"nombre": "Ana", "obsoleta": "viejo", "cuota": 25.5})
        self.engine.insert_row("mig_test", "clientes", {"nombre": "Luis", "obsoleta": "viejo2", "cuota": 40.0})

        # Evolución v2: eliminar columna 'obsoleta', cambiar 'cuota' a DECIMAL(10,2) y añadir 'activo'
        c2 = MasterSchemaContract.model_validate(c1.model_dump())
        tbl = c2.tables[0]
        tbl.columns = [c for c in tbl.columns if c.name != "obsoleta"]
        for c in tbl.columns:
            if c.name == "cuota":
                c.data_type = "DECIMAL(10,2)"
        tbl.columns.append(ColumnModel(name="activo", data_type="BOOLEAN", nullable=False, default_value="1"))

        res = self.engine.deploy_schema(c2, populate_mock_data=False)
        self.assertEqual(res["version"], 2)
        self.assertTrue(any("reconstruida" in ch.lower() for ch in res["migration"]["changes"]))

        rows = self.engine.get_table_rows("mig_test", "clientes")["rows"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["nombre"], "Ana")
        self.assertNotIn("obsoleta", rows[0])
        self.assertEqual(rows[0]["activo"], 1)

    def test_composite_pk_pagination_and_exports(self) -> None:
        ddl = """
        CREATE TABLE "order" (
            pista_id INTEGER NOT NULL,
            fecha DATE NOT NULL,
            nota VARCHAR(40),
            PRIMARY KEY (pista_id, fecha)
        );
        """
        c = self.tr.parse_ddl_to_contract(ddl)
        c.db_name = "exp_test"
        self.engine.deploy_schema(c, populate_mock_data=False)
        for day in range(1, 6):
            self.engine.insert_row("exp_test", "order", {"pista_id": 1, "fecha": f"2026-01-0{day}", "nota": f"N{day}"})

        # Update & delete exact composite key
        self.engine.update_cell("exp_test", "order", target_column="nota", new_value="EDITADO", pk_values={"pista_id": 1, "fecha": "2026-01-02"})
        self.engine.delete_row("exp_test", "order", pk_values={"pista_id": 1, "fecha": "2026-01-03"})

        # SQL Pagination
        p1 = self.engine.execute_query("exp_test", 'SELECT * FROM "order" ORDER BY fecha ASC;', page=1, page_size=2)
        p2 = self.engine.execute_query("exp_test", 'SELECT * FROM "order" ORDER BY fecha ASC;', page=2, page_size=2)
        self.assertEqual(p1["row_count"], 4)
        self.assertEqual(p1["total_pages"], 2)
        self.assertEqual(len(p1["rows"]), 2)
        self.assertEqual(p1["rows"][1]["nota"], "EDITADO")
        self.assertEqual(p2["rows"][0]["fecha"], "2026-01-04")

        # Exports CSV / JSON / SQL
        csv_exp = self.engine.export_table_data("exp_test", "order", "csv")
        json_exp = self.engine.export_table_data("exp_test", "order", "json")
        sql_exp = self.engine.export_table_data("exp_test", "order", "sql")
        self.assertEqual(csv_exp["row_count"], 4)
        self.assertIn("EDITADO", csv_exp["content"])
        self.assertEqual(len(json.loads(json_exp["content"])), 4)
        self.assertIn('INSERT INTO "order"', sql_exp["content"])


class TestAPISecurity(unittest.TestCase):
    def test_health_version_and_sql_write_protection(self) -> None:
        health = routes.health_check()
        self.assertEqual(health["version"], APP_VERSION)
        with self.assertRaises(HTTPException) as ctx:
            routes.save_sql_script_file(
                SaveSQLRequest(content="echo pwn", path=r"C:\Windows\Temp\evil.bat", save_as=False)
            )
        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
