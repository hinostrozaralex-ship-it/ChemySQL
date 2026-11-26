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
from backend.core.db_engine import DatabaseEngine, SQLExecutionDetailError
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

        # Sin confirmar migración destructiva, el Escudo Pre-Migración bloquea preventivamente
        warn_res = self.engine.deploy_schema(c2, populate_mock_data=False, confirmed_destructive=False)
        self.assertTrue(warn_res.get("requires_migration_confirmation"))
        self.assertEqual(warn_res["migration_warning"]["affected_rows"], 2)

        # Al confirmar, crea backup automático .db.bak y reconstruye preservando datos
        res = self.engine.deploy_schema(c2, populate_mock_data=False, confirmed_destructive=True)
        self.assertEqual(res["version"], 2)
        self.assertTrue(res.get("backup_path") and Path(res["backup_path"]).exists())
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

    def test_portable_chemysql_bundle_and_layout_persistence(self) -> None:
        ddl = """
        CREATE DATABASE Academia;
        CREATE TABLE alumno (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre VARCHAR(80) NOT NULL
        );
        """
        c = self.tr.parse_ddl_to_contract(ddl)
        self.engine.deploy_schema(c, populate_mock_data=False)
        self.engine.insert_row("academia", "alumno", {"nombre": "Lucía"})

        # Guardar maquetación visual personalizada (ER + Chen + Verbos)
        loaded = self.engine.load_or_introspect_schema("academia")
        loaded.tables[0].position_x = 412.0
        loaded.tables[0].position_y = 288.0
        loaded.diagram_layout = {
            "positions": {"chen": {"ent:alumno": {"x": 500, "y": 300}}, "tables": {}},
            "customVerbs": {"rel_demo": "Matricula"},
        }
        save_res = self.engine.save_schema_layout(loaded)
        self.assertTrue(save_res["saved"])
        self.assertTrue(save_res["is_deployed"])

        # Exportar a paquete portable .chemysql con datos SQLite embebidos
        reloaded = self.engine.load_or_introspect_schema("academia")
        bundle = self.engine.export_project_bundle(reloaded, include_data=True)
        self.assertEqual(bundle["filename"], "academia.chemysql")
        self.assertTrue(bundle["has_embedded_db"])

        # Importar el paquete .chemysql en otro ordenador / carpeta vacía
        with tempfile.TemporaryDirectory() as other_pc_dir:
            other_engine = DatabaseEngine(Path(other_pc_dir))
            imp = other_engine.import_project_bundle(bundle["content"])
            self.assertTrue(imp["imported"])
            self.assertTrue(imp["restored_sqlite_db"])
            self.assertEqual(imp["db_name"], "academia")
            restored_contract = imp["schema_contract"]
            self.assertEqual(restored_contract["ddl_identifier"], "Academia")
            self.assertEqual(restored_contract["tables"][0]["position_x"], 412.0)
            self.assertEqual(
                restored_contract["diagram_layout"]["customVerbs"]["rel_demo"],
                "Matricula",
            )
            self.assertGreaterEqual(len(imp["history"]), 1)
            rows = other_engine.get_table_rows("academia", "alumno")["rows"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["nombre"], "Lucía")


