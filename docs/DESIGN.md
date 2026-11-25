---
name: ChemySQL
description: Estudio cartográfico de ingeniería y planos técnicos para modelado relacional determinista, auditoría SQL y aprendizaje guiado.
colors:
  blueprint-canvas: "#090e18"
  slate-surface: "#0e1624"
  slate-elevated: "#141f33"
  slate-hover: "#1b2942"
  slate-active: "#213251"
  alabaster-canvas: "#eef3f9"
  paper-surface: "#ffffff"
  ink-primary: "#f0f6fc"
  ink-secondary: "#b8cae3"
  ink-muted: "#93accf"
  border-subtle: "#1e2d47"
  border-strong: "#2d4266"
  structural-cyan: "#38bdf8"
  structural-cyan-strong: "#0369a1"
  relational-indigo: "#a5b4fc"
  verified-emerald: "#34d399"
  verified-emerald-solid: "#047857"
  auditor-amber: "#fbbf24"
  shield-crimson: "#fb7185"
  shield-crimson-solid: "#be123c"
typography:
  headline:
    fontFamily: "\"Segoe UI Variable Text\", \"Segoe UI\", -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  title:
    fontFamily: "\"Segoe UI Variable Text\", \"Segoe UI\", -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 1.35
  body:
    fontFamily: "\"Segoe UI Variable Text\", \"Segoe UI\", -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "\"Cascadia Mono\", \"Consolas\", \"Liberation Mono\", monospace"
    fontSize: "12.5px"
    fontWeight: 600
    lineHeight: 1.4
rounded:
  sm: "4px"
  md: "6px"
  lg: "8px"
  pill: "999px"
spacing:
  xs: "6px"
  sm: "10px"
  md: "14px"
  lg: "18px"
components:
  button-primary:
    backgroundColor: "{colors.structural-cyan-strong}"
    textColor: "{colors.paper-surface}"
    rounded: "{rounded.md}"
    padding: "6px 14px"
    height: "36px"
  button-accent:
    backgroundColor: "{colors.verified-emerald-solid}"
    textColor: "{colors.paper-surface}"
    rounded: "{rounded.md}"
    padding: "6px 14px"
    height: "36px"
  button-secondary:
    backgroundColor: "{colors.slate-elevated}"
    textColor: "{colors.ink-primary}"
    rounded: "{rounded.md}"
    padding: "6px 14px"
    height: "36px"
  button-danger:
    backgroundColor: "{colors.shield-crimson-solid}"
    textColor: "{colors.paper-surface}"
    rounded: "{rounded.md}"
    padding: "6px 14px"
    height: "36px"
---

# Design System: ChemySQL

## Overview

**Creative North Star: "Estudio Cartográfico de Ingeniería y Planos Técnicos"**

ChemySQL concibe el modelado, la auditoría y la operación de bases de datos relacionales como una mesa de trabajo cartográfica y de planos de ingeniería de alta precisión. En lugar de presentar tarjetas flotantes decorativas o paneles administrativos genéricos, cada región de la pantalla funciona como un instrumento calibrado conectado en tiempo real al Contrato Maestro JSON: el texto libre en español se traduce en topología Entidad-Relación sobre un plano con retícula SVG CAD, mientras el panel lateral evalúa la integridad de claves, la 1ª Forma Normal y los planes de ejecución SQL.

La densidad es deliberadamente alta y escaneable, diseñada para sesiones prolongadas tanto de desarrolladores y arquitectos de datos (**Modo Estándar**) como de estudiantes en formación (**Modo Tutor**). El sistema rechaza el ornamento gratuito, los degradados decorativos en textos, las franjas laterales gruesas en tarjetas y el uso de emojis, confiando exclusivamente en iconografía vectorial de trazo uniforme (`1.75px`–`2px`), tipografía monoespaciada tabular y señalización cromática funcional.

