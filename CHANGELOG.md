# Changelog

Todos los cambios relevantes de **ChemySQL** se documentan en este archivo.

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
