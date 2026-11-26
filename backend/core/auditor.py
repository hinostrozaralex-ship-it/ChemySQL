"""
El Auditor Proactivo Estático y Dinámico de SGBD-Smart.
Evalúa el Contrato Maestro JSON y las sentencias SQL para detectar:
1. Problemas de integridad de claves (PK faltante, tipos FK incompatibles).
2. Violaciones de 1ª Forma Normal (1FN: columnas numeradas telefono_1, telefono_2 o listas CSV).
3. Tipos de datos semánticamente inadecuados (FLOAT en dinero, TEXT/VARCHAR en fechas).
4. Borrados en cascada peligrosos (ON DELETE CASCADE hacia tablas históricas o contables).
5. Claves foráneas sin índice y Full Table Scans en EXPLAIN QUERY PLAN.
6. Escudo Anti-Desastres ante UPDATE/DELETE sin WHERE y DROP/TRUNCATE sobre tablas pobladas o referenciadas.
"""

from __future__ import annotations
from datetime import datetime
import re
from typing import Any, Dict, List, Optional, Tuple

from backend.core.nlp_parser import HISTORICAL_KEYWORDS, build_column, to_plural, to_singular, to_snake_case
from backend.core.schema_model import (
    AuditAlertModel,
    ColumnModel,
    MasterSchemaContract,
    RelationModel,
    TableModel,
)


MONEY_TOKENS = (
    "precio",
    "coste",
    "costo",
    "importe",
    "salario",
    "sueldo",
    "total",
    "subtotal",
    "monto",
    "tarifa",
    "cuota",
    "presupuesto",
    "price",
    "cost",
    "amount",
    "salary",
    "wage",
    "fee",
    "budget",
    "rate",
    "balance",
)

DATE_TOKENS = (
    "fecha",
    "nacimiento",
    "vencimiento",
    "ingreso",
    "emision",
    "prestamo",
    "date",
    "birth",
    "created_at",
    "updated_at",
    "expires",
    "due_date",
)

NON_NEGATIVE_TOKENS = (
    "precio",
    "price",
    "cuota",
    "importe",
    "amount",
    "coste",
    "cost",
    "stock",
    "cantidad",
    "quantity",
    "edad",
    "age",
    "descuento",
    "discount",
    "salario",
    "salary",
    "tarifa",
    "fee",
    "num_horas",
    "hours",
)

PASSWORD_TOKENS = ("password", "passwd", "pwd", "contrasena", "clave_acceso", "pass_hash")

UNIQUE_PII_TOKENS = ("dni", "nif", "nie", "ssn", "passport", "pasaporte", "email", "correo")

SQL_RESERVED_WORDS = {
    "order",
    "user",
    "group",
    "select",
    "table",
    "index",
    "key",
    "check",
    "default",
    "values",
    "from",
    "where",
    "join",
    "limit",
    "desc",
    "asc",
    "date",
    "time",
    "values",
}