**Key Characteristics:**
- **Retícula Cartográfica SVG Nativa:** El lienzo Entidad-Relación dibuja su propia malla técnica de coordenadas en SVG (`#cad-blueprint-grid`) con curvas de Bézier cúbicas, puntos de anclaje y etiquetas compactas de cardinalidad y política referencial (`1:N·RESTR`, `N:M·RESTR`).
- **Señalización Cromática Semántica:** Cada acento de color tiene una única responsabilidad estructural: cian para claves primarias y foco activo, índigo para claves foráneas y enlaces relacionales, ámbar para diagnósticos del Auditor y lecciones del Modo Tutor, esmeralda para esquemas desplegados en SQLite y carmesí para el Escudo Anti-Desastres.
- **Disciplina Tabular Estricta:** Todos los tipos de datos SQL, contadores de filas, tiempos de ejecución en milisegundos, planes `EXPLAIN QUERY PLAN` y cuadrículas de datos aplican `font-variant-numeric: tabular-nums` sobre fuente monoespaciada.
- **Adaptabilidad Dual Oscuro / Claro:** Soporte nativo para entorno de ingeniería en grafito pizarra azulado (`[data-theme="dark"]`) y papel técnico alabastro de alto contraste (`[data-theme="light"]`).

## Colors

La paleta combina superficies de pizarra azulada profunda (o papel técnico alabastro en modo claro) con cinco señales cromáticas de precisión calibradas para superar el umbral de contraste WCAG AA ($\ge 4.5:1$).

### Primary
- **Structural Cyan** (`#38bdf8` en oscuro / `#0369a1` en claro) y **Structural Cyan Strong** (`#0369a1` / `#075985`): Señal principal de estructura activa, claves primarias (`PK`), pestañas seleccionadas, anillos de foco (`:focus-visible`) y acción maestra *Aprobar y Desplegar*.

### Secondary
- **Relational Indigo** (`#a5b4fc` en oscuro / `#3730a3` en claro): Identifica exclusivamente claves foráneas (`FK`), conectores de relación en el grafo ER y píldoras interactivas de previsualización de registros padre en el Explorador de Datos Relacional.
- **Verified Emerald** (`#34d399` texto / `#047857` sólido): Certifica estados desplegados en disco (`Desplegado en SQLite v1`), alternativas SQL seguras, bloques "Después" en lecciones de normalización y el botón de inferencia sintáctica (*Generar Boceto Estructural*).

### Tertiary
- **Auditor Amber** (`#fbbf24` en oscuro / `#92400e` en claro):Reservado para advertencias de normalización (1FN, tipos `FLOAT` en importes), sugerencias de índices y la capa pedagógica activa del **Modo Tutor**.
- **Shield Crimson** (`#fb7185` texto / `#be123c` sólido): Reservado para alertas críticas (tablas sin PK, `ON DELETE CASCADE` sobre tablas históricas/contables) y el bloqueo preventivo del **Escudo Anti-Desastres** (`UPDATE` / `DELETE` sin `WHERE`, `DROP TABLE`).

### Neutral
- **Blueprint Canvas** (`#090e18` oscuro / `#eef3f9` claro): Fondo base del plano cartográfico ER y áreas de código DDL.
- **Slate Surface & Elevated** (`#0e1624` y `#141f33` en oscuro / `#ffffff` y `#f5f8fc` en claro): Superficies de paneles laterales, cabeceras de instrumentación, nodos de tablas ER y tarjetas del auditor.
- **Technical Ink Hierarchy** (`#f0f6fc` primario, `#b8cae3` secundario, `#93accf` atenuado): Textos tintados desde el matiz azul pizarra del mundo visual, evitando grises neutros apagados.
- **Structural Hairlines** (`#1e2d47` sutil y `#2d4266` fuerte): Líneas divisorias de `1px` que articulan los paneles redimensionables y las celdas de la cuadrícula relacional.

### Named Rules
**The Chromatic Signal Rule.** Ningún color de acento se utiliza como decoración libre: el cian indica identidad primaria (`PK`) o selección activa, el índigo indica referencia foránea (`FK`), el ámbar indica diagnóstico o lección formativa, el esmeralda indica validación o despliegue confirmado y el carmesí indica riesgo destructivo.
**The Tinted Ink Rule.** El texto secundario y los bordes nunca usan gris puro desaturado; siempre conservan la temperatura azul pizarra del plano técnico para mantener cohesión cromática y contraste superior a `4.5:1`.

