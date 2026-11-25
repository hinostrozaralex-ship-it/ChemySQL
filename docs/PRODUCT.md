# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Backend local en Python (`FastAPI` + `Uvicorn` + `Pydantic` + `sqlite3`) ejecutado mediante `python run.py` en `http://127.0.0.1:8000`, sirviendo un Frontend Web Vanilla responsivo (`HTML5`, `CSS3`, `JavaScript ES6+` modular sin frameworks pesados de escritorio).

## Users

1. **Estudiantes y personas en aprendizaje de bases de datos (Modo Tutor):** Necesitan comprender conceptos relacionales (claves primarias/foráneas, cardinalidades 1:1, 1:N, N:M, formas normales 1FN-3FN, integridad referencial y orden lógico de ejecución SQL) trabajando sobre sus propios esquemas y datos reales con explicaciones cotidianas, comparativas visuales del "Antes y Después" y retos guiados con pistas escalonadas.
2. **Desarrolladores, analistas y diseñadores de bases de datos (Modo Estándar):** Buscan agilidad, alta densidad de datos, métricas técnicas, diseño visual ER rápido a partir de lenguaje natural o edición directa, transpilación DDL multi-dialecto (SQLite, MySQL, PostgreSQL), generación de datos sintéticos coherentes, exploración relacional y protección contra operaciones destructivas.

## Product Purpose

Concebir y operar un Sistema de Gestión de Bases de Datos (SGBD) relacional moderno, ligero, local y altamente responsivo (**ChemySQL**) que combine la solidez técnica de motores SQL reales (empezando por SQLite local en archivos `.db`) con una experiencia visual, intuitiva, preventiva y pedagógica. El éxito significa cubrir de extremo a extremo el ciclo desde una idea en texto libre en español hasta un esquema auditado, aprobado explícitamente (*Human-in-the-Loop*), desplegado en disco, poblado con datos de prueba coherentes, explorado visualmente y consultado con red de seguridad anti-desastres.

## Positioning

Un orquestador visual e inteligente **100 % determinista (sin modelos de IA ni APIs externas)** basado en algoritmos clásicos: procesamiento morfológico y sintáctico ligero en español, diccionarios heurísticos semánticos de tipos SQL, teoría de grafos para diagramas Entidad-Relación y análisis estático de árboles de sintaxis abstracta (AST) y planes de ejecución (`EXPLAIN QUERY PLAN`). Garantiza respuestas en milisegundos, cero alucinaciones, funcionamiento completamente offline y un Contrato Maestro JSON unificado como única fuente de verdad (*Single Source of Truth*) entre el lienzo ER, el auditor proactivo, el motor SQL y el Modo Tutor.

## Operating Context

- Ejecución local autónoma en escritorio Windows mediante `python run.py` escuchando en `http://127.0.0.1:8000`.
- Gestión directa de proyectos de bases de datos SQLite en archivos `.db` dentro del directorio local `workspaces/`, incluyendo bases de datos de demostración pre-cargadas listos para explorar desde el arranque.
- Uso intensivo en sesiones de modelado, auditoría de normalización, depuración de consultas SQL y aprendizaje práctico guiado, requiriendo soporte adaptable para tema oscuro y claro y paneles de trabajo redimensionables.

## Capabilities and Constraints