class ProactiveAuditor:
    """Motor determinista de auditoría de diseño, normalización, rendimiento y seguridad SQL."""

    def audit_schema(self, contract: MasterSchemaContract) -> List[AuditAlertModel]:
        alerts: List[AuditAlertModel] = []
        table_map: Dict[str, TableModel] = {t.name: t for t in contract.tables}

        # Sincronizar relaciones desde columnas FK si alguna fue añadida manualmente
        self._sync_relations_with_columns(contract, table_map)

        for tbl in contract.tables:
            # 1. Integridad de Clave Primaria (simple o compuesta)
            pk_cols = [c for c in tbl.columns if c.is_pk] or (
                [c for c in tbl.columns if c.name in tbl.primary_key] if tbl.primary_key else []
            )
            if not pk_cols:
                alerts.append(
                    AuditAlertModel(
                        id=f"audit_pk_missing_{tbl.name}",
                        severity="critical",
                        category="integridad_claves",
                        title=f"Tabla '{tbl.name}' sin Clave Primaria (PK)",
                        technical_message=(
                            f"La tabla '{tbl.name}' carece de una columna marcada como PRIMARY KEY. "
                            "Sin clave primaria no se puede garantizar la identidad única de las filas ni referenciar la tabla desde claves foráneas."
                        ),
                        affected_table=tbl.name,
                        auto_fix_action="add_primary_key",
                        auto_fix_label="Inyectar columna 'id' PRIMARY KEY",
                        auto_fix_payload={"table": tbl.name},
                        tutor_lesson={
                            "concept": "Identidad Relacional y Clave Primaria",
                            "why_it_matters": (
                                f"Si insertas dos registros idénticos en '{tbl.name}' sin una clave primaria, "
                                "el motor SQL no tendrá forma de distinguir cuál quieres actualizar o borrar."
                            ),
                            "before_example": f"Tabla {tbl.name} ({', '.join(c.name for c in tbl.columns[:3])}) -> Sin identificador único",
                            "after_example": f"Tabla {tbl.name} (id [PK], {', '.join(c.name for c in tbl.columns[:3])}) -> Cada fila es única e inequívoca",
                            "analogy": "Es como tener ciudadanos sin número de DNI ni pasaporte: dos personas con el mismo nombre serían indistinguibles.",
                        },
                    )
                )

            # 2. Detección de Violaciones de 1ª Forma Normal (1FN)
            # 2a. Columnas numeradas repetitivas (ej. telefono_1, telefono_2)
            numbered_groups: Dict[str, List[str]] = {}
            for col in tbl.columns:
                m = re.match(r"^([a-z][a-z0-9]*?)_?([1-9])$", col.name)
                if m:
                    base_stem = m.group(1)
                    numbered_groups.setdefault(base_stem, []).append(col.name)

            for stem, col_list in numbered_groups.items():
                if len(col_list) >= 2:
                    child_table_name = f"{to_singular(tbl.name)}_{to_plural(stem)}"
                    cols_str = ", ".join(col_list)
                    alerts.append(
                        AuditAlertModel(
                            id=f"audit_1fn_rep_{tbl.name}_{stem}",
                            severity="warning",
                            category="normalizacion_1fn",
                            title=f"Violación de 1ª Forma Normal (1FN) en '{tbl.name}': columnas repetitivas ({cols_str})",
                            technical_message=(
                                f"Las columnas numeradas ({cols_str}) en la tabla '{tbl.name}' crean un grupo repetitivo rígido. "
                                f"Impiden registrar más de {len(col_list)} valores, generan celdas NULL vacías y dificultan las búsquedas con WHERE."
                            ),
                            affected_table=tbl.name,
                            affected_column=col_list[0],
                            auto_fix_action="normalize_1fn",
                            auto_fix_label=f"Extraer a tabla hija '{child_table_name}' (1FN)",
                            auto_fix_payload={
                                "table": tbl.name,
                                "stem": stem,
                                "columns": col_list,
                                "child_table": child_table_name,
                            },
                            tutor_lesson={
                                "concept": "Primera Forma Normal (1FN): Atomicidad y Eliminación de Grupos Repetitivos",
                                "why_it_matters": (
                                    f"En la práctica, ¿qué ocurre si un '{to_singular(tbl.name)}' tiene {len(col_list) + 2} '{to_plural(stem)}' "
                                    f"o no tiene ninguno? Si no tiene ninguno, desperdicias columnas llenas de NULL; si tiene más de {len(col_list)}, "
                                    "el sistema te obliga a modificar la estructura de la base de datos. Además, para buscar un valor tendrías que escribir "
                                    f"`WHERE {col_list[0]} = X OR {col_list[1]} = X`."
                                ),
                                "before_example": (
                                    f"{tbl.name}: [id | nombre | {' | '.join(col_list)}]  <-- Límite rígido y celdas vacías"
                                ),
                                "after_example": (
                                    f"{tbl.name}: [id | nombre]  <-- 1:N -->  {child_table_name}: [id | {to_singular(tbl.name)}_id (FK) | {stem} | tipo]"
                                ),
                                "analogy": "Es como imprimir un formulario en papel con solo 2 casillas fijas en vez de usar una hoja anexa donde puedes apuntar tantas líneas como necesites.",
                            },
                        )
                    )

            # 2b. Columnas que sugieren listas separadas por comas (multivaluadas)
            for col in tbl.columns:
                if re.search(r"(^lista_|_csv$|_separados$|_multiples$|^varios_)", col.name):
                    clean_stem = re.sub(r"(^lista_|_csv$|_separados$|_multiples$|^varios_)", "", col.name) or "item"
                    child_table_name = f"{to_singular(tbl.name)}_{to_plural(clean_stem)}"
                    alerts.append(
                        AuditAlertModel(
                            id=f"audit_1fn_csv_{tbl.name}_{col.name}",
                            severity="warning",
                            category="normalizacion_1fn",
                            title=f"Violación de 1FN por atributo multivaluado '{col.name}' en '{tbl.name}'",
                            technical_message=(
                                f"La columna '{col.name}' sugiere almacenar múltiples valores separados por comas en una sola celda, "
                                "rompiendo la atomicidad de la 1ª Forma Normal e impidiendo indexación e integridad referencial."
                            ),
                            affected_table=tbl.name,
                            affected_column=col.name,
                            auto_fix_action="normalize_1fn",
                            auto_fix_label=f"Normalizar en tabla hija '{child_table_name}'",
                            auto_fix_payload={
                                "table": tbl.name,
                                "stem": to_singular(clean_stem),
                                "columns": [col.name],
                                "child_table": child_table_name,
                            },
                            tutor_lesson={
                                "concept": "1ª Forma Normal (1FN): Valores Atómicos",
                                "why_it_matters": (
                                    f"Guardar 'valor1, valor2, valor3' dentro de '{col.name}' convierte una base de datos relacional "
                                    "en un bloc de notas sin estructura: no puedes validar claves foráneas, ni contar elementos con precisión, ni usar índices."
                                ),
                                "before_example": f"{tbl.name}.{col.name} = 'A, B, C' (Celda no atómica)",
                                "after_example": f"Tabla hija '{child_table_name}' con 1 fila por cada elemento vinculado mediante '{to_singular(tbl.name)}_id'",
                                "analogy": "Meter tres productos distintos dentro de la misma línea de código de barras en un ticket de caja.",
                            },
                        )
                    )

            # 3. Validación Semántica de Tipos de Datos
            for col in tbl.columns:
                if col.is_pk or col.is_fk:
                    continue
                upper_type = col.data_type.upper()

                # 3a. Dinero en FLOAT/REAL/VARCHAR/TEXT
                if any(tok in col.name for tok in MONEY_TOKENS) and (
                    "FLOAT" in upper_type or "REAL" in upper_type or "DOUBLE" in upper_type or "TEXT" in upper_type or "VARCHAR" in upper_type
                ):
                    alerts.append(
                        AuditAlertModel(
                            id=f"audit_type_money_{tbl.name}_{col.name}",
                            severity="warning",
                            category="tipos_datos",
                            title=f"Tipo inexacto '{col.data_type}' para importe monetario '{tbl.name}.{col.name}'",
                            technical_message=(
                                f"La columna '{col.name}' almacena valores monetarios pero está definida como '{col.data_type}'. "
                                "Los tipos en coma flotante (FLOAT/REAL) sufren errores de representación binaria IEEE 754 (0.1 + 0.2 != 0.3) "
                                "y los tipos de texto impiden sumas aritméticas confiables."
                            ),
                            affected_table=tbl.name,
                            affected_column=col.name,
                            auto_fix_action="change_type_decimal",
                            auto_fix_label="Cambiar tipo a DECIMAL(10,2)",
                            auto_fix_payload={
                                "table": tbl.name,
                                "column": col.name,
                                "new_type": "DECIMAL(10,2)",
                            },
                            tutor_lesson={
                                "concept": "Precisión Financiera: DECIMAL vs FLOAT",
                                "why_it_matters": (
                                    f"Si sumas cientos de facturas o precios almacenados en FLOAT, aparecen descuadres de céntimos "
                                    "(ej. 19.990000000000002). DECIMAL(10,2) almacena dígitos exactos en base 10 con 2 decimales fijos."
                                ),
                                "before_example": f"{col.name} {col.data_type} -> 19.99 + 5.01 = 25.000000000000004",
                                "after_example": f"{col.name} DECIMAL(10,2) -> 19.99 + 5.01 = 25.00 (Exactitud contable)",
                                "analogy": "Calcular contabilidad bancaria aproximando fracciones a ojo en lugar de trabajar con céntimos exactos.",
                            },
                        )
                    )

                # 3b. Fechas en TEXT/VARCHAR
                if any(tok in col.name for tok in DATE_TOKENS) and (
                    "VARCHAR" in upper_type or "TEXT" in upper_type
                ):
                    suggested_date_type = "DATETIME" if "hora" in col.name or "registro" in col.name else "DATE"
                    alerts.append(
                        AuditAlertModel(
                            id=f"audit_type_date_{tbl.name}_{col.name}",
                            severity="suggestion",
                            category="tipos_datos",
                            title=f"Fecha almacenada como texto libre en '{tbl.name}.{col.name}' ({col.data_type})",
                            technical_message=(
                                f"Definir '{col.name}' como '{col.data_type}' permite insertar formatos inconsistentes "
                                "como '31/02/2025' o 'ayer' y rompe la ordenación cronológica cuando no se usa ISO-8601."
                            ),
                            affected_table=tbl.name,
                            affected_column=col.name,
                            auto_fix_action="change_type_date",
                            auto_fix_label=f"Cambiar tipo a {suggested_date_type}",
                            auto_fix_payload={
                                "table": tbl.name,
                                "column": col.name,
                                "new_type": suggested_date_type,
                            },
                            tutor_lesson={
                                "concept": "Tipado Semántico Temporal (DATE / DATETIME)",
                                "why_it_matters": (
                                    "Si guardas fechas como texto en formato 'DD/MM/YYYY', al ordenar con ORDER BY "
                                    "el día '02/01/2026' aparecerá antes que '15/01/2020' porque ordena alfabéticamente letra por letra."
                                ),
                                "before_example": f"{col.name} VARCHAR -> Orden alfabético erróneo ('05/12/2025' < '10/01/2021')",
                                "after_example": f"{col.name} {suggested_date_type} -> Orden cronológico real y validación de calendario",
                                "analogy": "Archivar expedientes ordenando por el primer número del día del mes en lugar del año y mes.",
                            },
                        )
                    )

            # 4. Integridad de Claves Foráneas e Índices de Rendimiento
            for col in tbl.columns:
                if not col.is_fk:
                    continue

                target_tbl_name = col.fk_target_table
                target_col_name = col.fk_target_column or "id"

                if not target_tbl_name or target_tbl_name not in table_map:
                    alerts.append(
                        AuditAlertModel(
                            id=f"audit_fk_orphan_{tbl.name}_{col.name}",
                            severity="critical",
                            category="integridad_claves",
                            title=f"Clave foránea huérfana '{tbl.name}.{col.name}'",
                            technical_message=(
                                f"La columna '{col.name}' apunta a la tabla '{target_tbl_name}', que no existe en el esquema actual."
                            ),
                            affected_table=tbl.name,
                            affected_column=col.name,
                            tutor_lesson={
                                "concept": "Integridad Referencial",
                                "why_it_matters": "Toda clave foránea debe apuntar a una tabla padre real dentro del modelo.",
                                "before_example": f"{tbl.name}.{col.name} -> {target_tbl_name} (Inexistente)",
                                "after_example": f"{tbl.name}.{col.name} -> tabla_padre.id (Válida)",
                                "analogy": "Un hipervínculo roto hacia una página que fue eliminada.",
                            },
                        )
                    )
                else:
                    target_tbl = table_map[target_tbl_name]
                    target_col = next((c for c in target_tbl.columns if c.name == target_col_name), None)
                    if not target_col:
                        alerts.append(
                            AuditAlertModel(
                                id=f"audit_fk_col_missing_{tbl.name}_{col.name}",
                                severity="critical",
                                category="integridad_claves",
                                title=f"Columna destino '{target_tbl_name}.{target_col_name}' no existe",
                                technical_message=(
                                    f"La clave foránea '{tbl.name}.{col.name}' referencia '{target_tbl_name}.{target_col_name}', "
                                    "pero esa columna no existe en la tabla padre."
                                ),
                                affected_table=tbl.name,
                                affected_column=col.name,
                            )
                        )
                    else:
                        # Verificar coincidencia exacta de tipo de dato y restricción PK/UNIQUE
                        if col.data_type.upper() != target_col.data_type.upper():
                            alerts.append(
                                AuditAlertModel(
                                    id=f"audit_fk_type_mismatch_{tbl.name}_{col.name}",
                                    severity="critical",
                                    category="integridad_claves",
                                    title=f"Incompatibilidad de tipos en FK '{tbl.name}.{col.name}' ({col.data_type} vs {target_col.data_type})",
                                    technical_message=(
                                        f"La clave foránea '{tbl.name}.{col.name}' tiene tipo '{col.data_type}', mientras que "
                                        f"la clave primaria '{target_tbl_name}.{target_col.name}' es '{target_col.data_type}'."
                                    ),
                                    affected_table=tbl.name,
                                    affected_column=col.name,
                                    auto_fix_action="sync_fk_type",
                                    auto_fix_label=f"Sincronizar tipo a {target_col.data_type}",
                                    auto_fix_payload={
                                        "table": tbl.name,
                                        "column": col.name,
                                        "new_type": target_col.data_type,
                                    },
                                    tutor_lesson={
                                        "concept": "Homogeneidad de Tipos entre PK y FK",
                                        "why_it_matters": "Una clave foránea almacena copias exactas de los valores de la clave primaria padre; por tanto, ambos deben compartir exactamente el mismo tipo de dato.",
                                        "before_example": f"{tbl.name}.{col.name} ({col.data_type}) != {target_tbl_name}.{target_col.name} ({target_col.data_type})",
                                        "after_example": f"Ambos unificados como {target_col.data_type}",
                                        "analogy": "Intentar encajar una clavija cuadrada en un enchufe redondo.",
                                    },
                                )
                            )

                # 5. Auditoría de Rendimiento: ¿La FK tiene índice asociado?
                if col.name not in tbl.indexes and not col.is_pk:
                    alerts.append(
                        AuditAlertModel(
                            id=f"audit_idx_fk_{tbl.name}_{col.name}",
                            severity="suggestion",
                            category="rendimiento_indices",
                            title=f"Clave foránea '{tbl.name}.{col.name}' sin índice de búsqueda (INDEX)",
                            technical_message=(
                                f"La columna '{col.name}' se utilizará frecuentemente en cruces `JOIN` con '{target_tbl_name}', "
                                "pero no tiene un índice definido. En tablas grandes provocará un escaneo completo (Full Table Scan)."
                            ),
                            affected_table=tbl.name,
                            affected_column=col.name,
                            auto_fix_action="create_fk_index",
                            auto_fix_label=f"Crear índice idx_{tbl.name}_{col.name}",
                            auto_fix_payload={
                                "table": tbl.name,
                                "column": col.name,
                            },
                            tutor_lesson={
                                "concept": "Indexación de Claves Foráneas y Rendimiento en JOIN",
                                "why_it_matters": (
                                    f"Las claves primarias crean un índice automático, pero las claves foráneas NO siempre lo hacen por defecto. "
                                    f"Sin un índice en '{tbl.name}.{col.name}', cada vez que consultes los registros de un '{to_singular(target_tbl_name or 'padre')}', "
                                    f"el motor tendrá que leer la tabla '{tbl.name}' fila por fila de principio a fin."
                                ),
                                "before_example": f"SELECT * FROM {tbl.name} WHERE {col.name} = 42 -> Lee el 100% de la tabla (SCAN)",
                                "after_example": f"CREATE INDEX idx_{tbl.name}_{col.name} -> Salto directo en árbol B-Tree en milisegundos (SEARCH)",
                                "analogy": "Buscar un tema en un libro de 800 páginas pasando hoja por hoja en lugar de consultar el índice alfabético al final del libro.",
                            },
                        )
                    )

        # 6. Prevención de Borrados en Cascada Peligrosos (ON DELETE CASCADE en tablas históricas/contables)
        for rel in contract.relations:
            source_tbl = table_map.get(rel.source_table)
            is_hist = False
            if source_tbl and source_tbl.is_historical:
                is_hist = True
            elif any(h in rel.source_table.lower() for h in HISTORICAL_KEYWORDS):
                is_hist = True

            if rel.on_delete == "CASCADE" and is_hist:
                alerts.append(
                    AuditAlertModel(
                        id=f"audit_cascade_danger_{rel.id}",
                        severity="critical",
                        category="cascada_peligrosa",
                        title=f"Riesgo contable/histórico: ON DELETE CASCADE hacia '{rel.source_table}'",
                        technical_message=(
                            f"La relación desde '{rel.target_table}' hacia '{rel.source_table}' tiene configurado `ON DELETE CASCADE`. "
                            f"Si se elimina un registro de '{rel.target_table}', el motor borrará automáticamente todos sus registros históricos/contables en '{rel.source_table}', "
                            "destruyendo trazabilidad legal y auditoría financiera."
                        ),
                        affected_table=rel.source_table,
                        affected_column=rel.source_column,
                        affected_relation_id=rel.id,
                        auto_fix_action="change_on_delete_restrict",
                        auto_fix_label="Proteger con ON DELETE RESTRICT + Borrado Lógico",
                        auto_fix_payload={
                            "relation_id": rel.id,
                            "parent_table": rel.target_table,
                            "child_table": rel.source_table,
                        },
                        tutor_lesson={
                            "concept": "Peligros de ON DELETE CASCADE en Tablas Históricas o Contables",
                            "why_it_matters": (
                                f"Imagina que das de baja a un '{to_singular(rel.target_table)}' antiguo con `DELETE`. "
                                f"Con `ON DELETE CASCADE`, la base de datos destruirá silenciosamente todas sus '{rel.source_table}' de años anteriores, "
                                "descuadrando la contabilidad anual. La buena práctica profesional es usar `ON DELETE RESTRICT` "
                                f"y desactivar al '{to_singular(rel.target_table)}' mediante una columna `activo = 0` o `fecha_baja` (Borrado Lógico)."
                            ),
                            "before_example": f"DELETE FROM {rel.target_table} WHERE id = 5 -> ¡Se destruyen todas sus filas en {rel.source_table}!",
                            "after_example": (
                                f"ON DELETE RESTRICT + UPDATE {rel.target_table} SET activo = 0, fecha_baja = CURRENT_DATE WHERE id = 5"
                            ),
                            "analogy": "Quemar todas las facturas emitidas de la caja fuerte del archivo contable solo porque un cliente dejó de comprar en la tienda.",
                        },
                    )
                )

        # 5. Reglas Avanzadas: 2FN, 3FN, Seguridad (Password/PII), CHECK de dominio, Grafo y Palabras Reservadas
        self._audit_advanced_rules(contract, table_map, alerts)

        contract.audit_alerts = alerts
        contract.tutor_metadata = dict(contract.tutor_metadata or {})
        contract.tutor_metadata["audit_summary"] = self.compute_health_score(alerts)
        return alerts

    def compute_health_score(self, alerts: List[AuditAlertModel]) -> Dict[str, Any]:
        """Calcula el Índice de Salud del Esquema (0-100) y Grado (A+ a D) de forma determinista."""
        critical = sum(1 for a in alerts if a.severity == "critical")
        warnings = sum(1 for a in alerts if a.severity == "warning")
        infos = sum(1 for a in alerts if a.severity == "info")
        score = max(0, min(100, 100 - critical * 18 - warnings * 7 - infos * 2))
        if score >= 95:
            grade = "A+"
        elif score >= 85:
            grade = "A"
        elif score >= 70:
            grade = "B"
        elif score >= 50:
            grade = "C"
        else:
            grade = "D"
        safe_fixable = sum(
            1
            for a in alerts
            if a.auto_fix_action
            in (
                "create_fk_index",
                "change_type_decimal",
                "change_type_date",
                "sync_fk_type",
                "widen_password_hash",
                "add_unique_constraint",
                "add_non_negative_check",
                "add_primary_key",
            )
        )
        return {
            "score": score,
            "grade": grade,
            "critical": critical,
            "warning": warnings,
            "info": infos,
            "total": len(alerts),
            "safe_fixable": safe_fixable,
        }

    def _audit_advanced_rules(
        self,
        contract: MasterSchemaContract,
        table_map: Dict[str, TableModel],
        alerts: List[AuditAlertModel],
    ) -> None:
        # 5a. Palabras reservadas SQL, Seguridad (Password / PII UNIQUE) y CHECK de dominio
        for tbl in contract.tables:
            if tbl.name.lower() in SQL_RESERVED_WORDS:
                alerts.append(
                    AuditAlertModel(
                        id=f"audit_reserved_tbl_{tbl.name}",
                        severity="warning",
                        category="portabilidad",
                        title=f"Nombre de tabla '{tbl.name}' es una palabra reservada SQL",
                        technical_message=(
                            f"'{tbl.name}' es una palabra reservada en SQL estándar. Al migrar a MySQL, PostgreSQL o SQL Server "
                            "requerirá comillas delimitadoras en cada consulta y puede provocar errores de sintaxis."
                        ),
                        affected_table=tbl.name,
                    )
                )

            pk_cols = [c for c in tbl.columns if c.is_pk] or (
                [c for c in tbl.columns if c.name in tbl.primary_key] if tbl.primary_key else []
            )
            pk_names = {c.name.lower() for c in pk_cols}

            # Detectar tablas padre referenciadas por esta tabla (para 2FN / 3FN)
            fk_parents = {
                c.fk_target_table
                for c in tbl.columns
                if c.is_fk and c.fk_target_table and c.fk_target_table in table_map and c.fk_target_table != tbl.name
            }

            for col in tbl.columns:
                low_col = col.name.lower()
                up_type = col.data_type.upper()

                # Seguridad: Contraseñas cortas (texto plano en vez de hash)
                if any(tok in low_col for tok in PASSWORD_TOKENS):
                    if up_type in ("VARCHAR", "CHAR") and (col.length is None or col.length < 60):
                        alerts.append(
                            AuditAlertModel(
                                id=f"audit_sec_pwd_{tbl.name}_{col.name}",
                                severity="critical",
                                category="seguridad",
                                title=f"Columna de contraseña '{tbl.name}.{col.name}' demasiado corta para hash seguro",
                                technical_message=(
                                    f"'{col.name}' tiene tipo {col.data_type}({col.length or 'sin longitud'}), insuficiente para almacenar "
                                    "hashes modernos (bcrypt/Argon2 requieren ≥ 60–255 caracteres). Nunca guardes contraseñas en texto plano."
                                ),
                                affected_table=tbl.name,
                                affected_column=col.name,
                                auto_fix_action="widen_password_hash",
                                auto_fix_label="Ampliar a VARCHAR(255) para hash seguro",
                                auto_fix_payload={"table": tbl.name, "column": col.name},
                            )
                        )

                # Seguridad / PII: DNI / Email / SSN sin UNIQUE
                if (
                    any(low_col == tok or low_col.endswith(f"_{tok}") for tok in UNIQUE_PII_TOKENS)
                    and not col.is_unique
                    and not col.is_pk
                    and not col.is_fk
                ):
                    alerts.append(
                        AuditAlertModel(
                            id=f"audit_sec_pii_uq_{tbl.name}_{col.name}",
                            severity="info",
                            category="seguridad",
                            title=f"Identificador personal '{tbl.name}.{col.name}' sin restricción UNIQUE",
                            technical_message=(
                                f"La columna '{col.name}' almacena un dato identificativo único por persona. "
                                "Añadir UNIQUE evita duplicados accidentales y acelera búsquedas por ese campo."
                            ),
                            affected_table=tbl.name,
                            affected_column=col.name,
                            auto_fix_action="add_unique_constraint",
                            auto_fix_label=f"Añadir UNIQUE en '{col.name}'",
                            auto_fix_payload={"table": tbl.name, "column": col.name},
                        )
                    )

                # Integridad de dominio: columnas monetarias/cantidad sin CHECK (>= 0)
                if (
                    any(tok in low_col for tok in NON_NEGATIVE_TOKENS)
                    and not col.check_constraint
                    and not col.is_pk
                    and not col.is_fk
                    and not col.computed_expression
                    and any(nt in up_type for nt in ("DECIMAL", "NUMERIC", "INT", "FLOAT", "REAL"))
                ):
                    alerts.append(
                        AuditAlertModel(
                            id=f"audit_domain_chk_{tbl.name}_{col.name}",
                            severity="info",
                            category="integridad_dominio",
                            title=f"Columna '{tbl.name}.{col.name}' sin restricción CHECK (>= 0)",
                            technical_message=(
                                f"La columna numérica '{col.name}' acepta valores negativos actualmente. "
                                f"Añadir `CHECK ({col.name} >= 0)` garantiza integridad de dominio directamente en el motor SQL."
                            ),
                            affected_table=tbl.name,
                            affected_column=col.name,
                            auto_fix_action="add_non_negative_check",
                            auto_fix_label=f"Añadir CHECK ({col.name} >= 0)",
                            auto_fix_payload={"table": tbl.name, "column": col.name},
                        )
                    )

                # 2FN / 3FN: redundancia de atributos de una tabla padre en una tabla hija
                if low_col not in pk_names and not col.is_fk and fk_parents:
                    for parent_name in fk_parents:
                        p_sing = to_singular(parent_name).lower()
                        p_low = parent_name.lower()
                        if len(p_sing) >= 4 and (
                            low_col.endswith(f"_{p_sing}") or low_col.endswith(f"_{p_low}")
                        ):
                            is_2fn = len(pk_cols) > 1
                            norm_label = "2ª Forma Normal (2FN)" if is_2fn else "3ª Forma Normal (3FN)"
                            cat = "normalizacion_2fn" if is_2fn else "normalizacion_3fn"
                            alerts.append(
                                AuditAlertModel(
                                    id=f"audit_norm_{cat}_{tbl.name}_{col.name}",
                                    severity="warning",
                                    category=cat,
                                    title=f"Posible violación de {norm_label} en '{tbl.name}.{col.name}'",
                                    technical_message=(
                                        f"'{tbl.name}' ya referencia a '{parent_name}' mediante clave foránea, pero también almacena '{col.name}'. "
                                        f"Este atributo parece depender de '{parent_name}' y genera redundancia/anomalías de actualización."
                                    ),
                                    affected_table=tbl.name,
                                    affected_column=col.name,
                                )
                            )
                            break

        # 5b. Detección de ciclos en claves foráneas (DFS)
        adj: Dict[str, List[str]] = {t.name: [] for t in contract.tables}
        for r in contract.relations:
            if r.source_table in adj and r.target_table in adj and r.source_table != r.target_table:
                adj[r.source_table].append(r.target_table)

        visited_state: Dict[str, int] = {t.name: 0 for t in contract.tables}
        cycle_reported: set = set()

        def dfs_cycle(node: str, path: List[str]) -> None:
            visited_state[node] = 1
            for nxt in adj.get(node, []):
                if visited_state.get(nxt, 0) == 1:
                    cycle_slice = path[path.index(nxt) :] + [nxt]
                    sig = tuple(sorted(set(cycle_slice)))
                    if sig not in cycle_reported:
                        cycle_reported.add(sig)
                        chain = " → ".join(cycle_slice)
                        alerts.append(
                            AuditAlertModel(
                                id=f"audit_fk_cycle_{'_'.join(sig)}",
                                severity="warning",
                                category="grafo_relacional",
                                title=f"Ciclo de claves foráneas detectado ({chain})",
                                technical_message=(
                                    f"Existe una dependencia circular entre tablas ({chain}). "
                                    "Los ciclos referenciales dificultan inserciones iniciales, migraciones y borrados en orden topológico."
                                ),
                                affected_table=nxt,
                            )
                        )
                elif visited_state.get(nxt, 0) == 0:
                    dfs_cycle(nxt, path + [nxt])
            visited_state[node] = 2

        for t_name in list(adj.keys()):
            if visited_state[t_name] == 0:
                dfs_cycle(t_name, [t_name])

        # 5c. Tablas aisladas / desconectadas en esquemas con >= 3 tablas
        if len(contract.tables) >= 3:
            connected = set()
            for r in contract.relations:
                connected.add(r.source_table)
                connected.add(r.target_table)
            for tbl in contract.tables:
                if tbl.name not in connected:
                    alerts.append(
                        AuditAlertModel(
                            id=f"audit_isolated_tbl_{tbl.name}",
                            severity="info",
                            category="grafo_relacional",
                            title=f"Tabla aislada '{tbl.name}' sin relaciones con el resto del esquema",
                            technical_message=(
                                f"'{tbl.name}' no participa en ninguna clave foránea (ni entrante ni saliente). "
                                "Verifica si debe vincularse a otra entidad mediante 'Vincular Tablas (FK)'."
                            ),
                            affected_table=tbl.name,
                        )
                    )

    def apply_auto_fix(self, contract: MasterSchemaContract, alert_id: str) -> Tuple[MasterSchemaContract, str]:
        """Aplica la acción de corrección automática en un clic sobre el Contrato Maestro JSON."""
        self.audit_schema(contract)
        alert = next((a for a in contract.audit_alerts if a.id == alert_id), None)
        if not alert or not alert.auto_fix_action:
            raise ValueError(f"No se encontró una acción automática para la alerta '{alert_id}'.")

        action = alert.auto_fix_action
        payload = alert.auto_fix_payload
        table_map = {t.name: t for t in contract.tables}
        summary = ""

        if action == "add_primary_key":
            tbl_name = payload["table"]
            tbl = table_map[tbl_name]
            tbl.columns.insert(0, build_column("id", f"Identificador único de {tbl_name}", is_pk=True))
            summary = f"Se inyectó la clave primaria subrogada 'id' en la tabla '{tbl_name}'."

        elif action == "normalize_1fn":
            tbl_name = payload["table"]
            stem = payload["stem"]
            cols_to_remove = set(payload["columns"])
            child_name = payload["child_table"]
            parent_tbl = table_map[tbl_name]

            # 1. Eliminar las columnas repetitivas o multivaluadas de la tabla padre
            parent_tbl.columns = [c for c in parent_tbl.columns if c.name not in cols_to_remove]

            # 2. Crear la tabla hija normalizada en 1FN
            fk_col_name = f"{to_singular(tbl_name)}_id"
            if child_name not in table_map:
                new_child_tbl = TableModel(
                    name=child_name,
                    description=f"Tabla normalizada (1FN) extraída de '{tbl_name}' para almacenar múltiples '{to_plural(stem)}'.",
                    is_associative=False,
                    is_historical=False,
                    position_x=parent_tbl.position_x + 360.0,
                    position_y=parent_tbl.position_y + 60.0,
                    columns=[
                        build_column("id", f"Identificador único de {child_name}", is_pk=True),
                        build_column(
                            fk_col_name,
                            f"Referencia a {tbl_name}.id",
                            is_fk=True,
                            fk_target_table=tbl_name,
                            fk_target_column="id",
                        ),
                        build_column(stem, f"Valor atómico de {stem}"),
                        build_column("etiqueta", f"Tipo o descripción (Principal, Trabajo, Secundario)"),
                        build_column("principal", f"Indica si es el {stem} preferido", force_type="BOOLEAN"),
                    ],
                    indexes=[fk_col_name],
                    tutor_explanation=(
                        f"Tabla extraída automáticamente para cumplir la 1ª Forma Normal (1FN). "
                        f"Ahora un '{to_singular(tbl_name)}' puede tener 0, 1 o N '{to_plural(stem)}' sin desperdiciar espacio."
                    ),
                )
                contract.tables.append(new_child_tbl)
                contract.relations.append(
                    RelationModel(
                        id=f"rel_{child_name}_{tbl_name}",
                        source_table=child_name,
                        source_column=fk_col_name,
                        target_table=tbl_name,
                        target_column="id",
                        cardinality="1:N",
                        on_delete="CASCADE",
                        on_update="CASCADE",
                        tutor_explanation=(
                            f"Relación 1:N resultante de normalizar los atributos repetitivos ({', '.join(cols_to_remove)}) de '{tbl_name}'."
                        ),
                    )
                )
            summary = (
                f"1FN aplicada: se extrajeron las columnas ({', '.join(cols_to_remove)}) de '{tbl_name}' "
                f"hacia la nueva tabla hija relacionada '{child_name}' con su clave foránea e índice."
            )

        elif action in ("change_type_decimal", "change_type_date", "sync_fk_type"):
            tbl = table_map[payload["table"]]
            col = next(c for c in tbl.columns if c.name == payload["column"])
            old_type = col.data_type
            col.data_type = payload["new_type"]
            col.length = None
            summary = f"Se actualizó el tipo de '{tbl.name}.{col.name}' de {old_type} a {col.data_type}."

        elif action == "create_fk_index":
            tbl = table_map[payload["table"]]
            col_name = payload["column"]
            if col_name not in tbl.indexes:
                tbl.indexes.append(col_name)
            summary = f"Se añadió el índice de rendimiento 'idx_{tbl.name}_{col_name}' en la tabla '{tbl.name}'."

        elif action == "widen_password_hash":
            tbl = table_map[payload["table"]]
            col = next(c for c in tbl.columns if c.name == payload["column"])
            col.data_type = "VARCHAR"
            col.length = 255
            col.nullable = False
            summary = f"Seguridad aplicada: '{tbl.name}.{col.name}' ampliada a VARCHAR(255) NOT NULL para hashes seguros."

        elif action == "add_unique_constraint":
            tbl = table_map[payload["table"]]
            col = next(c for c in tbl.columns if c.name == payload["column"])
            col.is_unique = True
            summary = f"Se añadió la restricción UNIQUE sobre '{tbl.name}.{col.name}'."

        elif action == "add_non_negative_check":
            tbl = table_map[payload["table"]]
            col = next(c for c in tbl.columns if c.name == payload["column"])
            col.check_constraint = f"{col.name} >= 0"
            summary = f"Se añadió la regla de dominio CHECK ({col.name} >= 0) en '{tbl.name}.{col.name}'."

        elif action == "change_on_delete_restrict":
            rel_id = payload["relation_id"]
            parent_tbl_name = payload["parent_table"]
            rel = next(r for r in contract.relations if r.id == rel_id)
            rel.on_delete = "RESTRICT"
            # Añadir columnas de borrado lógico a la tabla padre si no las tiene
            if parent_tbl_name in table_map:
                ptbl = table_map[parent_tbl_name]
                existing_names = {c.name for c in ptbl.columns}
                if "activo" not in existing_names:
                    ptbl.columns.append(build_column("activo", "Estado activo para borrado lógico"))
                if "fecha_baja" not in existing_names:
                    ptbl.columns.append(build_column("fecha_baja", "Fecha de baja lógica sin destruir historial"))
            summary = (
                f"Se cambió la política de '{rel.source_table} -> {rel.target_table}' a ON DELETE RESTRICT "
                f"y se habilitó el borrado lógico (activo, fecha_baja) en '{parent_tbl_name}'."
            )

        contract.updated_at = datetime.now().isoformat(timespec="seconds")
        self.audit_schema(contract)
        return contract, summary

    def apply_all_safe_fixes(self, contract: MasterSchemaContract) -> Tuple[MasterSchemaContract, int, List[str]]:
        """Aplica en una sola pasada todas las correcciones seguras no destructivas del Auditor."""
        safe_actions = {
            "create_fk_index",
            "change_type_decimal",
            "change_type_date",
            "sync_fk_type",
            "widen_password_hash",
            "add_unique_constraint",
            "add_non_negative_check",
            "add_primary_key",
        }
        applied: List[str] = []
        self.audit_schema(contract)
        for _ in range(30):
            target = next(
                (a for a in contract.audit_alerts if a.auto_fix_action in safe_actions),
                None,
            )
            if not target:
                break
            contract, msg = self.apply_auto_fix(contract, target.id)
            applied.append(msg)
        return contract, len(applied), applied

    def _sync_relations_with_columns(
        self, contract: MasterSchemaContract, table_map: Dict[str, TableModel]
    ) -> None:
        existing_pairs = {(r.source_table, r.source_column, r.target_table) for r in contract.relations}
        for tbl in contract.tables:
            for col in tbl.columns:
                if col.is_fk and col.fk_target_table:
                    key = (tbl.name, col.name, col.fk_target_table)
                    if key not in existing_pairs:
                        contract.relations.append(
                            RelationModel(
                                id=f"rel_{tbl.name}_{col.name}_{col.fk_target_table}",
                                source_table=tbl.name,
                                source_column=col.name,
                                target_table=col.fk_target_table,
                                target_column=col.fk_target_column or "id",
                                cardinality="1:N",
                                on_delete="RESTRICT",
                                on_update="CASCADE",
                                tutor_explanation=(
                                    f"Vínculo relacional entre '{tbl.name}.{col.name}' y '{col.fk_target_table}.id'."
                                ),
                            )
                        )
                        existing_pairs.add(key)

    def _strip_leading_cte(self, sql: str) -> str:
        """Elimina una cláusula WITH [RECURSIVE] ... inicial para inspeccionar la sentencia principal real."""
        s = sql.strip()
        m_with = re.match(r"^WITH\s+(?:RECURSIVE\s+)?", s, flags=re.IGNORECASE)
        if not m_with:
            return s
        pos = m_with.end()
        n = len(s)
        while pos < n:
            m_as = re.search(r"\bAS\s*\(", s[pos:], flags=re.IGNORECASE)
            if not m_as:
                return s
            pos += m_as.end()
            depth = 1
            in_sq = False
            while pos < n and depth > 0:
                ch = s[pos]
                if ch == "'":
                    in_sq = not in_sq
                elif not in_sq:
                    if ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                pos += 1
            while pos < n and s[pos].isspace():
                pos += 1
            if pos < n and s[pos] == ",":
                pos += 1
                continue
            return s[pos:].strip()
        return s

    def inspect_sql_safety(self, sql: str) -> Dict[str, Any]:
        """
        Escudo Anti-Desastres: analiza la instrucción SQL antes de enviarla al motor.
        Detecta UPDATE/DELETE sin WHERE (incluyendo tras CTE WITH ...) y DROP TABLE / TRUNCATE TABLE.
        """
        cleaned = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
        cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL).strip()

        if not cleaned:
            return {"is_dangerous": False, "statement_type": "EMPTY"}

        main_stmt = self._strip_leading_cte(cleaned)
        upper_sql = main_stmt.upper()
        first_token = upper_sql.split()[0] if upper_sql.split() else ""

        # 1. UPDATE sin WHERE
        if first_token == "UPDATE":
            m_tbl = re.match(r"^UPDATE\s+[`\"'\[]?([a-zA-Z0-9_]+)[`\"'\]]?", main_stmt, flags=re.IGNORECASE)
            target_table = m_tbl.group(1) if m_tbl else "desconocida"
            has_where = bool(re.search(r"\bWHERE\b\s+.+", main_stmt, flags=re.IGNORECASE | re.DOTALL))
            trivial_where = bool(
                re.search(r"\bWHERE\s+(?:1\s*=\s*1|TRUE)\b|\bOR\s+(?:1\s*=\s*1|TRUE)\b", main_stmt, flags=re.IGNORECASE)
            )
            if not has_where or trivial_where:
                return {
                    "is_dangerous": True,
                    "statement_type": "UPDATE_WITHOUT_WHERE",
                    "target_table": target_table,
                    "risk_level": "critical",
                    "title": f"Escudo Anti-Desastres: UPDATE sin cláusula WHERE sobre '{target_table}'",
                    "reason": (
                        f"La sentencia `UPDATE {target_table}` carece de una condición `WHERE` restrictiva. "
                        "Si se ejecuta, sobrescribirá todas las filas existentes en la tabla de forma irreversible."
                    ),
                }

        # 2. DELETE sin WHERE
        if first_token == "DELETE":
            m_tbl = re.search(r"\bFROM\s+[`\"'\[]?([a-zA-Z0-9_]+)[`\"'\]]?", main_stmt, flags=re.IGNORECASE)
            target_table = m_tbl.group(1) if m_tbl else "desconocida"
            has_where = bool(re.search(r"\bWHERE\b\s+.+", main_stmt, flags=re.IGNORECASE | re.DOTALL))
            trivial_where = bool(
                re.search(r"\bWHERE\s+(?:1\s*=\s*1|TRUE)\b|\bOR\s+(?:1\s*=\s*1|TRUE)\b", main_stmt, flags=re.IGNORECASE)
            )
            if not has_where or trivial_where:
                return {
                    "is_dangerous": True,
                    "statement_type": "DELETE_WITHOUT_WHERE",
                    "target_table": target_table,
                    "risk_level": "critical",
                    "title": f"Escudo Anti-Desastres: DELETE sin cláusula WHERE sobre '{target_table}'",
                    "reason": (
                        f"La instrucción `DELETE FROM {target_table}` no incluye filtro `WHERE`. "
                        "Vaciará por completo todos los registros de la tabla."
                    ),
                }

        # 3. DROP TABLE o TRUNCATE
        if first_token in ("DROP", "TRUNCATE"):
            m_tbl = re.search(
                r"\b(?:TABLE\s+(?:IF\s+EXISTS\s+)?|TRUNCATE\s+(?:TABLE\s+)?)[`\"'\[]?([a-zA-Z0-9_]+)[`\"'\]]?",
                main_stmt,
                flags=re.IGNORECASE,
            )
            target_table = m_tbl.group(1) if m_tbl else "desconocida"
            return {
                "is_dangerous": True,
                "statement_type": f"{first_token}_TABLE",
                "target_table": target_table,
                "risk_level": "critical",
                "title": f"Escudo Anti-Desastres: Operación destructiva {first_token} sobre '{target_table}'",
                "reason": (
                    f"Estás a punto de destruir la estructura y todos los datos de la tabla '{target_table}' "
                    "junto con las referencias de integridad dependientes."
                ),
            }

        return {
            "is_dangerous": False,
            "statement_type": first_token,
        }

    def analyze_query_plan(
        self, sql: str, explain_steps: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Analiza la salida de EXPLAIN QUERY PLAN en consultas SELECT para detectar
        Full Table Scans (SCAN) sobre columnas filtradas en WHERE, JOIN u ORDER BY,
        y sugiere el índice exacto a crear en un clic.
        """
        recommendations: List[Dict[str, Any]] = []
        cleaned_sql = re.sub(r"\s+", " ", sql.strip())

        # Extraer alias de tablas en FROM y JOIN: ej. FROM clientes c JOIN vehiculos v
        alias_map: Dict[str, str] = {}
        for m in re.finditer(
            r"\b(?:FROM|JOIN)\s+([a-zA-Z0-9_]+)(?:\s+(?:AS\s+)?([a-zA-Z0-9_]+))?",
            cleaned_sql,
            flags=re.IGNORECASE,
        ):
            tbl_name = m.group(1)
            alias = m.group(2)
            alias_map[tbl_name.lower()] = tbl_name
            if alias and alias.upper() not in ("ON", "WHERE", "INNER", "LEFT", "RIGHT", "JOIN", "ORDER", "GROUP", "LIMIT"):
                alias_map[alias.lower()] = tbl_name

        # Extraer columnas usadas en WHERE, ON y ORDER BY
        candidate_cols_by_table: Dict[str, List[str]] = {}
        for m in re.finditer(r"\b(?:([a-zA-Z0-9_]+)\.)?([a-zA-Z0-9_]+)\s*(?:=|>|<|>=|<=|LIKE|IN|BETWEEN)\b", cleaned_sql, flags=re.IGNORECASE):
            prefix = (m.group(1) or "").lower()
            col_name = m.group(2).lower()
            if col_name in ("id", "1", "true", "false"):
                continue
            resolved_table = alias_map.get(prefix, "")
            if resolved_table:
                candidate_cols_by_table.setdefault(resolved_table.lower(), []).append(col_name)
            else:
                for t_actual in set(alias_map.values()):
                    candidate_cols_by_table.setdefault(t_actual.lower(), []).append(col_name)

        for m in re.finditer(r"\bORDER\s+BY\s+(?:([a-zA-Z0-9_]+)\.)?([a-zA-Z0-9_]+)", cleaned_sql, flags=re.IGNORECASE):
            prefix = (m.group(1) or "").lower()
            col_name = m.group(2).lower()
            if col_name == "id":
                continue
            resolved_table = alias_map.get(prefix, "")
            if resolved_table:
                candidate_cols_by_table.setdefault(resolved_table.lower(), []).append(col_name)
            else:
                for t_actual in set(alias_map.values()):
                    candidate_cols_by_table.setdefault(t_actual.lower(), []).append(col_name)

        for step in explain_steps:
            detail = str(step.get("detail", ""))
            # En SQLite EXPLAIN QUERY PLAN: "SCAN clientes" o "SCAN TABLE clientes"
            m_scan = re.search(r"\bSCAN\s+(?:TABLE\s+)?([a-zA-Z0-9_]+)\b", detail, flags=re.IGNORECASE)
            if m_scan and "USING INDEX" not in detail.upper() and "COVERING INDEX" not in detail.upper():
                scanned_table = m_scan.group(1)
                cols = candidate_cols_by_table.get(scanned_table.lower(), [])
                if cols:
                    suggested_col = cols[0]
                    idx_name = f"idx_{scanned_table}_{suggested_col}"
                    recommendations.append(
                        {
                            "table": scanned_table,
                            "column": suggested_col,
                            "index_name": idx_name,
                            "ddl": f"CREATE INDEX IF NOT EXISTS {idx_name} ON {scanned_table} ({suggested_col});",
                            "plan_detail": detail,
                            "message": (
                                f"Escaneo completo detectado (`{detail}`) al filtrar u ordenar por `{scanned_table}.{suggested_col}`. "
                                f"Crear el índice `{idx_name}` convertirá el escaneo secuencial en una búsqueda indexada B-Tree."
                            ),
                        }
                    )
                else:
                    recommendations.append(
                        {
                            "table": scanned_table,
                            "column": None,
                            "index_name": None,
                            "ddl": None,
                            "plan_detail": detail,
                            "severity": "info",
                            "message": (
                                f"Lectura secuencial completa (`{detail}`) sobre `{scanned_table}`. "
                                "Es normal si consultas toda la tabla sin filtro WHERE, pero considera filtrar o paginar si la tabla crece."
                            ),
                        }
                    )

        # Anti-patrones estáticos de rendimiento en la consulta SELECT
        if re.search(r"\bJOIN\b", cleaned_sql, flags=re.IGNORECASE) and not re.search(
            r"\b(?:ON|USING|NATURAL|CROSS\s+JOIN)\b", cleaned_sql, flags=re.IGNORECASE
        ):
            recommendations.append(
                {
                    "table": None,
                    "column": None,
                    "index_name": None,
                    "ddl": None,
                    "severity": "critical",
                    "message": (
                        "Anti-patrón crítico: JOIN sin cláusula ON ni USING. "
                        "Genera un producto cartesiano (N × M filas) que degrada severamente el rendimiento."
                    ),
                }
            )

        if re.search(r"\bLIKE\s+'%", cleaned_sql, flags=re.IGNORECASE):
            recommendations.append(
                {
                    "table": None,
                    "column": None,
                    "index_name": None,
                    "ddl": None,
                    "severity": "warning",
                    "message": (
                        "Anti-patrón de rendimiento: `LIKE '%texto%'` con comodín inicial impide usar índices B-Tree. "
                        "Cuando sea posible usa prefijo (`LIKE 'texto%'`)."
                    ),
                }
            )

        if re.search(
            r"\bWHERE\b[^;]*\b(?:LOWER|UPPER|SUBSTR|SUBSTRING|TRIM|YEAR|MONTH|DATE)\s*\(\s*[a-zA-Z_][a-zA-Z0-9_.]*\s*\)",
            cleaned_sql,
            flags=re.IGNORECASE,
        ):
            recommendations.append(
                {
                    "table": None,
                    "column": None,
                    "index_name": None,
                    "ddl": None,
                    "severity": "warning",
                    "message": (
                        "Anti-patrón SARGable: aplicar una función sobre una columna dentro del WHERE "
                        "(ej. LOWER(col) o YEAR(fecha)) impide aprovechar índices sobre esa columna."
                    ),
                }
            )

        if re.search(r"^SELECT\s+\*\s+FROM\b", cleaned_sql, flags=re.IGNORECASE) and re.search(
            r"\bJOIN\b", cleaned_sql, flags=re.IGNORECASE
        ):
            recommendations.append(
                {
                    "table": None,
                    "column": None,
                    "index_name": None,
                    "ddl": None,
                    "severity": "info",
                    "message": (
                        "Buena práctica: evita `SELECT *` en consultas con JOIN; selecciona solo las columnas necesarias "
                        "para reducir transferencia y evitar colisiones de nombres."
                    ),
                }
            )

        return recommendations