## Typography

**Display & UI Font:** `"Segoe UI Variable Text", "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif`
**Label, Schema & SQL Mono Font:** `"Cascadia Mono", "Consolas", "Liberation Mono", monospace`

**Character:** Un emparejamiento funcional de ingeniería donde la sans-serif geométrica del sistema aporta lectura inmediata en controles, explicaciones didácticas y diagnósticos, mientras la monoespaciada gobierna identificadores `snake_case`, tipos SQL (`DECIMAL(10,2)`, `VARCHAR(150)`), sentencias DDL/DML y tablas de registros.

### Hierarchy
- **Headline** (`700`, `20px`, `line-height: 1.2`, `letter-spacing: -0.02em`): Identidad principal del estudio (`ChemySQL`) en la cabecera de instrumentación.
- **Title** (`700`, `16px`, `line-height: 1.35`): Títulos de módulos principales (Motor de Inferencia Sintáctica, modal del Escudo Anti-Desastres, diálogos de relación).
- **Section Heading** (`700`, `14px`, `line-height: 1.4`): Encabezados de paneles laterales (`Bases de Datos Locales`, `Tablas del Esquema`, `Diagnóstico de Normalización, Claves y Rendimiento`).
- **Body** (`400`, `14px`, `line-height: 1.5`): Explicaciones técnicas del auditor, lecciones del Modo Tutor y descripciones funcionales.
- **Technical Label & Data Grid** (`600`–`700`, `12px`–`13px`, `font-variant-numeric: tabular-nums`): Nombres de tablas y columnas en el lienzo ER, insignias `PK`/`FK`/`UQ`/`N:M`, celdas del explorador de datos y código SQL.

### Named Rules
**The 12px Legibility Floor Rule.** Ningún texto funcional, etiqueta de cardinalidad, insignia de clave (`PK`, `FK`, `UQ`, `N:M`) o metadato de columna desciende por debajo de `12px`.
**The Direct Heading Rule.** Todo encabezado (`h1`–`h4`) habla por su propio peso tipográfico; están prohibidos los *eyebrows* o *kickers* en mayúsculas pequeñas colocados encima de los títulos.

## Layout

La interfaz se organiza como una estación de trabajo a pantalla completa (`100vh` en escritorio) dividida en tres estratos:
1. **Cabecera de Instrumentación (`min-height: 60px`, `padding: 8px 16px`):** Barra horizontal única que agrupa identidad y estado del esquema (`Desplegado en SQLite v1` vs. `Boceto en Revisión`), selector de archivo `.db`, acciones de esquema (*Texto a Esquema*, *Mock Data*, *Aprobar y Desplegar*) y el conmutador global **Modo Estándar / Modo Tutor** junto al selector de tema.
2. **Muelle Desplegable de Inferencia NLP (`padding: 12px 16px`):** Panel superior plegable con plantillas rápidas de dominio, área de texto libre en español e input de nombre de base de datos.
3. **Rejilla Tripartita Redimensionable (`calc(100vh - 172px)`):**
   - **Panel Lateral Izquierdo (`280px` por defecto, redimensionable `220px`–`450px`):** Pestañas de *Esquema* (proyectos `.db` y árbol de tablas/columnas), *Retos* (escenarios guiados con 3 pistas escalonadas) y *Versiones* (historial de migraciones `ALTER TABLE`).
   - **Área Central de Trabajo (`flex: 1`, `min-width: 0`):** Conmuta entre el *Lienzo ER* (con auto-ajuste de escala `fitToViewport()` para encuadrar todas las tablas y relaciones sin recortes), el *Explorador de Datos* y el *Editor SQL Dual*.
   - **Panel Inspector Derecho (`390px` por defecto, redimensionable `300px`–`580px`):** Pestañas de *Auditor*, *Inspector*, *DDL SQL* (SQLite, PostgreSQL, MySQL) y *Tutor*.