class TestAPISecurity(unittest.TestCase):
    def test_health_version_and_sql_write_protection(self) -> None:
        health = routes.health_check()
        self.assertEqual(health["version"], APP_VERSION)
        self.assertIn(health["default_language"], ("es", "en"))
        with self.assertRaises(HTTPException) as ctx:
            routes.save_sql_script_file(
                SaveSQLRequest(content="echo pwn", path=r"C:\Windows\Temp\evil.bat", save_as=False)
            )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_atomic_ddl_rollback_and_error_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            eng = DatabaseEngine(Path(tmp))
            broken_script = (
                "CREATE TABLE INSTALACION (\n"
                "    cod_instalacion CHAR(3) NOT NULL PRIMARY KEY,\n"
                "    nombre VARCHAR(40) NOT NULL\n"
                ");\n\n"
                "CREATE TABLE PISTA (\n"
                "    cod_pista SMALLINT NOT NULL PRIMARY KEY,\n"
                "    precio_hora DECIMAL(5,2) NOT NULL BROKEN_SYNTAX\n"
                ");"
            )
            with self.assertRaises(SQLExecutionDetailError) as ctx:
                eng.execute_query("rollback_test", broken_script)
            self.assertTrue(ctx.exception.rolled_back)
            self.assertEqual(ctx.exception.line, 6)

            # Tras corregir el error y re-ejecutar el script completo, NO debe dar 'table already exists'
            fixed_script = broken_script.replace("BROKEN_SYNTAX", "")
            res = eng.execute_query("rollback_test", fixed_script)
            self.assertTrue(res["schema_updated"])
            tbl_names = [t["name"] for t in res["schema_contract"]["tables"]]
            self.assertEqual(tbl_names, ["INSTALACION", "PISTA"])

    def test_english_structured_spec_and_free_text(self) -> None:
        nlp = SpanishNLPParser()
        en_spec = """
        Create a database called gym_hub.
        Table MEMBER:
        member_id: type CHAR(4), required (NOT NULL), primary key.
        full_name: type VARCHAR(50), required (NOT NULL).
        Table SESSION:
        session_id: type INT, required (NOT NULL), primary key.
        member_id: type CHAR(4), required (NOT NULL), foreign key referencing member_id of table MEMBER.
        """
        c = nlp.parse_text_to_schema(en_spec, db_name="old_name")
        self.assertEqual(c.db_name, "gym_hub")
        self.assertEqual([t.name for t in c.tables], ["MEMBER", "SESSION"])
        fk_col = next(col for col in c.tables[1].columns if col.name == "member_id")
        self.assertTrue(fk_col.is_fk)
        self.assertEqual(fk_col.data_type, "CHAR")
        self.assertEqual(fk_col.length, 4)

        en_free = nlp.parse_text_to_schema("Customers place orders containing multiple products with price and stock.")
        ent_names = [t.name for t in en_free.tables]
        self.assertIn("clientes", ent_names)
        self.assertIn("pedidos", ent_names)
        self.assertIn("productos", ent_names)

    def test_advanced_auditor_score_security_antipatterns_and_fix_all(self) -> None:
        aud = ProactiveAuditor()
        nlp = SpanishNLPParser()
        contract = nlp.parse_text_to_schema(
            """
            Tabla user:
            id: tipo INT, NOT NULL, PRIMARY KEY.
            email: tipo VARCHAR(80), NOT NULL.
            password: tipo VARCHAR(20), NOT NULL.
            salario: tipo DECIMAL(8,2), NOT NULL.
            """,
            db_name="audit_pro_test",
        )
        alerts = aud.audit_schema(contract)
        cats = {a.category for a in alerts}
        self.assertIn("seguridad", cats)
        self.assertIn("integridad_dominio", cats)
        self.assertIn("portabilidad", cats)
        summary = contract.tutor_metadata.get("audit_summary", {})
        self.assertLess(summary.get("score", 100), 100)
        self.assertGreater(summary.get("safe_fixable", 0), 0)

        fixed_contract, count, _ = aud.apply_all_safe_fixes(contract)
        self.assertGreaterEqual(count, 3)
        new_score = fixed_contract.tutor_metadata["audit_summary"]["score"]
        self.assertGreater(new_score, summary["score"])

        # Anti-patrones SQL
        recs = aud.analyze_query_plan(
            "SELECT * FROM clientes JOIN pedidos WHERE LOWER(email) LIKE '%gmail.com'",
            [],
        )
        msgs = " ".join(r["message"] for r in recs)
        self.assertIn("producto cartesiano", msgs)
        self.assertIn("LIKE '%texto%'", msgs)
        self.assertIn("SARGable", msgs)

    def test_ddl_create_database_clean_style_mssql_cascade_and_full_export(self) -> None:
        tr = SQLTranspiler()
        clean_mysql_script = """
        CREATE DATABASE Polideportivo CHARACTER SET utf8mb4 COLLATE utf8mb4_spanish_ci;
        USE Polideportivo;

        CREATE TABLE INSTALACION (
            cod_instalacion CHAR(3) NOT NULL PRIMARY KEY,
            nombre VARCHAR(40) NOT NULL UNIQUE
        );

        CREATE TABLE PISTA (
            cod_pista SMALLINT NOT NULL PRIMARY KEY,
            largo DECIMAL(4,1) NOT NULL,
            ancho DECIMAL(4,1) NOT NULL,
            superficie DECIMAL(7,2) GENERATED ALWAYS AS (largo * ancho) VIRTUAL,
            cod_instalacion CHAR(3) NOT NULL,
            CONSTRAINT FK_PISTA_INST FOREIGN KEY (cod_instalacion) REFERENCES INSTALACION(cod_instalacion) ON DELETE CASCADE ON UPDATE CASCADE
        );

        CREATE TABLE MANTENIMIENTO (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cod_instalacion CHAR(3) NOT NULL,
            cod_pista SMALLINT NOT NULL,
            activo BOOLEAN NOT NULL DEFAULT 1,
            CONSTRAINT FK_MANT_INST FOREIGN KEY (cod_instalacion) REFERENCES INSTALACION(cod_instalacion) ON DELETE CASCADE ON UPDATE CASCADE,
            CONSTRAINT FK_MANT_PISTA FOREIGN KEY (cod_pista) REFERENCES PISTA(cod_pista) ON DELETE CASCADE ON UPDATE CASCADE
        );
        """
        contract = tr.parse_ddl_to_contract(clean_mysql_script)
        self.assertEqual(contract.db_name, "polideportivo")
        self.assertEqual(contract.ddl_identifier, "Polideportivo")
        self.assertEqual(contract.title, "Polideportivo")
        self.assertEqual(contract.ddl_style, "standard")
        self.assertEqual(contract.collation, "utf8mb4_spanish_ci")

        # En modo standard NO debe inyectar IF NOT EXISTS y debe respetar 'Polideportivo'
        mysql_out = tr.transpile_ddl(contract, "mysql")["full_sql"]
        self.assertIn("CREATE DATABASE Polideportivo CHARACTER SET utf8mb4 COLLATE utf8mb4_spanish_ci;", mysql_out)
        self.assertIn("USE Polideportivo;", mysql_out)
        self.assertNotIn("IF NOT EXISTS", mysql_out)

        # En modo idempotent SÍ debe incluir IF NOT EXISTS
        contract.ddl_style = "idempotent"
        mysql_idem = tr.transpile_ddl(contract, "mysql")["full_sql"]
        self.assertIn("CREATE DATABASE IF NOT EXISTS Polideportivo", mysql_idem)
        self.assertIn("CREATE TABLE IF NOT EXISTS INSTALACION", mysql_idem)
        contract.ddl_style = "standard"

        # En SQL Server debe degradar la segunda ruta convergente de cascada en MANTENIMIENTO a NO ACTION
        mssql_out = tr.transpile_ddl(contract, "sqlserver")["full_sql"]
        self.assertIn("CREATE DATABASE Polideportivo", mssql_out)
        self.assertIn("múltiples rutas de cascada", mssql_out)

        # Despliegue y exportación completa (DDL + INSERT en orden topológico sin columna calculada 'superficie')
        with tempfile.TemporaryDirectory() as tmp:
            eng = DatabaseEngine(Path(tmp))
            eng.deploy_schema(contract, populate_mock_data=False)
            eng.insert_row("polideportivo", "INSTALACION", {"cod_instalacion": "I01", "nombre": "Pabellón Norte"})
            eng.insert_row(
                "polideportivo",
                "PISTA",
                {"cod_pista": 1, "largo": 20.0, "ancho": 10.0, "cod_instalacion": "I01"},
            )
            eng.insert_row(
                "polideportivo",
                "MANTENIMIENTO",
                {"cod_instalacion": "I01", "cod_pista": 1, "activo": 1},
            )

            pg_full = eng.export_full_database_sql(contract, dialect="postgresql", include_data=True)
            self.assertEqual(pg_full["row_count"], 3)
            sql_txt = pg_full["content"]
            # Orden topológico en INSERT: INSTALACION antes que PISTA, y PISTA antes que MANTENIMIENTO
            pos_inst = sql_txt.index("INSERT INTO INSTALACION")
            pos_pista = sql_txt.index("INSERT INTO PISTA")
            pos_mant = sql_txt.index("INSERT INTO MANTENIMIENTO")
            self.assertLess(pos_inst, pos_pista)
            self.assertLess(pos_pista, pos_mant)
            # No se debe incluir la columna calculada 'superficie' en el INSERT de PISTA
            pista_insert_line = next(
                ln for ln in sql_txt.splitlines() if ln.startswith("INSERT INTO PISTA")
            )
            self.assertNotIn("superficie", pista_insert_line)
            # Booleano formateado como TRUE en PostgreSQL
            self.assertIn("TRUE", sql_txt)

            # En SQL Server incluye SET IDENTITY_INSERT para tablas con PK IDENTITY
            ms_full = eng.export_full_database_sql(contract, dialect="sqlserver", include_data=True)
            self.assertIn("SET IDENTITY_INSERT MANTENIMIENTO ON;", ms_full["content"])
            self.assertIn("SET IDENTITY_INSERT MANTENIMIENTO OFF;", ms_full["content"])

    def test_views_null_traps_and_relational_algebra(self) -> None:
        tr = SQLTranspiler()
        aud = ProactiveAuditor()
        tutor = TutorEngine()

        ddl_with_view = """
        CREATE DATABASE Biblioteca;
        CREATE TABLE socios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre VARCHAR(100) NOT NULL,
            telefono VARCHAR(20)
        );
        CREATE VIEW vista_socios_con_tel AS
        SELECT id, nombre, telefono FROM socios WHERE telefono IS NOT NULL;
        """
        contract = tr.parse_ddl_to_contract(ddl_with_view)
        self.assertEqual(len(contract.views), 1)
        self.assertEqual(contract.views[0].name, "vista_socios_con_tel")
        self.assertIn("nombre", contract.views[0].columns)

        # Transpilación multi-dialecto de vistas
        contract.ddl_style = "idempotent"
        self.assertIn("CREATE OR REPLACE VIEW", tr.transpile_ddl(contract, "postgresql")["full_sql"])
        self.assertIn("CREATE OR ALTER VIEW", tr.transpile_ddl(contract, "sqlserver")["full_sql"])

        # Despliegue y lectura de solo lectura desde Explorador
        with tempfile.TemporaryDirectory() as tmp:
            eng = DatabaseEngine(Path(tmp))
            eng.deploy_schema(contract, populate_mock_data=False)
            eng.insert_row("biblioteca", "socios", {"nombre": "Carlos", "telefono": "600111222"})
            eng.insert_row("biblioteca", "socios", {"nombre": "Elena", "telefono": None})

            v_rows = eng.get_table_rows("biblioteca", "vista_socios_con_tel")
            self.assertTrue(v_rows["is_view"])
            self.assertEqual(v_rows["total_rows"], 1)
            self.assertEqual(v_rows["rows"][0]["nombre"], "Carlos")

            # Intentar modificar una vista directamente debe rechazarse con mensaje claro
            with self.assertRaises(ValueError) as ctx:
                eng.insert_row("biblioteca", "vista_socios_con_tel", {"nombre": "X"})
            self.assertIn("solo lectura", str(ctx.exception))

        # Trampas de NULL detectadas por el Auditor SQL
        null_recs = aud.analyze_query_plan(
            "SELECT * FROM socios WHERE telefono = NULL AND id NOT IN (SELECT socio_id FROM prestamos)",
            [],
        )
        joined_msgs = " ".join(r["message"] for r in null_recs)
        self.assertIn("IS NULL", joined_msgs)
        self.assertIn("NOT IN", joined_msgs)

        # Equivalencia en Álgebra Relacional
        decomp = tutor.decompose_sql_query(
            "SELECT s.nombre, p.fecha FROM socios s INNER JOIN prestamos p ON s.id = p.socio_id WHERE s.activo = 1 ORDER BY p.fecha DESC;"
        )
        alg = decomp.get("relational_algebra")
        self.assertIsNotNone(alg)
        self.assertIn("π_", alg["expression"])
        self.assertIn("σ_", alg["expression"])
        self.assertIn("⋈_", alg["expression"])
        self.assertIn("τ_", alg["expression"])

    def test_formal_normalization_2fn_3fn_bcnf_4fn_and_denorm(self) -> None:
        tr = SQLTranspiler()
        aud = ProactiveAuditor()

        ddl = """
        CREATE TABLE reserva_pista (
            cod_pista CHAR(4) NOT NULL,
            fecha DATE NOT NULL,
            nombre_pista VARCHAR(40) NOT NULL,
            cod_postal CHAR(5) NOT NULL,
            ciudad VARCHAR(50) NOT NULL,
            PRIMARY KEY (cod_pista, fecha)
        );

        CREATE TABLE docencia_bcnf (
            alumno VARCHAR(30) NOT NULL,
            asignatura VARCHAR(30) NOT NULL,
            profesor VARCHAR(30) NOT NULL,
            PRIMARY KEY (alumno, asignatura)
        );

        CREATE TABLE empleado_habilidades (
            empleado_id INT NOT NULL,
            idioma VARCHAR(30) NOT NULL,
            titulacion VARCHAR(50) NOT NULL,
            PRIMARY KEY (empleado_id, idioma, titulacion)
        );

        CREATE TABLE facturas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            subtotal DECIMAL(10,2) NOT NULL CHECK (subtotal >= 0),
            total DECIMAL(10,2) NOT NULL CHECK (total >= 0),
            FOREIGN KEY (cliente_id) REFERENCES docencia_bcnf(alumno)
        );
        """
        contract = tr.parse_ddl_to_contract(ddl)
        t_res = next(t for t in contract.tables if t.name == "reserva_pista")
        t_bcnf = next(t for t in contract.tables if t.name == "docencia_bcnf")
        t_4fn = next(t for t in contract.tables if t.name == "empleado_habilidades")
        t_fac = next(t for t in contract.tables if t.name == "facturas")
        t_fac.is_historical = True

        # 2FN parcial (cod_pista -> nombre_pista) y 3FN transitiva (cod_postal -> ciudad)
        t_res.functional_dependencies = [
            "cod_pista -> nombre_pista",
            "cod_postal -> ciudad",
        ]
        # BCNF clásica: profesor -> asignatura (asignatura es atributo primo de la PK (alumno, asignatura))
        t_bcnf.functional_dependencies = [
            "profesor -> asignatura",
        ]
        # 4FN explícita: dependencia multivaluada empleado_id ->> idioma
        t_4fn.functional_dependencies = [
            "empleado_id ->> idioma",
        ]

        alerts = aud.audit_schema(contract)
        cats = {a.category for a in alerts}
        self.assertIn("normalizacion_2fn", cats)
        self.assertIn("normalizacion_3fn", cats)
        self.assertIn("normalizacion_bcnf", cats)
        self.assertIn("normalizacion_4fn", cats)
        self.assertIn("desnormalizacion", cats)

        norm_meta = contract.tutor_metadata["normalization_by_table"]
        self.assertEqual(norm_meta["reserva_pista"]["highest_nf"], "1FN")
        self.assertEqual(norm_meta["docencia_bcnf"]["highest_nf"], "3FN")
        # En docencia_bcnf existen dos claves candidatas minimales: (alumno, asignatura) y (alumno, profesor)
        ck_bcnf = [set(k) for k in norm_meta["docencia_bcnf"]["candidate_keys"]]
        self.assertIn({"alumno", "asignatura"}, ck_bcnf)
        self.assertIn({"alumno", "profesor"}, ck_bcnf)
        self.assertEqual(norm_meta["empleado_habilidades"]["highest_nf"], "BCNF")


if __name__ == "__main__":
    unittest.main()
