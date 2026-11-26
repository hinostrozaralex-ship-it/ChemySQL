# Changelog

Todos los cambios relevantes de **ChemySQL** se documentan en este archivo.

## [1.7.0] - 2026-11-26

### Añadido y mejorado
* **Fidelidad DDL Multi-Dialecto y Exportación SQL Completa:**
  * Selector **`IF NOT EXISTS: OFF / ON`** en el Editor DDL para alternar entre scripts estándar limpios (`CREATE DATABASE ...; CREATE TABLE ...;`) y scripts idempotentes.
  * `parse_ddl_to_contract` ahora lee `CREATE DATABASE`, `USE` y `COLLATE` respetando identificadores exactos (ej. `Polideportivo`) y preserva descripciones, cardinalidades (`1:1`, `N:M`), `is_associative`, `is_historical` y dependencias funcionales al sincronizar código DDL ↔ Lienzo ER (con soporte completo de `Ctrl+Z` / `Ctrl+Y`).
  * Prevención automática de rutas convergentes/cíclicas de cascada en SQL Server (error T-SQL 1785), tipos `NVARCHAR(MAX)`/`DOUBLE PRECISION` y botón **`Exportar BD + Datos (.sql)`** en orden topológico (`DDL + INSERT` con `SET IDENTITY_INSERT` cuando procede).
* **Proyecto Portable (`.chemysql`), Persistencia de Maquetación y Escudo Pre-Migración:**
  * Nuevo formato portable **`.chemysql`** (`Abrir .chemysql` / `Guardar .chemysql`) que empaqueta Contrato Maestro, coordenadas ER/Chen/Tablas, verbos personalizados, historial de migraciones y la base `.db` embebida.
  * Guardado automático de la maquetación visual de todos los diagramas en `.schema.json`.
  * Respaldo automático pre-migración en `workspaces/backups/*.db.bak` y diálogo preventivo con recuento de filas afectadas antes de desplegar migraciones que eliminen tablas o columnas con datos.
* **Diagrama Relacional Académico Pulido (ASIR):**
  * Título del proyecto dentro del lienzo y de los archivos **SVG / PNG** exportados.
  * Algoritmo anti-colisión angular en **Conceptual (Chen)** para que los atributos no se superpongan con conectores verticales, soporte de relaciones **N-arias / ternarias ($\ge 3$ FKs)** y conmutador **`Mostrar FK Débil`** con discriminadores subrayados discontinuos.
  * Leyenda **`fx` (Calculada)** y conmutador **`Mostrar Tipos / FK`** en **Paso a Tablas** para visualizar tipos físicos y políticas `ON DELETE` sobre los arcos.
* **Vistas (`CREATE VIEW`), Lógica `NULL`, Álgebra Relacional y `GROUP BY` Guiado:**
  * Soporte completo de vistas virtuales en modelo Pydantic, SQLite, transpilador multi-dialecto, Lienzo ER, Inspector, autocompletado SQL y Explorador de Datos (solo lectura).
  * Detección en vivo de trampas con `NULL` (`= NULL`, `!= NULL`, `<> NULL` y `NOT IN (SELECT ...)` sin `IS NOT NULL`) tanto al escribir como al ejecutar.
  * Traductor determinista a **Álgebra Relacional** ($\pi, \sigma, \bowtie, \times, \gamma, \tau, \cup, \cap, -$) en Modo Tutor y Constructor Guiado ampliado con `IS NULL`, `GROUP BY`, agregaciones y `HAVING`.
* **Motor Matemático de Normalización Formal (2FN–4FN) y Desnormalización Controlada:**
  * Editor de Dependencias Funcionales (`A -> B`) y Multivaluadas (`A ->> B`) en el Inspector de Tabla con cálculo de **Claves Candidatas minimales**, evaluación automática de **2FN, 3FN, FNBC (Boyce-Codd) y 4FN**, orientaciones de **desnormalización controlada** en tablas históricas y **Calculadora en vivo de Cierre de Atributos ($X^+$)**.

## [1.6.0] - 2026-11-26

### Añadido y mejorado
* **Auditor Empresarial Avanzado:** Índice de Salud del Esquema (`0–100` y grado `A+`–`D`), filtros por categoría, botón **"Corregir Todo"** (`POST /api/schema/audit/fix-all`) y exportación de informe técnico en Markdown (`.md`).
* **Nuevas reglas deterministas (ES/EN):** detección de **2ª y 3ª Forma Normal (2FN / 3FN)**, seguridad en contraseñas cortas (`VARCHAR(255)` auto-fix), identificadores PII sin `UNIQUE`, reglas de dominio `CHECK (>= 0)`, ciclos de claves foráneas, tablas aisladas y palabras reservadas SQL.
* **Auditoría de anti-patrones en consultas SQL:** detección de `JOIN` sin `ON` (producto cartesiano), `LIKE '%texto%'`, funciones no SARGables en `WHERE` y `SELECT *` en consultas con `JOIN`.
* **Resaltado visual de línea con error en el Editor SQL:** marca la línea fallida en el margen (`● N`) y dentro del código con tarjeta estructurada de error, estado de `ROLLBACK` atómico y salto en 1 clic.

