<p align="center">
  <img src="frontend/chemysql_logo.png" alt="ChemySQL Logo" width="96" height="96" />
</p>

<h1 align="center">ChemySQL</h1>

<p align="center">
  <strong>Estudio Relacional Auditado, Visual y Didáctico para Bases de Datos SQL</strong><br />
  <em>Tu laboratorio relacional de alta precisión: diseña, sintetiza y audita cada esquema y consulta antes de tocar el disco.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-Local%20Engine-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/SQLite-3-003B57?style=flat-square&logo=sqlite&logoColor=white" alt="SQLite" />
  <img src="https://img.shields.io/badge/License-MIT-10b981?style=flat-square" alt="MIT License" />
</p>

---

## ¿Qué es ChemySQL?

**ChemySQL** es una aplicación de escritorio open-source, ligera y **100 % determinista (offline, sin APIs externas ni alucinaciones)** para diseñar, auditar, desplegar, explorar y consultar bases de datos relacionales SQL.

Combina el rigor de un motor SQL real (SQLite local) con un **auditor relacional proactivo** que detecta errores de modelado y bloquea sentencias destructivas antes de que causen pérdida de datos.

## Características principales

* **Motor Determinista Texto → Esquema (Español / English, barra desplegable):** transforma descripciones en español o inglés (texto libre o especificaciones técnicas estructuradas `Tabla` / `Table`) en un *Contrato Maestro JSON* con entidades, tipos semánticos (`DECIMAL(10,2)`, `DATE`, `BOOLEAN`, `VARCHAR UNIQUE`), claves primarias simples/compuestas, columnas calculadas y relaciones `1:1`, `1:N` y `N:M`.
* **Lienzo ER Interactivo + Vistas + Undo/Redo (`Ctrl+Z` / `Ctrl+Y`):** arrastre de nodos con persistencia automática de maquetación, edición inline, creación de **Vistas Virtuales (`CREATE VIEW`)**, vinculación visual de claves foráneas y confirmación *Human-in-the-Loop* antes de materializar en disco.
* **Diagrama Relacional Académico:** notación **Conceptual (Chen)** (entidades simples y débiles con discriminadores, rombos editables binarios/reflexivos/N-arios $\ge 3$ FKs, óvalos con distribución anti-colisión angular y opción `Mostrar FK Débil`) y **Paso a Tablas (Claves)** (`pk`, `nn`, `uk`, `fk`, `fx`, modo extendido `Mostrar Tipos / FK`), con cabecera de esquema y exportación vectorial **SVG** y **PNG** en alta resolución.
* **Proyecto Portable (`.chemysql`) y Migraciones Protegidas:** exportación e importación de paquetes **`.chemysql`** (esquema, maquetación completa, historial y `.db` embebido) separados de copias físicas `.db` y scripts `.sql`; **Escudo Pre-Migración** con copias automáticas `.db.bak` en `workspaces/backups/` antes de reconstruir o eliminar tablas/columnas con datos.
* **Inspector Profesional + Pre-Análisis SQL + Normalización Matemática (2FN–4FN):** edición de Proyecto (`COLLATE`), Tablas, Vistas, Columnas (`DEFAULT`, `CHECK`, `GENERATED ALWAYS AS`, PK compuestas, `INDEX`) y Relaciones; editor de **Dependencias Funcionales (`A -> B`) y Multivaluadas (`A ->> B`)** con cálculo de **Claves Candidatas**, evaluación **2FN/3FN/BCNF/4FN** y **Calculadora de Cierre de Atributos ($X^+$)**; pre-análisis en vivo con detección de trampas **`NULL`** (`= NULL`, `NOT IN`) y salto directo a la línea exacta.
* **Auditor Empresarial Avanzado (Score `0–100` + Escudo Anti-Desastres):**
  * Calcula el **Índice de Salud del Esquema** (`0–100`, grado `A+` a `D`) con filtros por categoría, botón **"Corregir Todo"** en 1 clic y **exportación de informe técnico en Markdown (`.md`)**.
  * Detecta PK faltantes, **1FN, 2FN, 3FN, BCNF y 4FN**, criterio de **desnormalización controlada** en tablas históricas, tipos semánticos (`FLOAT` en dinero, `TEXT` en fechas), seguridad (**contraseñas cortas**, PII sin `UNIQUE`), reglas `CHECK (>= 0)`, **ciclos FK**, tablas aisladas, palabras reservadas SQL y `ON DELETE CASCADE` peligroso.
  * Analiza **anti-patrones en consultas SQL** (`JOIN` sin `ON`, `LIKE '%texto%'`, filtros no SARGables, `= NULL` / `NOT IN` y `SELECT *` con `JOIN`) e intercepta `UPDATE`/`DELETE` sin `WHERE` (incluyendo CTE `WITH`) y `DROP TABLE`.