En pantallas compactas y dispositivos móviles (`@media (max-width: 860px)`), los divisores verticales se ocultan y los tres paneles se apilan verticalmente al `100%` del ancho disponible sin desbordamiento horizontal (`overflow-x: hidden`).

## Elevation & Depth

El sistema emplea una estrategia híbrida de **capas tonales delimitadas por bordes técnicos de `1px`** combinada con sombras direccionales suaves únicamente en elementos flotantes o nodos arrastrables sobre el plano ER.

### Shadow Vocabulary
- **Card Node Elevation** (`box-shadow: 0 6px 18px -4px rgba(3, 7, 15, 0.5)` en oscuro / `0 6px 16px -4px rgba(12, 23, 38, 0.09)` en claro): Separa las tarjetas de tablas arrastrables (`.er-table-node`) del lienzo cartográfico.
- **Popover & Modal Elevation** (`box-shadow: 0 10px 28px -6px rgba(3, 7, 15, 0.65)` en oscuro / `0 12px 30px -8px rgba(12, 23, 38, 0.16)` en claro): Aplicada a nodos seleccionados, la tarjeta flotante de previsualización de claves foráneas (`#fk-preview-popover`), notificaciones toast y el diálogo crítico del Escudo Anti-Desastres.

### Named Rules
**The Perimeter Border Rule.** Toda tarjeta, alerta del auditor o nodo de tabla define su volumen mediante un borde perimetral completo de `1px solid`; nunca se utilizan bordes laterales gruesos (`border-left: 3px/4px`) ni sombras duras sin difuminado (`4px 4px 0`).

## Shapes

La geometría del sistema refleja precisión instrumental:
- **Contenedores y Tarjetas de Tabla (`8px` radius):** Esquinas contenidas que maximizan la alineación tabular interna.
- **Botones, Inputs y Pestañas (`5px`–`6px` radius):** Geometría compacta con bordes definidos de `1px`.
- **Insignias de Restricción (`4px` radius):** Etiquetas rectangulares técnicas para `PK`, `FK`, `UQ`, `N:M` y severidades del auditor.
- **Píldoras de Estado y Plantillas (`999px` radius):** Reservadas para indicadores de estado de despliegue, contadores numéricos y botones de plantillas rápidas.

## Components

### Buttons
- **Shape:** Esquinas técnicas redondeadas (`6px` en botones estándar de `36px` de alto; `5px` en botones de barra de herramientas de `32px`).
- **Primary (`.btn-primary`):** Fondo `#0369a1` con borde `#38bdf8` y texto blanco `#ffffff` (`padding: 6px 14px`), utilizado para *Aprobar y Desplegar* y acciones de confirmación principal.
- **Accent (`.btn-accent`):** Fondo esmeralda sólido `#047857` con borde `#34d399` y texto `#ffffff`, utilizado para *Generar Boceto Estructural*.
- **Secondary (`.btn-secondary`):** Fondo elevado `#141f33` con borde `#2d4266` y texto `#f0f6fc`; cambia su borde a `#38bdf8` en `:hover`.
- **Danger (`.btn-danger`):** Fondo carmesí sólido `#be123c` con texto `#ffffff`, reservado para confirmaciones destructivas en el Escudo Anti-Desastres.

### Chips & Key Badges
- **Style:** Micro-insignias monoespaciadas (`12px`, `font-weight: 700`, `padding: 2px 6px`, `border-radius: 4px`) con fondo tintado al `12%` y borde de `1px solid` en el mismo matiz (`PK` en cian, `FK` en índigo, `UQ` en esmeralda, `N:M` en ámbar).
- **State:** En el Explorador de Datos, las celdas de clave foránea se renderizan como botones interactivos `.fk-cell-btn` (`#id -> tabla_padre`) que invierten su color al pasar el cursor y abren la tarjeta flotante del registro padre.

