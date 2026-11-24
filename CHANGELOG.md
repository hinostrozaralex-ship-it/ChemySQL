# Changelog

Todos los cambios relevantes de **VarSQL** se documentan en este archivo.

## [1.4.0] - 2026-11-24

### Añadido
* Identidad completa **VarSQL** con icono oficial multi-resolución (`16px`–`256px`) y barra de estado inferior tipo IDE.
* Sistema visual dual de nivel empresarial (**Tema Oscuro VOR** y **Tema Claro Laboratorio**) con conmutador Sol/Luna y persistencia en `localStorage`.
* Soporte completo de **Claves Primarias Compuestas** en el Explorador de Datos (`UPDATE` / `DELETE` seguro por todas las columnas PK).
* **Migraciones SQLite reales** con reconstrucción transaccional de tabla preservando datos al modificar o eliminar columnas y políticas `ON DELETE`.
* **Paginación real** en resultados SQL y **exportación** de tablas/resultados a **CSV, JSON y SQL (`INSERT`)**.
* **Deshacer/Rehacer (Undo/Redo)** sobre el Contrato Maestro JSON (`Ctrl+Z` / `Ctrl+Y`) y modularización ES nativa del frontend (`frontend/modules/`).
* Escudo Anti-Desastres extendido a CTEs (`WITH ... DELETE/UPDATE`) y condiciones `OR 1=1`; soporte de `RIGHT`, `FULL OUTER` y `CROSS JOIN` en el Modo Tutor.
* Suite de pruebas automatizadas (`tests/test_varsql.py`) y flujo CI de GitHub Actions.
* Arranque limpio 100 % en blanco sin bases de datos demo pre-cargadas.

### Seguridad y correcciones
* Restricción estricta de CORS a orígenes locales (`127.0.0.1` / `localhost`) y protección contra escritura arbitraria de archivos en `/api/files/save-sql`.
* Escapado seguro de identificadores SQL multi-dialecto (`quote_identifier`) en toda la capa de base de datos y transpilador.
* Introspección SQLite mejorada leyendo `sqlite_master.sql` para conservar `CHECK`, columnas `GENERATED ALWAYS AS` y longitudes `VARCHAR(n)`/`CHAR(n)`.