* **Ejecución SQL Atómica (`ROLLBACK`) y Exportación Topológica:** si una sentencia falla en un script multi-sentencia, SQLite revierte todo el bloque para no dejar tablas a medias; soporta **ejecutar solo el texto seleccionado**, evolución con preservación de datos (`RENAME → CREATE → INSERT SELECT → DROP`) y exportación **`Exportar BD + Datos (.sql)`** (`DDL + INSERT` en orden topológico).
* **Explorador de Datos Relacional:** cuadrícula paginada editable para tablas y de solo lectura para vistas, con soporte de **PK compuestas**, previsualización flotante de registros padre en celdas `FK`, estilos `NULL` y exportación a **CSV, JSON y SQL (`INSERT` / `CREATE VIEW`)**.
* **Editor SQL Dual Multi-Dialecto:** sincronización bidireccional **DDL ↔ Lienzo ER** con selector **`IF NOT EXISTS: OFF / ON`** y lectura de `CREATE DATABASE` / `COLLATE`; transpilación fiel a **SQLite, MySQL, PostgreSQL y SQL Server** (incluyendo prevención de múltiples rutas de cascada T-SQL), **autocompletado inline (*Ghost Text* con `Tab`/`→`)**, resaltado de línea con error (`● N`), consultas DML paginadas y análisis `EXPLAIN QUERY PLAN` con creación de índices en 1 clic.
* **Modo Tutor vs. Modo Estándar:** tarjetas pedagógicas vivas sobre tu esquema, **equivalencia automática en Álgebra Relacional ($\pi, \sigma, \bowtie, \times, \gamma, \tau, \cup, \cap, -$)**, desglosador paso a paso del orden lógico SQL, Constructor Guiado con `GROUP BY` / `HAVING`, visualizador de conjuntos `INNER` / `LEFT` / `RIGHT` / `FULL` / `CROSS JOIN` y retos guiados.
* **Interfaz Dual y Bilingüe (`ES · EN`):** **Tema Oscuro (Grafito)** y **Tema Claro (Laboratorio)**, selector de idioma nativo en el instalador de Windows y conmutador en vivo `ES · EN` en la barra de estado.

---

## Estructura del proyecto

```text
ChemySQL/
├── assets/                 # Icono multi-resolución oficial (chemysql.ico)
├── backend/
│   ├── api/                # Endpoints REST (FastAPI + validación Pydantic)
│   └── core/               # Motor determinista (NLP, Auditor, Transpilador, SQLite, Tutor)
├── docs/                   # Especificación de producto (PRODUCT.md) y diseño (DESIGN.md)
├── frontend/               # Interfaz modular (HTML5, CSS3, ES Modules, SVG)
│   └── modules/            # Core, i18n (ES/EN), Inspector profesional, Undo/Redo y exportación
├── installer/              # Script de instalador Windows (Inno Setup 6: ChemySQL.iss)
├── tests/                  # Suite de pruebas automatizadas (unittest / pytest)
├── workspaces/             # Carpeta local de bases de datos .db (ignorada en Git)
├── run.py                  # Punto de entrada unificado (escritorio nativo + --web)
├── ChemySQL.spec             # Configuración de compilación PyInstaller
└── requirements.txt        # Dependencias Python
```

---

## Descargar e instalar (Windows)

Descarga el instalador oficial de Windows desde **GitHub Releases** o directamente desde [`installer_output/Setup-ChemySQL-1.7.0.exe`](installer_output/Setup-ChemySQL-1.7.0.exe) (no requiere Python instalado):

<p>
  <a href="https://github.com/hinostrozaralex-ship-it/ChemySQL/releases/download/v1.7.0/Setup-ChemySQL-1.7.0.exe">
    <img src="https://img.shields.io/badge/Descargar%20ChemySQL%20v1.7.0-Windows%20(.exe)-10b981?style=for-the-badge&logo=windows&logoColor=white" alt="Descargar ChemySQL para Windows" />
  </a>
</p>

1. Haz clic en el botón superior para descargar **`Setup-ChemySQL-1.7.0.exe`** (o visita la página de [Releases](https://github.com/hinostrozaralex-ship-it/ChemySQL/releases/latest)).
2. Ejecuta el instalador, elige tu idioma (**Español / English**) y sigue el asistente.
3. Abre **ChemySQL** desde el menú Inicio o el acceso directo del escritorio.

---

## Instalación y uso desde código fuente

### 1. Clonar e instalar dependencias

```bash
git clone https://github.com/hinostrozaralex-ship-it/ChemySQL.git
cd ChemySQL
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Ejecutar la aplicación

```bash
# Modo aplicación de escritorio nativa (Windows WebView2)
python run.py

# Modo servidor web local opcional
python run.py --web
```

### 3. Ejecutar los tests automatizados

```bash
python -m unittest discover -s tests -v
```

---

## Compilar ejecutable e instalador de Windows

```bash
# 1. Generar ejecutable nativo en dist/ChemySQL/ChemySQL.exe
python -m PyInstaller --noconfirm --clean ChemySQL.spec

# 2. (Opcional) Generar instalador único bilingüe Setup-ChemySQL-1.7.0.exe con Inno Setup 6
iscc installer\ChemySQL.iss
```

---

## Documentación y contribuciones

* [Especificación de Producto](docs/PRODUCT.md)
* [Sistema de Diseño](docs/DESIGN.md)
* [Guía de Contribución](CONTRIBUTING.md)
* [Historial de Cambios](CHANGELOG.md)

## Licencia

Distribuido bajo licencia **MIT**. Consulta el archivo [LICENSE](LICENSE) para más información.