## [1.5.0] - 2026-11-26

### Añadido y corregido
* **Soporte bilingüe completo (Español / English):** selector de idioma nativo en el instalador de Windows (`Setup-ChemySQL-1.5.0.exe`), conmutador rápido `ES · EN` en la barra de estado y soporte de lenguaje natural y especificaciones estructuradas (`Table` / `Tabla`) en inglés y español en el motor Texto → Esquema.
* **Ejecución SQL atómica con `ROLLBACK` automático:** si una sentencia falla dentro de un script multi-sentencia, SQLite revierte todo el bloque (incluyendo `CREATE TABLE` previos) evitando dejar tablas a medias y errores falsos de `table already exists` al corregir y re-ejecutar.
* **Ejecutar selección sombreada:** sombrear una sentencia y pulsar `Ejecutar SQL` (`Ctrl+Enter`) ejecuta únicamente el fragmento seleccionado.
* **Inspector profesional ampliado y Pre-Análisis SQL en vivo:** propiedades globales de proyecto (`COLLATE`), Inspector de Tabla enriquecido (`Ver Datos`, `Copiar CREATE TABLE`, lista clicable de columnas), Inspector de Columna completo (`DEFAULT`, `CHECK`, `GENERATED ALWAYS AS`, PK compuestas, `INDEX`) y detección de sintaxis en tiempo real con salto directo a la línea exacta.
* **Diagnóstico detallado de errores SQL en el Inspector:** muestra la línea exacta del error, estado de `ROLLBACK`, causa probable, fragmento fallido y un botón **"Ir a la línea en el editor"**.
* **Corrección visual del panel izquierdo:** eliminado el desbordamiento horizontal de los botones `Cambiar Carpeta` y `Abrir .db` en paneles estrechos.

## [1.4.2] - 2026-11-25

### Añadido y mejorado
* **Autocompletado inline de línea completa (*Ghost Text*):** sugerencias deterministas contextuales basadas en el esquema activo y el script actual aceptables con `Tab` o `→`.
* **Menú de sugerencias sin recortes:** posicionamiento `fixed` en el viewport con volteo automático por encima de la línea activa cuando se escribe cerca del borde inferior.
* **Editor SQL más amplio y ergonómico:** línea activa centrada automáticamente con espacio libre inferior (*scroll beyond last line*), panel de Resultados compacto por defecto y divisor horizontal redimensionable.
* **Barra de Inferencia Sintáctica desplegable:** arranca plegada para maximizar el espacio de trabajo y se abre/pliega en un clic desde `Texto a Esquema` o `Plegar`.

## [1.4.1] - 2026-11-25

### Cambiado
* Rebranding completo del proyecto a **ChemySQL** (código, interfaz, emblema hexagonal molecular, icono multi-resolución, instalador Windows `Setup-ChemySQL-1.4.1.exe`, workflows de CI/Release y documentación).

## [1.4.0] - 2026-11-24

### Añadido
* Identidad completa **ChemySQL** con icono oficial multi-resolución (`16px`–`256px`) y barra de estado inferior tipo IDE.
* Sistema visual dual de nivel empresarial (**Tema Oscuro Grafito** y **Tema Claro Laboratorio**) con conmutador Sol/Luna y persistencia en `localStorage`.
* Soporte completo de **Claves Primarias Compuestas** en el Explorador de Datos (`UPDATE` / `DELETE` seguro por todas las columnas PK).
* **Migraciones SQLite reales** con reconstrucción transaccional de tabla preservando datos al modificar o eliminar columnas y políticas `ON DELETE`.
* **Paginación real** en resultados SQL y **exportación** de tablas/resultados a **CSV, JSON y SQL (`INSERT`)**.
* **Deshacer/Rehacer (Undo/Redo)** sobre el Contrato Maestro JSON (`Ctrl+Z` / `Ctrl+Y`) y modularización ES nativa del frontend (`frontend/modules/`).
* Escudo Anti-Desastres extendido a CTEs (`WITH ... DELETE/UPDATE`) y condiciones `OR 1=1`; soporte de `RIGHT`, `FULL OUTER` y `CROSS JOIN` en el Modo Tutor.
* Suite de pruebas automatizadas (`tests/test_chemysql.py`) y flujo CI de GitHub Actions.
* Arranque limpio 100 % en blanco sin bases de datos demo pre-cargadas.

### Seguridad y correcciones
* Restricción estricta de CORS a orígenes locales (`127.0.0.1` / `localhost`) y protección contra escritura arbitraria de archivos en `/api/files/save-sql`.
* Escapado seguro de identificadores SQL multi-dialecto (`quote_identifier`) en toda la capa de base de datos y transpilador.
* Introspección SQLite mejorada leyendo `sqlite_master.sql` para conservar `CHECK`, columnas `GENERATED ALWAYS AS` y longitudes `VARCHAR(n)`/`CHAR(n)`.