- **Motor de Inferencia Sintáctica y Heurística (Texto -> JSON Maestro):** Limpieza de conectores en español, extracción de sustantivos núcleo a `snake_case`, detección de cuantificadores y patrones verbales para inferir relaciones 1:N (inyectando FK `entidad_id`) y N:M (creando tabla asociativa intermedia), diccionario semántico de tipos (`DECIMAL(10,2)` para importes, `DATE`/`DATETIME` para fechas, `VARCHAR UNIQUE` para DNI/email/código, `BOOLEAN` para estados `activo`/`pagado`/`es_*`, `TEXT` para descripciones) y clave primaria subrogada por defecto (`id INTEGER PRIMARY KEY AUTOINCREMENT`).
- **Contrato Maestro JSON:** Única fuente de verdad con metadatos, tablas, columnas, relaciones con políticas `ON DELETE` / `ON UPDATE`, diagnósticos del auditor y metadatos didácticos.
- **Lienzo Visual ER Interactivo (Human-in-the-Loop):** Nodos de tablas arrastrables, visualización de relaciones y cardinalidades (1:1, 1:N, N:M), edición visual de tablas/columnas/restricciones, vista previa DDL en tiempo real (SQLite, MySQL, PostgreSQL) y despliegue transaccional explícito bajo el botón *Aprobar y Desplegar*.
- **Auditor Proactivo Estático y Dinámico:**
  - Integridad de claves PK/FK y coincidencia exacta de tipos.
  - Detección de violaciones de 1ª Forma Normal (columnas repetitivas como `telefono_1`, `telefono_2` o listas CSV) con acción de corrección automática en un clic para extraer tabla hija.
  - Validación semántica de tipos (alerta por `FLOAT`/`REAL` en dinero o `TEXT` en fechas).
  - Prevención de `ON DELETE CASCADE` peligroso hacia tablas históricas/contables (`factura`, `pago`, `pedido`, `venta`, `movimiento`, `historial`), sugiriendo `RESTRICT` o borrado lógico (`activo`, `fecha_baja`).
  - Detección de FKs sin índice e inspección de `EXPLAIN QUERY PLAN` en consultas `SELECT` para detectar *Full Table Scans* y crear índices óptimos en un clic.
  - **Escudo Anti-Desastres:** Interceptación de `UPDATE`/`DELETE` sin `WHERE` y `DROP TABLE`/`TRUNCATE` en tablas con datos o dependencias FK, mostrando diálogo crítico con conteo exacto de filas afectadas y dependencias comprometidas.
- **Modo Tutor vs. Modo Estándar:** Conmutador global en cabecera. En Modo Tutor: tarjetas didácticas contextuales sobre el diagrama ER, diagnósticos formativos con comparativa visual "Antes vs. Después", desglosador paso a paso del orden lógico de ejecución SQL (`FROM/JOIN` -> `WHERE` -> `GROUP BY` -> `HAVING` -> `SELECT` -> `ORDER BY`) con diagramas visuales de intersección de conjuntos en `JOIN`, y escenarios de práctica guiada con pistas escalonadas (conceptual -> estructural -> solución comentada).
- **Explorador Relacional, Editor SQL Dual, Mock Data y Migraciones:** Cuadrícula paginada editable con tarjeta flotante de previsualización de registros padre en celdas FK; editor SQL con resaltado/autocompletado más constructor visual guiado por reglas; generador de datos sintéticos coherentes respetando tipos, `UNIQUE`, `CHECK` y FKs; e historial de versiones del esquema con instantáneas y scripts `ALTER TABLE`.

## Evidence on Hand

- Documento de Especificación Arquitectónica completo de **ChemySQL**.
- Base de datos de demostración pre-cargada al iniciar (`taller_mecanico.db` / proyectos de ejemplo) junto con retos interactivos del Modo Tutor (Biblioteca, Clínica/Reservas, Inventario y Facturación).
- Todos los datos generados por la herramienta de *Mock Data* se etiquetan explícitamente como datos sintéticos de prueba.

## Product Principles

1. **Determinismo y Transparencia Absoluta:** Cada inferencia textual, regla de auditoría, plan de ejecución y transpilación SQL responde a reglas explícitas, predecibles y explicables en milisegundos, sin cajas negras.
2. **Human-in-the-Loop Antes de Materializar:** Ninguna inferencia o cambio estructural toca el disco sin pasar por el Contrato Maestro JSON, el lienzo de revisión visual y la confirmación explícita del usuario.
3. **Seguridad Preventiva con Contexto Real:** El sistema no solo bloquea errores o sentencias destructivas, sino que cuantifica el impacto exacto (filas afectadas, claves foráneas dependientes, escaneos completos) y ofrece remediación accionable en un clic.
4. **Pedagogía Viva sobre el Propio Esquema:** El aprendizaje no ocurre en diapositivas abstractas, sino usando las propias tablas, columnas, relaciones y consultas activas del usuario como ejemplos vivos al activar el Modo Tutor.
