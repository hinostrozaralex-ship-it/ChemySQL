"""
Motor Pedagógico del Modo Tutor de SGBD-Smart.
Proporciona:
1. Explicaciones contextuales sobre tablas, columnas, claves y relaciones del esquema activo.
2. Desglosador paso a paso del orden lógico de ejecución de consultas SELECT (FROM/JOIN -> WHERE -> GROUP BY -> HAVING -> SELECT -> ORDER BY -> LIMIT).
3. Esquemas visuales de intersección de conjuntos (INNER JOIN, LEFT JOIN, GROUP BY) aplicados a las tablas reales de la consulta.
4. Escenarios de práctica guiada con pistas escalonadas (Pista Conceptual -> Pista Estructural -> Solución Comentada).
"""

from __future__ import annotations
import re
from typing import Any, Dict, List, Optional


class TutorEngine:
    """Generador determinista de lecciones contextuales, desglose lógico SQL y retos guiados."""

    def decompose_sql_query(self, sql: str) -> Dict[str, Any]:
        """
        Analiza una sentencia SQL y genera el desglose paso a paso según el orden lógico real
        en que el motor relacional procesa la consulta, además de diagramas de conjuntos JOIN.
        """
        cleaned = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
        cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL).strip()
        single_line = re.sub(r"\s+", " ", cleaned)

        if not single_line:
            return {"is_select": False, "steps": [], "join_visualizer": None}

        upper = single_line.upper()
        if not upper.startswith("SELECT"):
            first_word = upper.split()[0]
            return {
                "is_select": False,
                "statement_type": first_word,
                "summary": f"Sentencia de modificación o definición ({first_word}). El orden lógico de 6 etapas aplica a consultas SELECT.",
                "steps": [
                    {
                        "order": 1,
                        "clause": first_word,
                        "fragment": single_line,
                        "title": f"Ejecución transaccional {first_word}",
                        "explanation": (
                            "El motor valida primero permisos, tipos de datos y restricciones de integridad (PK, UNIQUE, FK, CHECK) "
                            "antes de confirmar los cambios en el archivo de base de datos."
                        ),
                    }
                ],
                "join_visualizer": None,
            }

        # Extraer cláusulas de la consulta SELECT
        clauses = self._extract_select_clauses(single_line)
        steps: List[Dict[str, Any]] = []
        step_num = 1

        # Paso 1: FROM & JOIN
        if clauses.get("from"):
            from_frag = clauses["from"]
            join_frag = clauses.get("join", "")
            combined_from = f"FROM {from_frag}" + (f" {join_frag}" if join_frag else "")
            steps.append(
                {
                    "order": step_num,
                    "clause": "FROM & JOIN" if join_frag else "FROM",
                    "fragment": combined_from,
                    "title": "1º Origen de Datos y Cruce de Tablas",
                    "explanation": (
                        "Aunque `SELECT` se escribe primero, el motor SQL empieza SIEMPRE por `FROM` y `JOIN`: "
                        "carga las tablas involucradas y empareja sus filas usando la condición `ON` (clave foránea = clave primaria) "
                        "para construir un conjunto de trabajo virtual en memoria."
                        if join_frag
                        else "Aunque `SELECT` se escribe al principio, el motor ejecuta primero `FROM`: localiza la tabla en disco y prepara sus filas para filtrarlas."
                    ),
                }
            )
            step_num += 1

        # Paso 2: WHERE
        if clauses.get("where"):
            steps.append(
                {
                    "order": step_num,
                    "clause": "WHERE",
                    "fragment": f"WHERE {clauses['where']}",
                    "title": f"{step_num}º Filtrado Individual de Filas",
                    "explanation": (
                        "El motor evalúa la condición `WHERE` fila por fila sobre el conjunto generado en `FROM/JOIN`. "
                        "Solo las filas que cumplen esta condición pasan a la siguiente etapa; el resto se descarta inmediatamente."
                    ),
                }
            )
            step_num += 1

        # Paso 3: GROUP BY
        if clauses.get("group_by"):
            steps.append(
                {
                    "order": step_num,
                    "clause": "GROUP BY",
                    "fragment": f"GROUP BY {clauses['group_by']}",
                    "title": f"{step_num}º Agrupación en Cubos Lógicos",
                    "explanation": (
                        "Las filas que sobrevivieron al `WHERE` se agrupan en bloques que comparten el mismo valor en "
                        f"`{clauses['group_by']}`. A partir de este punto ya no trabajas con filas sueltas, sino con resúmenes por grupo."
                    ),
                }
            )
            step_num += 1

        # Paso 4: HAVING
        if clauses.get("having"):
            steps.append(
                {
                    "order": step_num,
                    "clause": "HAVING",
                    "fragment": f"HAVING {clauses['having']}",
                    "title": f"{step_num}º Filtrado de Grupos Agregados",
                    "explanation": (
                        "Mientras `WHERE` filtra filas individuales antes de agrupar, `HAVING` filtra los grupos ya formados "
                        "por `GROUP BY` (por ejemplo, quedarse solo con los clientes cuya suma o conteo supere un umbral)."
                    ),
                }
            )
            step_num += 1

        # Paso 5: SELECT
        if clauses.get("select"):
            steps.append(
                {
                    "order": step_num,
                    "clause": "SELECT",
                    "fragment": f"SELECT {clauses['select']}",
                    "title": f"{step_num}º Proyección de Columnas y Cálculos",
                    "explanation": (
                        "Recién ahora el motor evalúa la lista de columnas de `SELECT`, calcula funciones de agregación "
                        "(`COUNT`, `SUM`, `AVG`, `MAX`) o alias (`AS`), y descarta las columnas que no pediste mostrar."
                    ),
                }
            )
            step_num += 1

        # Paso 6: ORDER BY
        if clauses.get("order_by"):
            steps.append(
                {
                    "order": step_num,
                    "clause": "ORDER BY",
                    "fragment": f"ORDER BY {clauses['order_by']}",
                    "title": f"{step_num}º Ordenación del Resultado Final",
                    "explanation": (
                        "Con las columnas ya proyectadas, el motor ordena las filas resultantes de forma ascendente (`ASC`) "
                        "o descendente (`DESC`). Como ocurre casi al final, aquí sí puedes usar los alias definidos en `SELECT`."
                    ),
                }
            )
            step_num += 1

        # Paso 7: LIMIT
        if clauses.get("limit"):
            steps.append(
                {
                    "order": step_num,
                    "clause": "LIMIT",
                    "fragment": f"LIMIT {clauses['limit']}",
                    "title": f"{step_num}º Recorte y Paginación de Filas",
                    "explanation": (
                        "Finalmente, el motor entrega únicamente el número máximo de filas solicitado en `LIMIT`, "
                        "protegiendo la memoria y acelerando la respuesta en pantalla."
                    ),
                }
            )

        join_viz = self._build_join_visualizer(single_line, clauses)
        rel_algebra = self._build_relational_algebra(single_line, clauses)

        return {
            "is_select": True,
            "written_order": ["SELECT", "FROM / JOIN", "WHERE", "GROUP BY", "HAVING", "ORDER BY", "LIMIT"],
            "logical_order": [s["clause"] for s in steps],
            "steps": steps,
            "join_visualizer": join_viz,
            "relational_algebra": rel_algebra,
        }

    def _build_relational_algebra(
        self, sql: str, clauses: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Traduce determinísticamente una consulta SELECT a su expresión equivalente
        en Álgebra Relacional clásica / extendida (π, σ, ⋈, ×, γ, τ, ∪, ∩, −).
        """
        # Operaciones de conjuntos (UNION / INTERSECT / EXCEPT)
        m_set = re.split(r"\b(UNION(?:\s+ALL)?|INTERSECT|EXCEPT)\b", sql, flags=re.IGNORECASE)
        if len(m_set) >= 3:
            op_raw = m_set[1].upper()
            sym = "∪" if "UNION" in op_raw else "∩" if "INTERSECT" in op_raw else "−"
            op_name = (
                "Unión (∪)" if sym == "∪" else "Intersección (∩)" if sym == "∩" else "Diferencia (−)"
            )
            return {
                "expression": f"(Q₁) {sym} (Q₂)",
                "operators": [{"symbol": op_name, "detail": f"Combina los resultados compatibles mediante {op_raw}."}],
            }

        from_part = (clauses.get("from") or "").strip()
        if not from_part:
            return None

        operators: List[Dict[str, str]] = []
        # 1. Base relacional / Producto cartesiano / Reuniones (JOIN)
        join_part = (clauses.get("join") or "").strip()
        if "," in from_part and not join_part:
            rels = [p.strip().split()[0] for p in from_part.split(",") if p.strip()]
            expr = " × ".join(rels)
            operators.append({"symbol": "× (Producto Cartesiano)", "detail": f"Combina todas las tuplas de {', '.join(rels)}."})
        else:
            base_tbl = from_part.split()[0]
            expr = base_tbl
            if join_part:
                join_Regex = re.compile(
                    r"\b(?P<jtype>(?:INNER|CROSS|(?:LEFT|RIGHT|FULL)(?:\s+OUTER)?)\s+)?JOIN\s+(?P<rtbl>[A-Za-z0-9_`\"\[\]]+)(?:\s+(?:AS\s+)?[A-Za-z0-9_]+)?(?:\s+ON\s+(?P<cond>.*?))?(?=\s+(?:INNER|LEFT|RIGHT|FULL|CROSS|JOIN)\b|$)",
                    flags=re.IGNORECASE,
                )
                for mj in join_Regex.finditer(join_part):
                    jtype = (mj.group("jtype") or "INNER").upper()
                    rtbl = mj.group("rtbl")
                    cond = (mj.group("cond") or "").strip()
                    if "CROSS" in jtype:
                        expr = f"({expr} × {rtbl})"
                        operators.append({"symbol": "× (Producto Cartesiano)", "detail": f"Cruce total con {rtbl}."})
                    else:
                        jsym = (
                            "⟕" if "LEFT" in jtype
                            else "⟖" if "RIGHT" in jtype
                            else "⟗" if "FULL" in jtype
                            else "⋈"
                        )
                        jlabel = (
                            "⟕ (Reunión Externa Izq.)" if jsym == "⟕"
                            else "⟖ (Reunión Externa Der.)" if jsym == "⟖"
                            else "⟗ (Reunión Externa Completa)" if jsym == "⟗"
                            else "⋈ (Reunión / Theta-Join)"
                        )
                        sub = f"_{{{cond}}}" if cond else ""
                        expr = f"({expr} {jsym}{sub} {rtbl})"
                        operators.append({"symbol": jlabel, "detail": f"Empareja con {rtbl}" + (f" bajo [{cond}]" if cond else "")})

        # 2. Selección σ (WHERE)
        where_part = (clauses.get("where") or "").strip()
        if where_part:
            expr = f"σ_{{{where_part}}}({expr})"
            operators.append({"symbol": "σ (Selección)", "detail": f"Filtra tuplas donde {where_part}"})

        # 3. Agrupación γ (GROUP BY) y filtro de grupos σ (HAVING)
        group_part = (clauses.get("group_by") or "").strip()
        select_part = (clauses.get("select") or "*").strip()
        if group_part:
            expr = f"γ_{{{group_part}; {select_part}}}({expr})"
            operators.append({"symbol": "γ (Agrupación y Agregación)", "detail": f"Agrupa por [{group_part}] calculando [{select_part}]"})
            having_part = (clauses.get("having") or "").strip()
            if having_part:
                expr = f"σ_{{{having_part}}}({expr})"
                operators.append({"symbol": "σ (Filtro HAVING sobre grupos)", "detail": f"Conserva grupos con {having_part}"})
        else:
            # 4. Proyección π (SELECT) cuando no es SELECT *
            clean_sel = re.sub(r"^DISTINCT\s+", "", select_part, flags=re.IGNORECASE).strip()
            if clean_sel != "*":
                expr = f"π_{{{clean_sel}}}({expr})"
                operators.append({"symbol": "π (Proyección)", "detail": f"Proyecta los atributos [{clean_sel}]"})

        # 5. Ordenación τ (ORDER BY)
        order_part = (clauses.get("order_by") or "").strip()
        if order_part:
            expr = f"τ_{{{order_part}}}({expr})"
            operators.append({"symbol": "τ (Ordenación)", "detail": f"Ordena el resultado por [{order_part}]"})

        return {
            "expression": expr,
            "operators": operators,
        }

    def _extract_select_clauses(self, sql: str) -> Dict[str, str]:
        """Segmenta una consulta SELECT en sus cláusulas principales de forma determinista."""
        pattern = re.compile(
            r"^\s*SELECT\s+(?P<select>.+?)"
            r"(?:\s+FROM\s+(?P<from>.+?))?"
            r"(?:\s+(?P<join>(?:(?:INNER|CROSS|(?:LEFT|RIGHT|FULL)(?:\s+OUTER)?)\s+)?JOIN\s+.+?))?"
            r"(?:\s+WHERE\s+(?P<where>.+?))?"
            r"(?:\s+GROUP\s+BY\s+(?P<group_by>.+?))?"
            r"(?:\s+HAVING\s+(?P<having>.+?))?"
            r"(?:\s+ORDER\s+BY\s+(?P<order_by>.+?))?"
            r"(?:\s+LIMIT\s+(?P<limit>.+?))?\s*;?\s*$",
            flags=re.IGNORECASE,
        )
        m = pattern.match(sql)
        if m:
            return {k: (v.strip() if v else "") for k, v in m.groupdict().items()}

        # Fallback por tokens si hay subconsultas o múltiples JOINs
        res: Dict[str, str] = {}
        upper = sql.upper()
        keywords = [
            ("SELECT", "select"),
            ("FROM", "from"),
            ("WHERE", "where"),
            ("GROUP BY", "group_by"),
            ("HAVING", "having"),
            ("ORDER BY", "order_by"),
            ("LIMIT", "limit"),
        ]
        positions: List[ Any ] = []
        for kw, key in keywords:
            match = re.search(rf"\b{kw}\b", upper)
            if match:
                positions.append((match.start(), match.end(), key))
        positions.sort(key=lambda x: x[0])

        for i, (_, end_pos, key) in enumerate(positions):
            next_start = positions[i + 1][0] if i + 1 < len(positions) else len(sql)
            fragment = sql[end_pos:next_start].strip().rstrip(";")
            if key == "from":
                join_m = re.search(
                    r"\b((?:(?:INNER|CROSS|(?:LEFT|RIGHT|FULL)(?:\s+OUTER)?)\s+)?JOIN\b.+)$",
                    fragment,
                    flags=re.IGNORECASE,
                )
                if join_m:
                    res["from"] = fragment[: join_m.start()].strip()
                    res["join"] = join_m.group(1).strip()
                else:
                    res["from"] = fragment
            else:
                res[key] = fragment
        return res

    def _build_join_visualizer(self, sql: str, clauses: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Construye los metadatos para el diagrama de intersección de conjuntos (Venn) en consultas con JOIN o GROUP BY."""
        from_part = clauses.get("from", "")
        join_part = clauses.get("join", "")

        left_table = from_part.split()[0] if from_part else "Tabla_A"
        if join_part:
            m_join = re.search(
                r"\b(?P<jtype>INNER\s+JOIN|LEFT\s+(?:OUTER\s+)?JOIN|RIGHT\s+(?:OUTER\s+)?JOIN|FULL\s+(?:OUTER\s+)?JOIN|CROSS\s+JOIN|JOIN)\s+(?P<rtbl>[a-zA-Z0-9_]+)(?:.*?\bON\s+(?P<on_cond>[^;]+))?",
                join_part,
                flags=re.IGNORECASE,
            )
            if m_join:
                raw_type = m_join.group("jtype").upper()
                right_table = m_join.group("rtbl")
                on_cond = (m_join.group("on_cond") or "").strip()
                # Limpiar cláusulas posteriores si se colaron en on_cond
                on_cond = re.split(r"\b(?:INNER|LEFT|RIGHT|FULL|CROSS|JOIN|WHERE|GROUP|ORDER|LIMIT)\b", on_cond, flags=re.IGNORECASE)[0].strip()

                if "LEFT" in raw_type:
                    return {
                        "type": "LEFT JOIN",
                        "left_table": left_table,
                        "right_table": right_table,
                        "on_condition": on_cond or f"{left_table}.id = {right_table}.{left_table[:-1]}_id",
                        "active_regions": ["left_only", "intersection"],
                        "title": f"LEFT JOIN: Todo '{left_table}' + Coincidencias en '{right_table}'",
                        "explanation": (
                            f"Conserva el 100 % de las filas de la tabla izquierda (`{left_table}`), incluso si no tienen ningún registro "
                            f"relacionado en `{right_table}` (en cuyo caso las columnas de `{right_table}` se rellenan con `NULL`)."
                        ),
                    }
                if "RIGHT" in raw_type:
                    return {
                        "type": "RIGHT JOIN",
                        "left_table": left_table,
                        "right_table": right_table,
                        "on_condition": on_cond or f"{left_table}.id = {right_table}.{left_table[:-1]}_id",
                        "active_regions": ["right_only", "intersection"],
                        "title": f"RIGHT JOIN: Coincidencias en '{left_table}' + Todo '{right_table}'",
                        "explanation": (
                            f"Conserva el 100 % de las filas de la tabla derecha (`{right_table}`), aunque no tengan coincidencia "
                            f"en `{left_table}` (rellenando las columnas de `{left_table}` con `NULL`)."
                        ),
                    }
                if "FULL" in raw_type:
                    return {
                        "type": "FULL JOIN",
                        "left_table": left_table,
                        "right_table": right_table,
                        "on_condition": on_cond or f"{left_table}.id = {right_table}.{left_table[:-1]}_id",
                        "active_regions": ["left_only", "intersection", "right_only"],
                        "title": f"FULL OUTER JOIN: Unión completa de '{left_table}' y '{right_table}'",
                        "explanation": (
                            f"Devuelve todas las filas de `{left_table}` y todas las filas de `{right_table}`, "
                            "emparejando las que coinciden y rellenando con `NULL` el lado sin correspondencia."
                        ),
                    }
                if "CROSS" in raw_type:
                    return {
                        "type": "CROSS JOIN",
                        "left_table": left_table,
                        "right_table": right_table,
                        "on_condition": "Producto cartesiano (sin cláusula ON)",
                        "active_regions": ["left_only", "intersection", "right_only"],
                        "title": f"CROSS JOIN: Producto cartesiano '{left_table}' × '{right_table}'",
                        "explanation": (
                            f"Combina cada fila de `{left_table}` con todas las filas de `{right_table}` "
                            "(si tienen N y M filas, produce N × M combinaciones)."
                        ),
                    }
                return {
                    "type": "INNER JOIN",
                    "left_table": left_table,
                    "right_table": right_table,
                    "on_condition": on_cond or f"{left_table}.id = {right_table}.{left_table[:-1]}_id",
                    "active_regions": ["intersection"],
                    "title": f"INNER JOIN: Intersección estricta entre '{left_table}' y '{right_table}'",
                    "explanation": (
                        f"Devuelve únicamente las filas donde existe coincidencia exacta en ambos conjuntos según `{on_cond}`. "
                        f"Si un registro de `{left_table}` no tiene correspondencia en `{right_table}`, queda fuera del resultado."
                    ),
                }

        if clauses.get("group_by"):
            return {
                "type": "GROUP BY",
                "left_table": left_table,
                "right_table": clauses["group_by"],
                "on_condition": f"Agrupado por {clauses['group_by']}",
                "active_regions": ["grouped_buckets"],
                "title": f"GROUP BY: Condensación de '{left_table}' por '{clauses['group_by']}'",
                "explanation": (
                    f"Colapsa múltiples filas individuales de `{left_table}` que comparten el mismo valor de `{clauses['group_by']}` "
                    "en una única fila resumen para calcular totales (`COUNT`, `SUM`, `AVG`)."
                ),
            }

        return None

    def get_guided_challenges(self) -> List[Dict[str, Any]]:
        """Devuelve los escenarios de práctica guiada con pistas escalonadas."""
        return [
            {
                "id": "reto_biblioteca",
                "level": "Nivel 1 · Básico",
                "title": "Biblioteca Municipal y Control de Préstamos",
                "goal": (
                    "Modelar una biblioteca donde los socios toman prestados distintos libros escritos por autores, "
                    "registrando la fecha de préstamo, fecha de vencimiento y si ya fue devuelto."
                ),
                "suggested_prompt": (
                    "Necesito gestionar una biblioteca donde los autores escriben varios libros con isbn, titulo y stock, "
                    "y los socios con dni, nombre y email realizan prestamos con fecha_prestamo, fecha_vencimiento y devuelto."
                ),
                "hint_1_conceptual": (
                    "Piensa primero en los sustantivos que tienen existencia propia en la biblioteca: "
                    "¿Quiénes escriben las obras? ¿Qué objetos físicos se prestan? ¿Quiénes se llevan los libros a casa? "
                    "¿Y qué evento ocurre cada vez que alguien retira un ejemplar?"
                ),
                "hint_2_estructural": (
                    "Necesitas 4 entidades principales: `autores`, `libros`, `socios` y `prestamos`. "
                    "Como un libro puede ser escrito por más de un autor y un autor escribe varios libros, entre `autores` y `libros` "
                    "existe una relación N:M (`autor_libros`). En cambio, cada registro de `prestamos` pertenece a un `socio_id` y a un `libro_id` (dos relaciones 1:N)."
                ),
                "hint_3_solution": (
                    "Esquema óptimo: `autores` (id, nombre, nacionalidad), `libros` (id, isbn UNIQUE, titulo, stock), "
                    "`autor_libros` (id, autor_id FK, libro_id FK), `socios` (id, codigo UNIQUE, nombre, email UNIQUE, activo) "
                    "y `prestamos` (id, socio_id FK, libro_id FK, fecha_prestamo DATE, fecha_vencimiento DATE, devuelto BOOLEAN)."
                ),
            },
            {
                "id": "reto_clinica_1fn",
                "level": "Nivel 2 · Normalización 1FN",
                "title": "Clínica Médica y Corrección de Grupos Repetitivos (1FN)",
                "goal": (
                    "Diseñar la base de datos de una clínica donde los pacientes (que inicialmente tenían telefono_1 y telefono_2) "
                    "agendan citas médicas con distintos médicos especialistas, corrigiendo la violación de 1ª Forma Normal."
                ),
                "suggested_prompt": (
                    "Necesito una clinica donde los pacientes con dni, nombre, telefono_1 y telefono_2 agendan varias citas "
                    "con fecha_hora, diagnostico y coste atendidas por medicos con codigo, nombre y especialidad."
                ),
                "hint_1_conceptual": (
                    "Observa qué ocurre cuando guardas `telefono_1` y `telefono_2` en la misma fila del paciente: "
                    "¿qué pasa si un paciente necesita registrar tres teléfonos de emergencia o ninguno? "
                    "Eso viola la 1ª Forma Normal (atomicidad y ausencia de grupos repetitivos)."
                ),
                "hint_2_estructural": (
                    "Genera el boceto con `pacientes`, `medicos` y `citas`. Luego abre el panel del **Auditor Proactivo** "
                    "y observa la alerta amarilla de `Violación de 1FN en pacientes (telefono_1, telefono_2)`. "
                    "Puedes usar el botón de corrección automática en un clic para extraer la tabla hija `paciente_telefonos`."
                ),
                "hint_3_solution": (
                    "Al normalizar a 1FN, `pacientes` conserva solo sus datos únicos (id, dni, nombre, email) y se crea la tabla hija "
                    "`paciente_telefonos` (id, paciente_id FK, telefono, etiqueta) en relación 1:N. "
                    "Por su parte, `citas` actúa como vínculo temporal entre `paciente_id` y `medico_id` con `coste DECIMAL(10,2)`."
                ),
            },
            {
                "id": "reto_comercio_auditoria",
                "level": "Nivel 3 · Integridad Contable",
                "title": "Comercio, Inventario y Protección de Historial de Facturas",
                "goal": (
                    "Modelar un sistema de pedidos, productos y facturas asegurando precisión monetaria DECIMAL(10,2) "
                    "y protegiendo las facturas históricas frente a borrados en cascada (ON DELETE CASCADE)."
                ),
                "suggested_prompt": (
                    "Necesito una tienda donde los clientes realizan pedidos que incluyen distintos productos con precio y stock, "
                    "y cada cliente recibe facturas con fecha_emision, subtotal, total y pagado."
                ),
                "hint_1_conceptual": (
                    "En un sistema comercial hay dos peligros clásicos: usar tipos de coma flotante (`FLOAT`) para precios "
                    "(causando errores de redondeo de céntimos) y configurar `ON DELETE CASCADE` desde `clientes` hacia `facturas` "
                    "(lo cual destruiría facturas legales si alguien borra un cliente)."
                ),
                "hint_2_estructural": (
                    "Entre `pedidos` y `productos` se necesita una tabla intermedia `pedido_productos` con `cantidad` y `precio_unitario`. "
                    "Entre `clientes` y `facturas` la política de integridad referencial debe ser `ON DELETE RESTRICT`, implementando "
                    "borrado lógico en `clientes` mediante `activo` y `fecha_baja`."
                ),
                "hint_3_solution": (
                    "Verifica en el inspector que todos los campos monetarios (`precio`, `subtotal`, `total`) sean `DECIMAL(10,2)`, "
                    "que todas las claves foráneas tengan índice (`idx_facturas_cliente_id`, `idx_pedidos_cliente_id`) "
                    "y que la relación hacia `facturas` use `ON DELETE RESTRICT`."
                ),
            },
            {
                "id": "reto_taller_maestro",
                "level": "Nivel 4 · Caso Maestro",
                "title": "Taller Mecánico Integral (Del Texto al Despliegue y Consulta JOIN)",
                "goal": (
                    "Completar el flujo maestro: clientes con varios vehículos, reparaciones por vehículo y piezas con precio y stock "
                    "en relación muchos-a-muchos, desplegando la base de datos y ejecutando un cruce JOIN indexado."
                ),
                "suggested_prompt": (
                    "Necesito gestionar un taller mecánico donde los clientes traen varios vehículos, "
                    "cada vehículo tiene reparaciones y en cada reparación se utilizan distintas piezas con un precio y stock."
                ),
                "hint_1_conceptual": (
                    "Identifica la cadena de dependencias: un Cliente es dueño de varios Vehículos (1:N); "
                    "un Vehículo entra al taller para varias Reparaciones (1:N); y en una Reparación se instalan muchas Piezas "
                    "a la vez que una misma Pieza sirve en distintas Reparaciones (N:M)."
                ),
                "hint_2_estructural": (
                    "El motor inferirá automáticamente 5 tablas: `clientes`, `vehiculos` (con `cliente_id`), "
                    "`reparaciones` (con `vehiculo_id`), `piezas` (con `precio DECIMAL(10,2)` y `stock INTEGER`) "
                    "y la tabla asociativa `reparacion_piezas` (con `reparacion_id`, `pieza_id`, `cantidad` y `precio_unitario`)."
                ),
                "hint_3_solution": (
                    "Tras generar el boceto, aplica los índices sugeridos por el Auditor en un clic, pulsa **Aprobar y Desplegar**, "
                    "genera datos de prueba coherentes y ejecuta en el Editor SQL: "
                    "`SELECT c.nombre, v.matricula, r.codigo, r.total FROM clientes c INNER JOIN vehiculos v ON c.id = v.cliente_id INNER JOIN reparaciones r ON v.id = r.vehiculo_id ORDER BY r.total DESC;`."
                ),
            },
        ]