### Cards / Containers (`.er-table-node`, `.audit-card`, `.inspector-card`)
- **Corner Style:** `7px`–`8px` de radio con borde perimetral de `1px solid`.
- **Background:** `#0e1624` para nodos de tablas en el lienzo (con cabecera y pie en `#141f33`) y `#141f33` para tarjetas del auditor e inspector.
- **Shadow Strategy:** Los paneles laterales mantienen tarjetas planas delimitadas por borde; los nodos del lienzo ER proyectan `var(--shadow-card)`.
- **Border:** Borde perimetral completo codificado por estado (`#2d4266` reposo, `#38bdf8` seleccionado, `#fbbf24` con advertencia del auditor, `#fb7185` crítico).
- **Internal Padding:** `10px 12px` en cabeceras de nodo ER; `12px` en tarjetas del auditor e inspector.

### Inputs / Fields (`.control-input`, `.control-select`, `.nlp-textarea`, `.sql-code-textarea`)
- **Style:** Fondo `#0e1624` o `#141f33`, borde `1px solid #2d4266` y radio de `6px`.
- **Focus:** Anillo de foco exterior nítido (`outline: 2px solid #38bdf8; outline-offset: 2px`) y cursor (`caret-color: #38bdf8`).

### Navigation & Mode Switchers
- **Global Mode Switcher (`.mode-switch-group`):** Cápsula segmentada en la cabecera que alterna entre **Modo Estándar** (foco cian sobre `#213251`) y **Modo Tutor** (foco ámbar `#fbbf24` con borde de `1px`).
- **Workspace Tabs (`.panel-tab`, `.view-tab`):** Pestañas con relleno interno holgado (`6px 11px`), icono SVG alineado a `6px` y borde activo perimetral de `1px solid var(--accent-cyan)`.

### ER Diagram Canvas & Proactive Auditor Cards (Signature Components)
- **ER Diagram Canvas (`#er-canvas-viewport`):** Superficie interactiva con patrón SVG `#cad-blueprint-grid`, nodos de tabla de `236px` de ancho arrastrables en tiempo real, conectores Bézier SVG con etiquetas centrales `1:N·RESTR` / `N:M·RESTR` y ajuste automático de encuadre (`fitToViewport()`).
- **Formative Auditor Card (`.audit-card` + `.tutor-micro-lesson`):** Tarjeta de diagnóstico que combina la explicación técnica y el botón de corrección automática en un clic (*Extraer a tabla hija 1FN*, *Cambiar a DECIMAL(10,2)*, *Crear índice FK*) con un bloque pedagógico desplegable en Modo Tutor que contrasta visualmente el **Antes** (carmesí) y el **Después** (esmeralda).

## Do's and Don'ts

### Do:
- **Do** utilizar `font-variant-numeric: tabular-nums` y `--font-mono` en todas las columnas de tipos SQL, conteos de registros, tiempos en milisegundos y celdas del explorador de datos.
- **Do** mantener un contraste mínimo de `4.5:1` en todo texto funcional y botones sólidos (`#ffffff` sobre `#0369a1`, `#047857` o `#be123c`).
- **Do** encuadrar automáticamente el diagrama ER (`fitToViewport()`) al cargar o reorganizar un esquema para que todas las tablas y etiquetas de relación sean visibles sin recortes.
- **Do** acompañar cada bloqueo del Escudo Anti-Desastres con el conteo exacto de filas afectadas, las tablas hijas dependientes por clave foránea y una sentencia alternativa segura en un clic.

### Don't:
- **Don't** colocar *eyebrows* o *kickers* encima de los encabezados (`h1`–`h4`).
- **Don't** utilizar emojis o glifos Unicode como sustitutos de iconos; emplear siempre iconos SVG en línea con trazo consistente de `1.75px`–`2px`.
- **Don't** aplicar bordes laterales gruesos (`border-left` o `border-right` > `1px`) en tarjetas de alerta, ni sombras duras tipo bloque (`4px 4px 0`).
- **Don't** utilizar tamaños de fuente inferiores a `12px` en ninguna etiqueta, insignia o celda de la interfaz.
