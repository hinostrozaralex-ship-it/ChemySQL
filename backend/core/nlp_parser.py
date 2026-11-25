"""
Motor Determinista de Inferencia Sintáctica y Heurística en Español (Texto -> Contrato Maestro JSON).
Transforma descripciones en lenguaje natural en español en un modelo relacional completo
con entidades, atributos tipados semánticamente, claves primarias subrogadas y relaciones 1:1, 1:N y N:M.
"""

from __future__ import annotations
import re
import unicodedata
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from backend.core.schema_model import (
    ColumnModel,
    MasterSchemaContract,
    RelationModel,
    TableModel,
)


def strip_accents(text: str) -> str:
    """Elimina tildes conservando la eñe o normalizando a ASCII limpio para identificadores."""
    text = text.replace("ñ", "n").replace("Ñ", "N")
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def to_snake_case(text: str) -> str:
    clean = strip_accents(text.lower().strip())
    clean = re.sub(r"[^a-z0-9]+", "_", clean)
    return re.sub(r"_+", "_", clean).strip("_")


def to_singular(word: str) -> str:
    """Convierte un sustantivo plural en español (snake_case) a su forma singular."""
    w = to_snake_case(word)
    irregulars = {
        "clientes": "cliente",
        "vehiculos": "vehiculo",
        "reparaciones": "reparacion",
        "piezas": "pieza",
        "facturas": "factura",
        "pagos": "pago",
        "pedidos": "pedido",
        "productos": "producto",
        "categorias": "categoria",
        "usuarios": "usuario",
        "libros": "libro",
        "autores": "autor",
        "prestamos": "prestamo",
        "socios": "socio",
        "ejemplares": "ejemplar",
        "pacientes": "paciente",
        "medicos": "medico",
        "citas": "cita",
        "consultas": "consulta",
        "recetas": "receta",
        "medicamentos": "medicamento",
        "estudiantes": "estudiante",
        "alumnos": "alumno",
        "profesores": "profesor",
        "cursos": "curso",
        "asignaturas": "asignatura",
        "matriculas": "matricula",
        "habitaciones": "habitacion",
        "reservas": "reserva",
        "huespedes": "huesped",
        "empleados": "empleado",
        "departamentos": "departamento",
        "proyectos": "proyecto",
        "tareas": "tarea",
        "proveedores": "proveedor",
        "almacenes": "almacen",
        "movimientos": "movimiento",
        "ventas": "venta",
        "compras": "compra",
        "envios": "envio",
        "direcciones": "direccion",
        "telefonos": "telefono",
        "historiales": "historial",
    }
    if w in irregulars:
        return irregulars[w]
    if w.endswith("ciones"):
        return w[:-6] + "cion"
    if w.endswith("siones"):
        return w[:-6] + "sion"
    if w.endswith("ces"):
        return w[:-3] + "z"
    if w.endswith("res") or w.endswith("les") or w.endswith("nes") or w.endswith("des"):
        return w[:-2]
    if w.endswith("s") and len(w) > 3:
        return w[:-1]
    return w


def to_plural(word: str) -> str:
    """Convierte un sustantivo singular en español (snake_case) a plural coherente."""
    w = to_snake_case(word)
    singular_to_plural = {
        "cliente": "clientes",
        "vehiculo": "vehiculos",
        "coche": "vehiculos",
        "auto": "vehiculos",
        "automovil": "vehiculos",
        "reparacion": "reparaciones",
        "pieza": "piezas",
        "repuesto": "piezas",
        "recambio": "piezas",
        "factura": "facturas",
        "pago": "pagos",
        "pedido": "pedidos",
        "producto": "productos",
        "articulo": "productos",
        "categoria": "categorias",
        "usuario": "usuarios",
        "libro": "libros",
        "autor": "autores",
        "prestamo": "prestamos",
        "socio": "socios",
        "lector": "socios",
        "ejemplar": "ejemplares",
        "paciente": "pacientes",
        "medico": "medicos",
        "doctor": "medicos",
        "cita": "citas",
        "consulta": "consultas",
        "receta": "recetas",
        "medicamento": "medicamentos",
        "estudiante": "estudiantes",
        "alumno": "estudiantes",
        "profesor": "profesores",
        "docente": "profesores",
        "curso": "cursos",
        "asignatura": "asignaturas",
        "materia": "asignaturas",
        "matricula": "matriculas",
        "inscripcion": "matriculas",
        "habitacion": "habitaciones",
        "reserva": "reservas",
        "huesped": "huespedes",
        "empleado": "empleados",
        "trabajador": "empleados",
        "departamento": "departamentos",
        "proyecto": "proyectos",
        "tarea": "tareas",
        "proveedor": "proveedores",
        "almacen": "almacenes",
        "movimiento": "movimientos",
        "venta": "ventas",
        "compra": "compras",
        "envio": "envios",
        "direccion": "direcciones",
        "telefono": "telefonos",
        "historial": "historiales",
    }
    if w in singular_to_plural:
        return singular_to_plural[w]
    if w in singular_to_plural.values():
        return w
    if w.endswith(("a", "e", "i", "o", "u")):
        return w + "s"
    if w.endswith("z"):
        return w[:-1] + "ces"
    if not w.endswith("s"):
        return w + "es"
    return w


# Catálogo heurístico de entidades conocidas con sus columnas base por defecto
ENTITY_DEFAULT_COLUMNS: Dict[str, List[Tuple[str, str]]] = {
    "clientes": [
        ("nombre", "Nombre completo o razón social del cliente"),
        ("dni", "Documento nacional de identidad único"),
        ("email", "Correo electrónico de contacto"),
        ("telefono", "Teléfono principal de contacto"),
        ("fecha_registro", "Fecha de alta en el sistema"),
        ("activo", "Indica si el cliente sigue activo"),
    ],
    "vehiculos": [
        ("matricula", "Matrícula o placa única del vehículo"),
        ("marca", "Fabricante del vehículo"),
        ("modelo", "Modelo comercial del vehículo"),
        ("anio", "Año de fabricación"),
        ("kilometraje", "Kilómetros registrados al ingreso"),
    ],
    "reparaciones": [
        ("codigo", "Código único de orden de reparación"),
        ("fecha_ingreso", "Fecha de entrada al taller"),
        ("diagnostico", "Descripción técnica de la avería y trabajos"),
        ("coste_mano_obra", "Importe de mano de obra"),
        ("total", "Importe total de la reparación"),
        ("completado", "Estado de finalización de la reparación"),
    ],
    "piezas": [
        ("codigo", "Referencia o SKU único del recambio"),
        ("nombre", "Nombre comercial de la pieza"),
        ("descripcion", "Especificaciones técnicas de la pieza"),
        ("precio", "Precio unitario de venta"),
        ("stock", "Unidades disponibles en inventario"),
        ("disponible", "Indica si la pieza está en catálogo activo"),
    ],
    "facturas": [
        ("codigo", "Número correlativo único de factura"),
        ("fecha_emision", "Fecha de emisión contable"),
        ("subtotal", "Base imponible antes de impuestos"),
        ("total", "Importe total facturado"),
        ("pagado", "Indica si la factura ha sido abonada"),
    ],
    "pagos": [
        ("fecha_pago", "Fecha y hora de la transacción"),
        ("importe", "Monto abonado"),
        ("metodo_pago", "Medio utilizado (Tarjeta, Transferencia, Efectivo)"),
        ("referencia", "Código de autorización bancaria"),
    ],
    "libros": [
        ("isbn", "Código internacional único ISBN"),
        ("titulo", "Título completo de la obra"),
        ("editorial", "Casa editorial de publicación"),
        ("anio_publicacion", "Año de edición"),
        ("stock", "Ejemplares disponibles en sala"),
        ("disponible", "Disponibilidad para préstamo"),
    ],
    "autores": [
        ("nombre", "Nombre completo del autor"),
        ("nacionalidad", "País de origen"),
        ("fecha_nacimiento", "Fecha de nacimiento"),
        ("biografia", "Reseña biográfica del autor"),
    ],
    "socios": [
        ("codigo", "Número de carné de biblioteca"),
        ("nombre", "Nombre y apellidos del lector"),
        ("email", "Correo electrónico del socio"),
        ("telefono", "Teléfono de contacto"),
        ("fecha_registro", "Fecha de inscripción"),
        ("activo", "Estado del carné de socio"),
    ],
    "prestamos": [
        ("fecha_prestamo", "Fecha de retirada del ejemplar"),
        ("fecha_vencimiento", "Fecha límite de devolución"),
        ("devuelto", "Indica si el libro ya fue devuelto"),
        ("observaciones", "Notas sobre el estado del ejemplar"),
    ],
    "productos": [
        ("codigo", "Código SKU del producto"),
        ("nombre", "Denominación comercial"),
        ("descripcion", "Ficha técnica del artículo"),
        ("precio", "Precio unitario de venta"),
        ("stock", "Existencias actuales en almacén"),
        ("activo", "Visible en catálogo"),
    ],
    "categorias": [
        ("nombre", "Nombre de la familia o categoría"),
        ("descripcion", "Descripción del grupo de artículos"),
    ],
    "pedidos": [
        ("codigo", "Número único de pedido"),
        ("fecha_pedido", "Fecha y hora de creación"),
        ("total", "Importe total de la orden"),
        ("estado", "Estado logístico del pedido"),
        ("pagado", "Confirmación de pago"),
    ],
    "proveedores": [
        ("nif", "Identificador fiscal de la empresa proveedora"),
        ("nombre", "Razón social del proveedor"),
        ("email", "Correo de pedidos comerciales"),
        ("telefono", "Teléfono de contacto"),
        ("ciudad", "Ciudad sede del proveedor"),
    ],
    "pacientes": [
        ("dni", "Documento de identidad del paciente"),
        ("nombre", "Nombre completo del paciente"),
        ("fecha_nacimiento", "Fecha de nacimiento"),
        ("email", "Correo electrónico"),
        ("telefono", "Teléfono de contacto"),
    ],
    "medicos": [
        ("codigo", "Número de colegiado médico"),
        ("nombre", "Nombre y apellidos del facultativo"),
        ("especialidad", "Especialidad clínica"),
        ("email", "Correo institucional"),
    ],
    "citas": [
        ("fecha_hora", "Fecha y hora programada de la consulta"),
        ("motivo", "Descripción del motivo de consulta"),
        ("diagnostico", "Observaciones clínicas y pauta"),
        ("coste", "Importe de la consulta"),
        ("completado", "Indica si la cita fue atendida"),
    ],
    "estudiantes": [
        ("dni", "Documento identificativo del estudiante"),
        ("nombre", "Nombre y apellidos"),
        ("email", "Correo académico"),
        ("fecha_nacimiento", "Fecha de nacimiento"),
        ("activo", "Matrícula activa"),
    ],
    "profesores": [
        ("dni", "Documento de identidad del docente"),
        ("nombre", "Nombre completo del profesor"),
        ("departamento_academico", "Área docente"),
        ("email", "Correo institucional"),
        ("salario", "Remuneración mensual bruta"),
    ],
    "cursos": [
        ("codigo", "Código académico del curso"),
        ("titulo", "Nombre de la materia o curso"),
        ("descripcion", "Programa y objetivos formativos"),
        ("creditos", "Número de créditos ECTS"),
        ("precio", "Importe de matrícula del curso"),
    ],
    "asignaturas": [
        ("codigo", "Código de asignatura"),
        ("nombre", "Denominación de la asignatura"),
        ("horas", "Carga lectiva en horas"),
        ("descripcion", "Temario de la asignatura"),
    ],
    "matriculas": [
        ("fecha_registro", "Fecha de formalización"),
        ("importe", "Coste de inscripción"),
        ("calificacion", "Nota final obtenida"),
        ("pagado", "Estado de abono de tasas"),
    ],
    "habitaciones": [
        ("codigo", "Número o código de habitación"),
        ("tipo", "Categoría (Individual, Doble, Suite)"),
        ("capacidad", "Número máximo de plazas"),
        ("precio", "Tarifa por noche"),
        ("disponible", "Estado operativo actual"),
    ],
    "reservas": [
        ("codigo", "Localizador único de reserva"),
        ("fecha_inicio", "Fecha de check-in"),
        ("fecha_fin", "Fecha de check-out"),
        ("total", "Importe total de la estancia"),
        ("confirmado", "Indica si la reserva está garantizada"),
    ],
    "huespedes": [
        ("dni", "Pasaporte o documento de identidad"),
        ("nombre", "Nombre completo del huésped"),
        ("email", "Correo electrónico"),
        ("telefono", "Teléfono móvil"),
    ],
    "empleados": [
        ("dni", "Documento nacional de identidad"),
        ("nombre", "Nombre y apellidos del trabajador"),
        ("cargo", "Puesto desempeñado"),
        ("email", "Correo corporativo"),
        ("salario", "Salario bruto mensual"),
        ("fecha_ingreso", "Fecha de contratación"),
        ("activo", "En plantilla activa"),
    ],
    "departamentos": [
        ("codigo", "Código interno del departamento"),
        ("nombre", "Nombre de la división o área"),
        ("presupuesto", "Dotación presupuestaria anual"),
    ],
    "proyectos": [
        ("codigo", "Código de proyecto"),
        ("nombre", "Título del proyecto"),
        ("descripcion", "Alcance y entregables"),
        ("fecha_inicio", "Fecha de arranque"),
        ("presupuesto", "Presupuesto asignado"),
        ("activo", "Estado de ejecución"),
    ],
    "tareas": [
        ("titulo", "Resumen de la tarea"),
        ("descripcion", "Detalle técnico de la actividad"),
        ("fecha_vencimiento", "Fecha límite de entrega"),
        ("horas", "Horas estimadas de esfuerzo"),
        ("completado", "Indica si la tarea finalizó"),
    ],
    "usuarios": [
        ("username", "Nombre de usuario único"),
        ("nombre", "Nombre completo"),
        ("email", "Correo electrónico verificado"),
        ("fecha_registro", "Fecha y hora de alta"),
        ("activo", "Cuenta habilitada"),
    ],
    "ventas": [
        ("codigo", "Número de ticket o operación"),
        ("fecha_venta", "Fecha y hora de la operación"),
        ("total", "Importe total cobrado"),
        ("pagado", "Confirmación de cobro"),
    ],
    "movimientos": [
        ("fecha_registro", "Marca temporal del movimiento"),
        ("tipo_movimiento", "Entrada, salida o ajuste"),
        ("cantidad", "Unidades afectadas"),
        ("importe", "Valor económico asociado"),
        ("observaciones", "Justificación del movimiento"),
    ],
}

HISTORICAL_KEYWORDS = {
    "factura",
    "facturas",
    "pago",
    "pagos",
    "pedido",
    "pedidos",
    "venta",
    "ventas",
    "movimiento",
    "movimientos",
    "historial",
    "historiales",
    "reparacion",
    "reparaciones",
    "prestamo",
    "prestamos",
    "matricula",
    "matriculas",
    "cita",
    "citas",
    "reserva",
    "reservas",
}

# Relaciones canónicas de dominio cuando las dos entidades aparecen en el texto
CANONICAL_DOMAIN_RELATIONS: List[Tuple[str, str, str, str]] = [
    # (parent_or_left, child_or_right, cardinality, verb_hint)
    ("clientes", "vehiculos", "1:N", "Un cliente puede registrar varios vehículos"),
    ("vehiculos", "reparaciones", "1:N", "Un vehículo acumula múltiples órdenes de reparación"),
    ("reparaciones", "piezas", "N:M", "En cada reparación se emplean distintas piezas y cada pieza sirve en varias reparaciones"),
    ("clientes", "facturas", "1:N", "Un cliente recibe múltiples facturas"),
    ("reparaciones", "facturas", "1:N", "Una reparación puede generar facturación asociada"),
    ("facturas", "pagos", "1:N", "Una factura puede liquidarse mediante uno o varios pagos"),
    ("clientes", "pedidos", "1:N", "Un cliente realiza múltiples pedidos"),
    ("pedidos", "productos", "N:M", "Un pedido incluye varios productos y un producto figura en múltiples pedidos"),
    ("categorias", "productos", "1:N", "Una categoría clasifica múltiples productos"),
    ("proveedores", "productos", "1:N", "Un proveedor suministra varios productos"),
    ("proveedores", "piezas", "1:N", "Un proveedor distribuye distintas piezas de recambio"),
    ("autores", "libros", "N:M", "Un autor escribe varios libros y una obra puede tener coautores"),
    ("socios", "prestamos", "1:N", "Un socio realiza múltiples préstamos a lo largo del tiempo"),
    ("libros", "prestamos", "1:N", "Un libro se presta en distintas ocasiones"),
    ("usuarios", "prestamos", "1:N", "Un usuario solicita múltiples préstamos"),
    ("pacientes", "citas", "1:N", "Un paciente agenda diversas citas médicas"),
    ("medicos", "citas", "1:N", "Un médico atiende múltiples citas en su agenda"),
    ("profesores", "cursos", "1:N", "Un profesor imparte uno o varios cursos"),
    ("profesores", "asignaturas", "1:N", "Un profesor imparte distintas asignaturas"),
    ("estudiantes", "cursos", "N:M", "Los estudiantes se inscriben en múltiples cursos"),
    ("estudiantes", "asignaturas", "N:M", "Los estudiantes cursan diversas asignaturas"),
    ("estudiantes", "matriculas", "1:N", "Un estudiante formaliza varias matrículas"),
    ("cursos", "matriculas", "1:N", "Un curso registra múltiples matrículas"),
    ("huespedes", "reservas", "1:N", "Un huésped efectúa varias reservas"),
    ("clientes", "reservas", "1:N", "Un cliente realiza distintas reservas"),
    ("habitaciones", "reservas", "1:N", "Una habitación se asigna a múltiples reservas en distintas fechas"),
    ("departamentos", "empleados", "1:N", "Un departamento agrupa a varios empleados"),
    ("empleados", "proyectos", "N:M", "Varios empleados colaboran en distintos proyectos"),
    ("proyectos", "tareas", "1:N", "Un proyecto se desglosa en múltiples tareas"),
    ("empleados", "tareas", "1:N", "Un empleado tiene asignadas varias tareas"),
    ("clientes", "ventas", "1:N", "Un cliente protagoniza diversas ventas"),
    ("productos", "movimientos", "1:N", "Un producto registra múltiples movimientos de inventario"),
]


def infer_column_type(col_name: str) -> Dict[str, object]:
    """
    Diccionario semántico determinista que deduce el tipo SQL óptimo, longitud,
    unicidad, nulabilidad, valor por defecto y explicación didáctica según el nombre del atributo.
    """
    c = to_snake_case(col_name)

    # 1. Dinero / importes -> DECIMAL(10,2)
    money_tokens = (
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
        "comision",
    )
    if any(tok in c for tok in money_tokens):
        return {
            "data_type": "DECIMAL(10,2)",
            "length": None,
            "nullable": False,
            "default_value": "0.00",
            "is_unique": False,
            "tutor_explanation": (
                f"El atributo '{c}' representa un valor monetario. Se utiliza DECIMAL(10,2) "
                "en lugar de FLOAT para garantizar precisión decimal exacta en cálculos contables sin errores de redondeo binario."
            ),
        }

    # 2. Fechas y marcas de tiempo -> DATE / DATETIME
    datetime_tokens = ("fecha_hora", "registro", "creado", "actualizado", "timestamp", "fecha_pago", "fecha_pedido", "fecha_venta")
    if any(tok in c for tok in datetime_tokens):
        return {
            "data_type": "DATETIME",
            "length": None,
            "nullable": False,
            "default_value": "CURRENT_TIMESTAMP",
            "is_unique": False,
            "tutor_explanation": (
                f"La columna '{c}' registra un instante temporal con fecha y hora (DATETIME), "
                "ideal para trazabilidad cronológica y auditoría de eventos."
            ),
        }

    date_tokens = ("fecha", "nacimiento", "vencimiento", "inicio", "fin", "baja", "ingreso", "emision", "prestamo")
    if any(tok in c for tok in date_tokens):
        return {
            "data_type": "DATE",
            "length": None,
            "nullable": True if "baja" in c else False,
            "default_value": None,
            "is_unique": False,
            "tutor_explanation": (
                f"La columna '{c}' almacena una fecha de calendario (DATE), permitiendo ordenar cronológicamente "
                "y calcular intervalos de días de forma nativa en SQL."
            ),
        }

    # 3. Identificadores únicos naturales -> VARCHAR con UNIQUE
    unique_tokens = ("email", "correo", "dni", "nif", "cif", "nie", "pasaporte", "matricula", "isbn", "codigo", "sku", "username", "referencia")
    if any(c == tok or c.startswith(tok + "_") or c.endswith("_" + tok) for tok in unique_tokens):
        return {
            "data_type": "VARCHAR",
            "length": 120,
            "nullable": False,
            "default_value": None,
            "is_unique": True,
            "tutor_explanation": (
                f"'{c}' es un identificador de negocio natural. Aunque la tabla tiene su clave primaria 'id', "
                "la restricción UNIQUE impide que existan dos registros con el mismo valor."
            ),
        }

    # 4. Estados binarios -> BOOLEAN
    bool_tokens = ("activo", "pagado", "disponible", "devuelto", "completado", "confirmado", "verificado", "entregado")
    if c in bool_tokens or c.startswith("es_") or c.startswith("tiene_"):
        default_bool = "0" if c in ("pagado", "devuelto", "completado") else "1"
        return {
            "data_type": "BOOLEAN",
            "length": None,
            "nullable": False,
            "default_value": default_bool,
            "is_unique": False,
            "tutor_explanation": (
                f"'{c}' modela un estado lógico binario (Verdadero/Falso). En SQLite se almacena como 1 o 0 "
                "y permite filtrar estados rápidamente sin ambigüedades de texto."
            ),
        }

    # 5. Textos largos -> TEXT
    text_tokens = (
        "descripcion",
        "observaciones",
        "notas",
        "comentario",
        "comentarios",
        "diagnostico",
        "detalle",
        "biografia",
        "contenido",
        "resumen",
        "motivo",
    )
    if any(tok in c for tok in text_tokens):
        return {
            "data_type": "TEXT",
            "length": None,
            "nullable": True,
            "default_value": None,
            "is_unique": False,
            "tutor_explanation": (
                f"'{c}' está pensado para texto libre extenso (TEXT), sin límite rígido de caracteres."
            ),
        }

    # 6. Cantidades y enteros -> INTEGER
    int_tokens = (
        "stock",
        "cantidad",
        "unidades",
        "capacidad",
        "edad",
        "anio",
        "kilometraje",
        "creditos",
        "horas",
        "duracion",
        "plazas",
        "numero",
        "puntos",
    )
    if any(tok in c for tok in int_tokens):
        return {
            "data_type": "INTEGER",
            "length": None,
            "nullable": False,
            "default_value": "0" if "stock" in c or "cantidad" in c else None,
            "is_unique": False,
            "tutor_explanation": (
                f"'{c}' representa una magnitud entera (INTEGER), apta para conteos, sumas e inventario."
            ),
        }

    # 7. Calificaciones o decimales no monetarios
    if "calificacion" in c or "nota" in c or "porcentaje" in c:
        return {
            "data_type": "DECIMAL(5,2)",
            "length": None,
            "nullable": True,
            "default_value": None,
            "is_unique": False,
            "tutor_explanation": f"'{c}' almacena un valor numérico con decimales controlados.",
        }

    # 8. Por defecto: cadena de texto acotada VARCHAR(150)
    return {
        "data_type": "VARCHAR",
        "length": 150,
        "nullable": False if c in ("nombre", "titulo", "marca", "modelo") else True,
        "default_value": None,
        "is_unique": False,
        "tutor_explanation": (
            f"'{c}' almacena texto estructurado corto (VARCHAR) con longitud máxima definida."
        ),
    }


def build_column(
    name: str,
    description: str = "",
    force_type: Optional[str] = None,
    is_pk: bool = False,
    is_fk: bool = False,
    fk_target_table: Optional[str] = None,
    fk_target_column: Optional[str] = None,
) -> ColumnModel:
    col_name = to_snake_case(name)
    if is_pk:
        return ColumnModel(
            name=col_name,
            data_type="INTEGER",
            nullable=False,
            is_pk=True,
            auto_increment=True,
            description=description or "Identificador único subrogado de la tabla",
            tutor_explanation=(
                f"Clave Primaria Subrogada ('{col_name}'): garantiza que cada fila tenga un número único "
                "irrepetible asignado automáticamente por el motor, independiente de si cambian otros datos."
            ),
        )
    if is_fk and fk_target_table:
        return ColumnModel(
            name=col_name,
            data_type="INTEGER",
            nullable=False,
            is_fk=True,
            fk_target_table=fk_target_table,
            fk_target_column=fk_target_column or "id",
            description=description or f"Referencia relacional hacia {fk_target_table}.id",
            tutor_explanation=(
                f"Clave Foránea ('{col_name}'): conecta cada registro de esta tabla con un registro real "
                f"de la tabla '{fk_target_table}', impidiendo referencias huérfanas."
            ),
        )

    sem = infer_column_type(col_name)
    dtype = force_type if force_type else str(sem["data_type"])
    return ColumnModel(
        name=col_name,
        data_type=dtype,
        length=sem["length"] if not force_type else None,
        nullable=bool(sem["nullable"]),
        default_value=sem["default_value"],  # type: ignore[arg-type]
        is_unique=bool(sem["is_unique"]),
        description=description or f"Atributo {col_name.replace('_', ' ')}",
        tutor_explanation=str(sem["tutor_explanation"]),
    )


class SpanishNLPParser:
    """
    Motor determinista de análisis sintáctico y heurístico para transformar descripciones
    en lenguaje natural en español a una instancia del Contrato Maestro JSON.
    """

    STOPWORDS_ENTITIES = {
        "sistema",
        "programa",
        "base",
        "datos",
        "tabla",
        "tablas",
        "entidad",
        "entidades",
        "registro",
        "registros",
        "gestion",
        "control",
        "aplicacion",
        "proyecto",
        "taller",
        "mecanico",
        "clinica",
        "biblioteca",
        "tienda",
        "escuela",
        "universidad",
        "hotel",
        "empresa",
        "negocio",
        "informacion",
        "proceso",
        "relacion",
        "relaciones",
        "varios",
        "varias",
        "distintos",
        "distintas",
        "muchos",
        "muchas",
        "cada",
        "donde",
        "como",
        "para",
        "con",
        "sin",
        "por",
        "una",
        "uno",
        "unos",
        "unas",
        "los",
        "las",
        "del",
    }

    KNOWN_ATTRIBUTE_WORDS = {
        "nombre",
        "apellidos",
        "dni",
        "nif",
        "cif",
        "email",
        "correo",
        "telefono",
        "telefono_1",
        "telefono_2",
        "direccion",
        "direccion_1",
        "direccion_2",
        "ciudad",
        "precio",
        "coste",
        "costo",
        "importe",
        "salario",
        "sueldo",
        "total",
        "subtotal",
        "stock",
        "cantidad",
        "unidades",
        "capacidad",
        "fecha",
        "fecha_nacimiento",
        "fecha_registro",
        "fecha_ingreso",
        "fecha_emision",
        "fecha_inicio",
        "fecha_fin",
        "descripcion",
        "observaciones",
        "notas",
        "comentario",
        "diagnostico",
        "codigo",
        "sku",
        "isbn",
        "matricula",
        "marca",
        "modelo",
        "anio",
        "kilometraje",
        "titulo",
        "editorial",
        "especialidad",
        "cargo",
        "activo",
        "pagado",
        "disponible",
        "completado",
        "confirmado",
        "estado",
        "tipo",
        "creditos",
        "horas",
        "calificacion",
    }

    def parse_text_to_schema(
        self,
        text: str,
        db_name: Optional[str] = None,
        dialect: str = "sqlite",
    ) -> MasterSchemaContract:
        raw_text = (text or "").strip()
        if not raw_text:
            raw_text = (
                "Necesito gestionar un taller mecánico donde los clientes traen varios vehículos, "
                "cada vehículo tiene reparaciones y en cada reparación se utilizan distintas piezas con un precio y stock."
            )

        # Modo 1 (Prioritario): Especificación Estructurada Explícita (Tabla <NOMBRE> + columnas tipadas)
        if self._is_structured_spec(raw_text):
            return self._parse_structured_specification(raw_text, db_name=db_name, dialect=dialect)

        norm_text = strip_accents(raw_text.lower())

        # 1. Detectar título y nombre de base de datos según el dominio mencionado
        inferred_db_name, inferred_title = self._infer_project_identity(raw_text, norm_text, db_name)

        # 2. Detectar entidades mencionadas en el texto
        detected_entities = self._detect_entities(norm_text)
        if not detected_entities:
            # Fallback si el usuario escribió una frase muy corta o abstracta
            detected_entities = ["clientes", "vehiculos", "reparaciones", "piezas"]

        # 3. Extraer atributos explícitos solicitados por el usuario para cada entidad
        explicit_attrs, explicit_type_overrides = self._extract_explicit_attributes(
            norm_text, detected_entities
        )

        # 4. Construir tablas iniciales con su PK subrogada y columnas combinadas (explícitas + dominio)
        tables_by_name: Dict[str, TableModel] = {}
        for idx, ent_name in enumerate(detected_entities):
            cols: List[ColumnModel] = [
                build_column("id", f"Identificador único de {ent_name}", is_pk=True)
            ]
            existing_col_names: Set[str] = {"id"}

            # Añadir columnas base conocidas del dominio
            for base_col, base_desc in ENTITY_DEFAULT_COLUMNS.get(ent_name, [
                ("codigo", f"Código identificador de {to_singular(ent_name)}"),
                ("nombre", f"Nombre o título de {to_singular(ent_name)}"),
                ("descripcion", f"Descripción detallada de {to_singular(ent_name)}"),
                ("fecha_registro", f"Fecha de alta de {to_singular(ent_name)}"),
                ("activo", f"Estado activo de {to_singular(ent_name)}"),
            ]):
                if base_col not in existing_col_names:
                    override_type = explicit_type_overrides.get((ent_name, base_col))
                    cols.append(build_column(base_col, base_desc, force_type=override_type))
                    existing_col_names.add(base_col)

            # Añadir cualquier columna explícita pedida por el usuario en el texto
            for exp_col in explicit_attrs.get(ent_name, []):
                if exp_col not in existing_col_names:
                    override_type = explicit_type_overrides.get((ent_name, exp_col))
                    cols.append(
                        build_column(
                            exp_col,
                            f"Atributo '{exp_col}' especificado en el requerimiento",
                            force_type=override_type,
                        )
                    )
                    existing_col_names.add(exp_col)

            is_hist = ent_name in HISTORICAL_KEYWORDS or to_singular(ent_name) in HISTORICAL_KEYWORDS
            col_grid_x = 70.0 + (idx % 3) * 350.0
            col_grid_y = 70.0 + (idx // 3) * 320.0

            tables_by_name[ent_name] = TableModel(
                name=ent_name,
                description=f"Entidad principal que almacena los registros de {ent_name.replace('_', ' ')}.",
                is_associative=False,
                is_historical=is_hist,
                position_x=col_grid_x,
                position_y=col_grid_y,
                columns=cols,
                indexes=[],
                tutor_explanation=(
                    f"La tabla '{ent_name}' representa una entidad sustantiva del dominio. "
                    f"Cada fila corresponde a un '{to_singular(ent_name)}' único identificado por su clave primaria 'id'."
                ),
            )

        # 5. Inferir relaciones (1:N, N:M, 1:1) a partir de patrones verbales y semántica de dominio
        relations: List[RelationModel] = []
        self._infer_and_inject_relations(norm_text, detected_entities, tables_by_name, relations)

        # Recalcular posiciones en un layout topológico limpio para el lienzo ER
        ordered_tables = list(tables_by_name.values())
        self._layout_tables_cleanly(ordered_tables)

        contract = MasterSchemaContract(
            db_name=inferred_db_name,
            title=inferred_title,
            description=raw_text,
            source_prompt=raw_text,
            dialect=dialect,  # type: ignore[arg-type]
            is_deployed=False,
            version=1,
            updated_at=datetime.now().isoformat(timespec="seconds"),
            tables=ordered_tables,
            relations=relations,
            audit_alerts=[],
            tutor_metadata={
                "nlp_summary": (
                    f"Se analizaron las oraciones en español detectando {len(ordered_tables)} tablas "
                    f"(incluyendo tablas intermedias N:M) y {len(relations)} vínculos de integridad referencial."
                ),
                "detected_entities": detected_entities,
            },
        )
        return contract

    def _extract_explicit_db_name(self, raw_text: str) -> Optional[str]:
        """Extrae el nombre explícito de la base de datos si el texto declara 'base de datos llamada <nombre>'."""
        stop = {
            "para", "con", "de", "del", "que", "en", "donde", "sobre", "la", "el",
            "un", "una", "los", "las", "por", "como", "segun", "mediante", "sin",
        }
        patterns = [
            r"base\s+de\s+datos\s+(?:llamada|denominada|nombrada)\s+[`\"'«]?([A-Za-z_][A-Za-z0-9_]*)[`\"'»]?",
            r"crear\s+(?:una\s+|la\s+)?base\s+de\s+datos\s+(?:llamada\s+|denominada\s+|nombrada\s+)?[`\"'«]?([A-Za-z_][A-Za-z0-9_]*)[`\"'»]?",
            r"\bbd\s+(?:llamada|denominada|nombrada)\s+[`\"'«]?([A-Za-z_][A-Za-z0-9_]*)[`\"'»]?",
            r"esquema\s+(?:llamado|denominado|nombrado)\s+[`\"'«]?([A-Za-z_][A-Za-z0-9_]*)[`\"'»]?",
        ]
        for pat in patterns:
            m = re.search(pat, raw_text, flags=re.IGNORECASE)
            if m:
                cand = to_snake_case(m.group(1))
                if cand and cand not in stop:
                    return cand
        return None

    def _infer_project_identity(
        self, raw_text: str, norm_text: str, explicit_db_name: Optional[str]
    ) -> Tuple[str, str]:
        declared_db = self._extract_explicit_db_name(raw_text)
        if declared_db:
            return declared_db, f"Base de Datos {declared_db.replace('_', ' ').title()}"

        domain_patterns = [
            (r"taller\s+mecanico", "taller_mecanico", "Gestión de Taller Mecánico"),
            (r"biblioteca", "biblioteca_municipal", "Sistema de Biblioteca y Préstamos"),
            (r"clinica|hospital|consultorio|medic", "clinica_medica", "Gestión de Clínica Médica"),
            (r"universidad|escuela|colegio|academia|curso", "academia_cursos", "Gestión Académica y Matrículas"),
            (r"hotel|reserva|habitacion", "hotel_reservas", "Sistema de Reservas de Hotel"),
            (r"tienda|comercio|inventario|almacen|pedido|producto", "comercio_inventario", "Gestión de Inventario y Pedidos"),
            (r"recursos\s+humanos|empleado|departamento", "rrhh_proyectos", "Gestión de Empleados y Proyectos"),
        ]
        for pat, slug, title in domain_patterns:
            if re.search(pat, norm_text):
                return (to_snake_case(explicit_db_name) if explicit_db_name else slug, title)

        if explicit_db_name:
            clean_db = to_snake_case(explicit_db_name)
            return clean_db, clean_db.replace("_", " ").title()

        return "proyecto_relacional", "Proyecto Relacional ChemySQL"

    def _detect_entities(self, norm_text: str) -> List[str]:
        found: List[str] = []

        # 1. Buscar entidades conocidas en el catálogo en orden de aparición en el texto
        known_candidates: List[Tuple[int, str]] = []
        all_known_nouns = set(ENTITY_DEFAULT_COLUMNS.keys())
        synonyms = {
            "coche": "vehiculos",
            "coches": "vehiculos",
            "auto": "vehiculos",
            "autos": "vehiculos",
            "automovil": "vehiculos",
            "automoviles": "vehiculos",
            "repuesto": "piezas",
            "repuestos": "piezas",
            "recambio": "piezas",
            "recambios": "piezas",
            "lector": "socios",
            "lectores": "socios",
            "alumno": "estudiantes",
            "alumnos": "estudiantes",
            "docente": "profesores",
            "docentes": "profesores",
            "doctor": "medicos",
            "doctores": "medicos",
            "trabajador": "empleados",
            "trabajadores": "empleados",
            "articulo": "productos",
            "articulos": "productos",
        }

        for plural_ent in all_known_nouns:
            sing_ent = to_singular(plural_ent)
            match = re.search(rf"\b({plural_ent}|{sing_ent})\b", norm_text)
            if match:
                known_candidates.append((match.start(), plural_ent))

        for syn_word, target_ent in synonyms.items():
            match = re.search(rf"\b{syn_word}\b", norm_text)
            if match:
                known_candidates.append((match.start(), target_ent))

        known_candidates.sort(key=lambda x: x[0])
        for _, ent in known_candidates:
            if ent not in found:
                found.append(ent)

        # 2. Detectar entidades nuevas mediante patrones sintácticos explícitos:
        # "tabla X", "entidad X", "los/las X traen/tienen/realizan/...", "cada X tiene", "varios/varias/distintos/distintas X"
        syntactic_patterns = [
            r"\b(?:tabla|entidad|modulo)\s+(?:de\s+)?([a-z]{3,20})\b",
            r"\b(?:los|las)\s+([a-z]{4,20})\s+(?:traen|tienen|realizan|hacen|compran|solicitan|registran|pueden|reciben|cursan|atienden)",
            r"\bcada\s+([a-z]{4,20})\s+(?:tiene|posee|incluye|contiene|genera|pertenece|realiza)",
            r"\b(?:varios|varias|distintos|distintas|muchos|muchas|multiples)\s+([a-z]{4,20})\b",
        ]
        for pat in syntactic_patterns:
            for m in re.finditer(pat, norm_text):
                candidate = m.group(1)
                if (
                    candidate not in self.STOPWORDS_ENTITIES
                    and candidate not in self.KNOWN_ATTRIBUTE_WORDS
                ):
                    plural_cand = to_plural(candidate)
                    if (
                        plural_cand not in found
                        and plural_cand not in self.STOPWORDS_ENTITIES
                        and to_singular(plural_cand) not in self.KNOWN_ATTRIBUTE_WORDS
                    ):
                        found.append(plural_cand)

        return found

    def _extract_explicit_attributes(
        self, norm_text: str, entities: List[str]
    ) -> Tuple[Dict[str, List[str]], Dict[Tuple[str, str], str]]:
        """
        Detecta atributos explícitos asociados a una entidad en frases como:
        'piezas con un precio y stock', 'clientes con telefono_1, telefono_2 y direccion_1',
        'facturas con importe en float'.
        """
        attrs_by_entity: Dict[str, List[str]] = {e: [] for e in entities}
        type_overrides: Dict[Tuple[str, str], str] = {}

        if not entities:
            return attrs_by_entity, type_overrides

        # Buscar cláusulas "ENTIDAD ... con ATRIBUTO1, ATRIBUTO2 y ATRIBUTO3"
        all_entity_tokens = set(entities) | {to_singular(e) for e in entities}
        for ent in entities:
            sing = to_singular(ent)
            other_entities = [o for o in all_entity_tokens if o not in (ent, sing)]
            other_ent_regex = rf"\b(?:{'|'.join(re.escape(o) for o in other_entities)})\b" if other_entities else r"$"
            pattern = rf"\b(?:{ent}|{sing})\b\s+(?:con|tiene|incluyendo|atributos|campos)\s+([^.;]+)"
            for m in re.finditer(pattern, norm_text):
                segment = m.group(1)
                # Cortar si aparece otra entidad o verbo relacional
                segment = re.split(
                    rf"(?:\b(?:donde|cada|que\s+se\s+relaciona|relacionado|y\s+cada|y\s+los|y\s+las|agendan|realizan|traen|tienen|atendidas|atendidos)\b|{other_ent_regex})",
                    segment,
                )[0]
                tokens = re.findall(r"\b([a-z][a-z0-9_]{2,25})\b", segment)
                for idx, tok in enumerate(tokens):
                    if tok in ("un", "una", "unos", "unas", "el", "la", "los", "las", "su", "sus", "tipo", "en"):
                        continue
                    if tok in ("float", "real", "text", "varchar", "integer", "decimal", "date"):
                        # Si el token anterior era un atributo, aplica override de tipo (útil para probar el auditor)
                        if attrs_by_entity[ent]:
                            prev_attr = attrs_by_entity[ent][-1]
                            type_overrides[(ent, prev_attr)] = tok.upper()
                        continue
                    if tok in entities or to_plural(tok) in entities:
                        continue
                    if (
                        tok in self.KNOWN_ATTRIBUTE_WORDS
                        or re.match(r"^[a-z]+_[0-9]+$", tok)
                        or tok.startswith(("fecha_", "precio_", "coste_", "telefono", "direccion", "lista_"))
                    ):
                        if tok not in attrs_by_entity[ent]:
                            attrs_by_entity[ent].append(tok)

        # Detectar patrones explícitos de prueba de 1FN como telefono_1, telefono_2 en cualquier parte del texto
        numbered_cols = re.findall(r"\b([a-z]+_[123])\b", norm_text)
        if numbered_cols and entities:
            target_ent = entities[0]
            for ncol in numbered_cols:
                if ncol not in attrs_by_entity[target_ent]:
                    attrs_by_entity[target_ent].append(ncol)

        return attrs_by_entity, type_overrides

    def _infer_and_inject_relations(
        self,
        norm_text: str,
        entities: List[str],
        tables_by_name: Dict[str, TableModel],
        relations: List[RelationModel],
    ) -> None:
        connected_pairs: Set[Tuple[str, str]] = set()

        def add_1n_relation(parent_table: str, child_table: str, explanation: str, on_delete: str = "RESTRICT") -> None:
            if parent_table == child_table:
                return
            pair = tuple(sorted([parent_table, child_table]))
            if pair in connected_pairs:
                return
            connected_pairs.add(pair)

            fk_col_name = f"{to_singular(parent_table)}_id"
            child_tbl = tables_by_name[child_table]
            if not any(c.name == fk_col_name for c in child_tbl.columns):
                fk_col = build_column(
                    fk_col_name,
                    description=f"Clave foránea hacia {parent_table}.id",
                    is_fk=True,
                    fk_target_table=parent_table,
                    fk_target_column="id",
                )
                # Insertar después de la PK 'id'
                insert_pos = 1
                while insert_pos < len(child_tbl.columns) and child_tbl.columns[insert_pos].is_fk:
                    insert_pos += 1
                child_tbl.columns.insert(insert_pos, fk_col)

            rel_id = f"rel_{child_table}_{parent_table}"
            relations.append(
                RelationModel(
                    id=rel_id,
                    source_table=child_table,
                    source_column=fk_col_name,
                    target_table=parent_table,
                    target_column="id",
                    cardinality="1:N",
                    on_delete=on_delete,  # type: ignore[arg-type]
                    on_update="CASCADE",
                    tutor_explanation=(
                        f"{explanation}. En una relación 1:N (Uno a Muchos), la clave foránea "
                        f"'{fk_col_name}' siempre se coloca en la tabla del lado 'Muchos' ('{child_table}')."
                    ),
                )
            )

        def add_nm_relation(left_table: str, right_table: str, explanation: str) -> None:
            if left_table == right_table:
                return
            pair = tuple(sorted([left_table, right_table]))
            if pair in connected_pairs:
                return
            connected_pairs.add(pair)

            assoc_name = f"{to_singular(left_table)}_{right_table}"
            left_fk = f"{to_singular(left_table)}_id"
            right_fk = f"{to_singular(right_table)}_id"

            if assoc_name not in tables_by_name:
                assoc_cols = [
                    build_column("id", f"Identificador único de relación {assoc_name}", is_pk=True),
                    build_column(
                        left_fk,
                        f"Referencia a {left_table}.id",
                        is_fk=True,
                        fk_target_table=left_table,
                        fk_target_column="id",
                    ),
                    build_column(
                        right_fk,
                        f"Referencia a {right_table}.id",
                        is_fk=True,
                        fk_target_table=right_table,
                        fk_target_column="id",
                    ),
                ]
                # Si involucra piezas o productos, añadir cantidad y precio_aplicado
                if right_table in ("piezas", "productos") or left_table in ("piezas", "productos"):
                    assoc_cols.append(build_column("cantidad", "Cantidad de unidades utilizadas"))
                    assoc_cols.append(build_column("precio_unitario", "Precio unitario aplicado en el momento"))
                else:
                    assoc_cols.append(build_column("fecha_registro", "Fecha de vinculación"))

                tables_by_name[assoc_name] = TableModel(
                    name=assoc_name,
                    description=(
                        f"Tabla asociativa intermedia que resuelve la relación N:M entre "
                        f"'{left_table}' y '{right_table}'."
                    ),
                    is_associative=True,
                    is_historical=False,
                    columns=assoc_cols,
                    indexes=[left_fk, right_fk],
                    tutor_explanation=(
                        f"Tabla Asociativa ('{assoc_name}'): en bases de datos relacionales no se pueden conectar "
                        f"dos tablas N:M directamente sin duplicar datos. Esta tabla intermedia divide la relación N:M "
                        f"en dos relaciones 1:N limpias mediante las claves foráneas '{left_fk}' y '{right_fk}'."
                    ),
                )

            relations.append(
                RelationModel(
                    id=f"rel_{assoc_name}_{left_table}",
                    source_table=assoc_name,
                    source_column=left_fk,
                    target_table=left_table,
                    target_column="id",
                    cardinality="N:M",
                    on_delete="RESTRICT",
                    on_update="CASCADE",
                    via_table=assoc_name,
                    tutor_explanation=(
                        f"{explanation}. Vincula la tabla intermedia '{assoc_name}' con '{left_table}'."
                    ),
                )
            )
            relations.append(
                RelationModel(
                    id=f"rel_{assoc_name}_{right_table}",
                    source_table=assoc_name,
                    source_column=right_fk,
                    target_table=right_table,
                    target_column="id",
                    cardinality="N:M",
                    on_delete="RESTRICT",
                    on_update="CASCADE",
                    via_table=assoc_name,
                    tutor_explanation=(
                        f"{explanation}. Vincula la tabla intermedia '{assoc_name}' con '{right_table}'."
                    ),
                )
            )

        # 1. Evaluar relaciones canónicas de dominio presentes entre las entidades detectadas
        entity_set = set(entities)
        for left_ent, right_ent, card, hint in CANONICAL_DOMAIN_RELATIONS:
            if left_ent in entity_set and right_ent in entity_set:
                # Comprobar si en el texto se pidió explícitamente N:M o 1:N
                if card == "N:M":
                    add_nm_relation(left_ent, right_ent, hint)
                else:
                    add_1n_relation(left_ent, right_ent, hint)

        # 2. Inferir relaciones adicionales únicamente para entidades que quedaron aisladas (sin ninguna conexión)
        adj: Dict[str, Set[str]] = {e: set() for e in entities}
        for r in relations:
            if r.source_table in adj and r.target_table in adj:
                adj[r.source_table].add(r.target_table)
                adj[r.target_table].add(r.source_table)
            elif r.via_table:
                # Conectar tablas que comparten la misma tabla asociativa
                for r2 in relations:
                    if r2.via_table == r.via_table and r2.target_table != r.target_table:
                        if r.target_table in adj and r2.target_table in adj:
                            adj[r.target_table].add(r2.target_table)
                            adj[r2.target_table].add(r.target_table)

        def are_connected_in_graph(start: str, goal: str) -> bool:
            seen: Set[str] = {start}
            queue: List[str] = [start]
            while queue:
                curr = queue.pop(0)
                if curr == goal:
                    return True
                for nxt in adj.get(curr, set()):
                    if nxt not in seen:
                        seen.add(nxt)
                        queue.append(nxt)
            return False

        for i in range(len(entities) - 1):
            e1 = entities[i]
            e2 = entities[i + 1]
            if are_connected_in_graph(e1, e2):
                continue

            s1, s2 = to_singular(e1), to_singular(e2)
            between_match = re.search(
                rf"\b(?:{e1}|{s1})\b([^.;]{{0,120}})\b(?:{e2}|{s2})\b", norm_text
            )
            between_text = between_match.group(1) if between_match else ""

            if re.search(r"\b(?:utilizan|usan|incluyen|contienen|relacionan|muchos\s+a\s+muchos|distintas|multiples)\b", between_text) and re.search(r"\b(?:en\s+cada|varios|muchos)\b", norm_text):
                add_nm_relation(
                    e1,
                    e2,
                    f"Relación muchos-a-muchos inferida entre '{e1}' y '{e2}'",
                )
            else:
                add_1n_relation(
                    e1,
                    e2,
                    f"Relación jerárquica 1:N inferida donde '{e1}' agrupa múltiples registros de '{e2}'",
                )
            adj[e1].add(e2)
            adj[e2].add(e1)

    def _layout_tables_cleanly(self, tables: List[TableModel]) -> None:
        """Organiza las coordenadas (position_x, position_y) en una retícula clara sin solapamientos."""
        cols_per_row = 3 if len(tables) > 4 else 2
        x_gap = 324.0
        y_gap = 288.0
        for idx, tbl in enumerate(tables):
            col_idx = idx % cols_per_row
            row_idx = idx // cols_per_row
            tbl.position_x = 20.0 + col_idx * x_gap
            tbl.position_y = 20.0 + row_idx * y_gap

    # ==========================================================================
    # MODO 1 (PRIORITARIO): ANALIZADOR DE ESPECIFICACIÓN ESTRUCTURADA EXPLÍCITA
    # ==========================================================================

    def _is_structured_spec(self, raw_text: str) -> bool:
        """Detecta si el texto contiene definiciones estructuradas explícitas (Tabla <NOMBRE> + columnas tipadas)."""
        table_headers = list(
            re.finditer(
                r"(?:^|[\n.;:•\-]\s*)(?:\*\*)?Tabla\s+([A-Za-z_][A-Za-z0-9_]*)(?:\*\*)?\s*(?:\([^)]*\))?\s*:",
                raw_text,
                flags=re.IGNORECASE,
            )
        )
        if not table_headers:
            return False
        has_typed_cols = bool(
            re.search(
                r"[a-zA-Z_][a-zA-Z0-9_]*\s*:\s*(?:tipo\s+)?(?:SMALLINT|TINYINT|BIGINT|INTEGER|INT|VARCHAR|CHAR|DECIMAL|NUMERIC|DATE|TIME|DATETIME|BOOLEAN|TEXT|columna\s+calculada|calculad[ao])",
                raw_text,
                flags=re.IGNORECASE,
            )
        )
        return len(table_headers) >= 1 and has_typed_cols

    def _parse_structured_specification(
        self,
        raw_text: str,
        db_name: Optional[str] = None,
        dialect: str = "sqlite",
    ) -> MasterSchemaContract:
        # 1. Detectar nombre de base de datos y cotejamiento (collation)
        # Si el texto declara explícitamente "base de datos llamada <nombre>", tiene prioridad absoluta.
        inferred_db = self._extract_explicit_db_name(raw_text)
        if inferred_db:
            final_db_name = inferred_db
        elif db_name and to_snake_case(db_name) not in ("proyecto_chemysql", "proyecto_sgbd", "nuevo_proyecto"):
            final_db_name = to_snake_case(db_name)
        else:
            final_db_name = to_snake_case(db_name or "proyecto_estructurado")
        final_title = f"Base de Datos {final_db_name.replace('_', ' ').title()}"

        collation = self._extract_collation(raw_text)

        # 2. Localizar todos los bloques "Tabla <NOMBRE> (descripción opcional):"
        header_pattern = re.compile(
            r"(?:^|[\n.;:•\-]\s*)(?:\*\*)?Tabla\s+([A-Za-z_][A-Za-z0-9_]*)(?:\*\*)?\s*(?:\(([^)]*)\))?\s*:",
            flags=re.IGNORECASE,
        )
        matches = list(header_pattern.finditer(raw_text))

        tables: List[TableModel] = []
        raw_relations_pending: List[Tuple[str, str, str, str]] = []
        table_names_ci: Dict[str, str] = {}

        for idx, m in enumerate(matches):
            t_name = m.group(1).strip()
            t_desc = (m.group(2) or "").strip()
            body_start = m.end()
            body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(raw_text)
            body_text = raw_text[body_start:body_end].strip()

            table_names_ci[t_name.lower()] = t_name
            table_names_ci[to_singular(t_name).lower()] = t_name
            table_names_ci[to_plural(t_name).lower()] = t_name

            # 3. Extraer declaración de clave primaria compuesta al cierre de la tabla si existe
            composite_pk_cols: List[str] = []
            m_comp_pk = re.search(
                r"(?:la\s+)?clave\s+primaria(?:\s+de\s+[A-Za-z0-9_]+)?\s+(?:es\s+una\s+)?(?:clave\s+primaria\s+)?compuesta[^.(]*\(([^)]+)\)",
                body_text,
                flags=re.IGNORECASE,
            )
            if not m_comp_pk:
                m_comp_pk = re.search(
                    r"PRIMARY\s+KEY\s*\(([^)]+)\)",
                    body_text,
                    flags=re.IGNORECASE,
                )
            if m_comp_pk:
                composite_pk_cols = [
                    c.strip().strip("`'\"")
                    for c in m_comp_pk.group(1).split(",")
                    if c.strip()
                ]
                # Retirar la frase de clave primaria compuesta para que no se confunda con la última columna
                body_for_cols = body_text[: m_comp_pk.start()].strip()
            else:
                body_for_cols = body_text

            # 4. Extraer cada columna explícita "<col_name>: <especificación>"
            col_header_pat = re.compile(
                r"(?:^|[\n;•]\s*|\.\s+)(?:[-*]\s*)?(?:\*\*)?([a-zA-Z_][a-zA-Z0-9_]*)(?:\*\*)?\s*:\s*"
            )
            col_matches = list(col_header_pat.finditer(body_for_cols))

            cols: List[ColumnModel] = []
            for c_idx, cm in enumerate(col_matches):
                col_name = cm.group(1).strip()
                if col_name.lower() in ("tabla", "nota", "notas", "importante", "restriccion", "restricciones"):
                    continue
                spec_start = cm.end()
                spec_end = col_matches[c_idx + 1].start() if c_idx + 1 < len(col_matches) else len(body_for_cols)
                spec_text = body_for_cols[spec_start:spec_end].strip().rstrip(".;")

                col_model, fk_info = self._parse_structured_column(col_name, spec_text, t_name)
                cols.append(col_model)
                if fk_info:
                    raw_relations_pending.append((t_name, col_name, fk_info[0], fk_info[1]))

            # 5. Aplicar clave primaria compuesta si se declaró
            pk_list: List[str] = []
            if composite_pk_cols:
                pk_set = {c.lower() for c in composite_pk_cols}
                for col in cols:
                    if col.name.lower() in pk_set:
                        col.is_pk = True
                        col.nullable = False
                        pk_list.append(col.name)
            else:
                pk_list = [c.name for c in cols if c.is_pk]

            is_hist = to_snake_case(t_name) in HISTORICAL_KEYWORDS or to_singular(t_name) in HISTORICAL_KEYWORDS
            tables.append(
                TableModel(
                    name=t_name,
                    description=t_desc or f"Tabla {t_name} definida por especificación técnica estructurada.",
                    is_associative=False,
                    is_historical=is_hist,
                    primary_key=pk_list,
                    columns=cols,
                    indexes=[],
                    tutor_explanation=(
                        f"Tabla '{t_name}' generada con fidelidad exacta a tu especificación técnica"
                        + (
                            f" con clave primaria compuesta ({', '.join(pk_list)})."
                            if len(pk_list) > 1
                            else f" ({len(cols)} columnas explícitas)."
                        )
                    ),
                )
            )

        # 6. Resolver y construir relaciones de claves foráneas en la dirección exacta declarada
        relations: List[RelationModel] = []
        table_map = {t.name: t for t in tables}
        for src_tbl, src_col, raw_tgt_tbl, raw_tgt_col in raw_relations_pending:
            resolved_tgt_tbl = table_names_ci.get(raw_tgt_tbl.lower(), raw_tgt_tbl)
            resolved_tgt_col = raw_tgt_col

            # Actualizar fk_target_table con el nombre exacto de la tabla destino
            # y heredar exactamente el mismo tipo de dato y longitud que la columna PK referenciada
            if src_tbl in table_map:
                col_obj = next((c for c in table_map[src_tbl].columns if c.name == src_col), None)
                if col_obj:
                    col_obj.fk_target_table = resolved_tgt_tbl
                    col_obj.fk_target_column = resolved_tgt_col
                    if resolved_tgt_tbl in table_map:
                        tgt_col_obj = next(
                            (
                                tc
                                for tc in table_map[resolved_tgt_tbl].columns
                                if tc.name.lower() == resolved_tgt_col.lower()
                            ),
                            None,
                        )
                        if tgt_col_obj:
                            col_obj.fk_target_column = tgt_col_obj.name
                            resolved_tgt_col = tgt_col_obj.name
                            col_obj.data_type = tgt_col_obj.data_type
                            col_obj.length = tgt_col_obj.length
                            type_label = (
                                f"{col_obj.data_type}({col_obj.length})"
                                if col_obj.length
                                else col_obj.data_type
                            )
                            col_obj.tutor_explanation = (
                                f"Columna '{col_obj.name}' ({type_label}) en '{src_tbl}', "
                                f"clave foránea sincronizada con '{resolved_tgt_tbl}.{tgt_col_obj.name}'."
                            )

            relations.append(
                RelationModel(
                    id=f"rel_{src_tbl}_{src_col}_{resolved_tgt_tbl}",
                    source_table=src_tbl,
                    source_column=src_col,
                    target_table=resolved_tgt_tbl,
                    target_column=resolved_tgt_col,
                    cardinality="1:N",
                    on_delete="RESTRICT",
                    on_update="CASCADE",
                    tutor_explanation=(
                        f"Relación 1:N explícita: '{src_tbl}.{src_col}' referencia a "
                        f"'{resolved_tgt_tbl}.{resolved_tgt_col}'."
                    ),
                )
            )

        self._layout_tables_cleanly(tables)

        return MasterSchemaContract(
            db_name=final_db_name,
            title=final_title,
            description=raw_text[:280] + ("..." if len(raw_text) > 280 else ""),
            source_prompt=raw_text,
            dialect=dialect,  # type: ignore[arg-type]
            collation=collation,
            is_deployed=False,
            version=1,
            updated_at=datetime.now().isoformat(timespec="seconds"),
            tables=tables,
            relations=relations,
            audit_alerts=[],
            tutor_metadata={
                "parser_mode": "structured_specification",
                "nlp_summary": (
                    f"Modo Especificación Estructurada: se respetaron exactamente las {len(tables)} tablas declaradas "
                    f"({', '.join(t.name for t in tables)}) con sus tipos SQL, restricciones CHECK/DEFAULT, columnas calculadas y claves primarias."
                ),
                "detected_entities": [t.name for t in tables],
            },
        )

    def _extract_collation(self, raw_text: str) -> Optional[str]:
        m_explicit = re.search(
            r"\b(utf8mb4_[a-z0-9_]+|Modern_Spanish_[A-Z_]+|Latin1_General_[A-Z_]+)\b",
            raw_text,
            flags=re.IGNORECASE,
        )
        if m_explicit:
            return m_explicit.group(1)
        norm = strip_accents(raw_text.lower())
        if ("insensible" in norm and "mayuscula" in norm and ("acento" in norm or "tilde" in norm)) or "ci/ai" in norm or "ci_ai" in norm:
            return "utf8mb4_0900_ai_ci"
        if "cotejamiento" in norm or "collation" in norm or ("insensible" in norm and "mayuscula" in norm):
            return "utf8mb4_spanish_ci"
        return None

    def _parse_structured_column(
        self, col_name: str, spec_text: str, table_name: str
    ) -> Tuple[ColumnModel, Optional[Tuple[str, str]]]:
        norm_spec = strip_accents(spec_text.lower())

        # 1. Tipo SQL y longitud/precisión
        data_type = "VARCHAR"
        length: Optional[int] = None
        m_type = re.search(
            r"\b(DECIMAL\s*\(\s*\d+\s*,\s*\d+\s*\)|NUMERIC\s*\(\s*\d+\s*,\s*\d+\s*\)|VARCHAR\s*\(\s*\d+\s*\)|CHAR\s*\(\s*\d+\s*\)|SMALLINT|TINYINT|BIGINT|INTEGER|INT|DATETIME|TIMESTAMP|DATE|TIME|BOOLEAN|TEXT|FLOAT|REAL)(?=\s|[,.;:\)]|$)",
            spec_text,
            flags=re.IGNORECASE,
        )
        if m_type:
            raw_type = re.sub(r"\s+", "", m_type.group(1).upper())
            m_len = re.match(r"^(VARCHAR|CHAR)\((\d+)\)$", raw_type)
            if m_len:
                data_type = m_len.group(1)
                length = int(m_len.group(2))
            else:
                data_type = raw_type
        else:
            # Si es columna calculada sin tipo explícito, usar DECIMAL(10,2)
            if any(w in norm_spec for w in ("calculad", "generad", "derivad", "producto de")):
                data_type = "DECIMAL(10,2)"
            else:
                sem = infer_column_type(col_name)
                data_type = str(sem["data_type"])
                length = sem["length"]  # type: ignore[assignment]

        # 2. Columna calculada / generada
        computed_expr: Optional[str] = None
        if any(w in norm_spec for w in ("calculad", "generad", "generated always", "columna derivada")):
            m_expr = re.search(
                r"(?:como\s+(?:el\s+producto\s+de\s+|el\s+resultado\s+de\s+|la\s+formula\s+)?|as\s*\(|=\s*|\(\s*)([a-zA-Z_][a-zA-Z0-9_]*\s*[\*\/\+\-]\s*[a-zA-Z0-9_]+)",
                spec_text,
                flags=re.IGNORECASE,
            )
            if m_expr:
                computed_expr = re.sub(r"\s+", " ", m_expr.group(1).strip())

        # 3. Clave primaria, autoincremental, unicidad y nulabilidad
        is_pk = bool(
            re.search(r"\b(?:clave\s+primaria|primary\s+key)\b", norm_spec)
            and "compuesta" not in norm_spec
        )
        auto_inc = bool(re.search(r"\b(?:auto_increment|autoincrement|identity|autoincremental)\b", norm_spec))
        # Evitar falsos positivos de "una única instalación" dentro de notas de cardinalidad
        spec_without_rel_note = re.sub(r"\(relacion\s+[^)]*\)", "", norm_spec)
        is_unique = bool(
            re.search(r"\b(?:unique|valor\s+unic[oa]|no\s+repetible|irrepetible)\b|(?:^|,\s*)unic[oa]\b", spec_without_rel_note)
        )

        if re.search(r"\b(?:not\s+null|obligatorio|obligatoria|no\s+nulo)\b", norm_spec) or is_pk:
            nullable = False
        elif re.search(r"\b(?:opcional|puede\s+ser\s+nulo|permite\s+null)\b", norm_spec):
            nullable = True
        else:
            nullable = True

        # 4. Valor por defecto (DEFAULT ...)
        default_val: Optional[str] = None
        m_def = re.search(r"\bDEFAULT\s+('[^']*'|\d+(?:\.\d+)?|[A-Za-z_][A-Za-z0-9_]*)", spec_text, flags=re.IGNORECASE)
        if not m_def:
            m_def = re.search(r"por\s+defecto\s+(?:de\s+)?('[^']*'|\d+(?:\.\d+)?|[A-Za-z_][A-Za-z0-9_]*)", norm_spec)
        if m_def:
            cand_def = m_def.group(1).strip("'\"")
            if cand_def.lower() not in ("si", "no", "se", "el", "la", "un", "una"):
                default_val = cand_def

        # 5. Restricción CHECK (...)
        check_expr: Optional[str] = None
        m_chk_explicit = re.search(r"\bCHECK\s*\(([^)]+)\)", spec_text, flags=re.IGNORECASE)
        if m_chk_explicit:
            check_expr = m_chk_explicit.group(1).strip()
        else:
            # Buscar expresiones de validación entre paréntesis como (cuota_mensual >= 0) o (num_horas <= 3, o num_horas BETWEEN 1 AND 3)
            for paren_m in re.finditer(r"\(([^()]{3,120})\)", spec_text):
                inner = paren_m.group(1).strip()
                if re.search(r"(?:>=|<=|<>|!=|>|<|\bBETWEEN\b|\bIN\s*\()", inner, flags=re.IGNORECASE):
                    # Si ofrece dos alternativas separadas por ", o ", preferir la más completa (ej. BETWEEN)
                    parts_or = re.split(r",\s*o\s+", inner, flags=re.IGNORECASE)
                    if len(parts_or) > 1:
                        best = next((p.strip() for p in parts_or if "BETWEEN" in p.upper()), parts_or[0].strip())
                        check_expr = best
                    else:
                        check_expr = inner
                    break

        # 6. Clave foránea (FOREIGN KEY -> tabla(columna))
        is_fk = False
        fk_info: Optional[Tuple[str, str]] = None
        if re.search(r"\b(?:clave\s+foranea|foreign\s+key|referencia\s+a|apunta\s+a|references)\b", norm_spec):
            is_fk = True
            # Patrón 1: "referencia a [la columna] cod_instalacion de [la] tabla INSTALACION"
            m_fk1 = re.search(
                r"(?:referencia|apunta)\s+a\s+(?:(?:la\s+)?columna\s+|(?:el\s+)?campo\s+)?[`\"']?([a-zA-Z_][a-zA-Z0-9_]*)[`\"']?\s+de\s+(?:la\s+)?tabla\s+[`\"']?([a-zA-Z_][a-zA-Z0-9_]*)[`\"']?",
                spec_text,
                flags=re.IGNORECASE,
            )
            # Patrón 2: "REFERENCES PISTA(cod_pista)" o "tabla PISTA(cod_pista)"
            m_fk2 = re.search(
                r"(?:REFERENCES|tabla)\s+[`\"']?([a-zA-Z_][a-zA-Z0-9_]*)[`\"']?\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)",
                spec_text,
                flags=re.IGNORECASE,
            )
            if m_fk1:
                fk_info = (m_fk1.group(2).strip(), m_fk1.group(1).strip())
            elif m_fk2:
                fk_info = (m_fk2.group(1).strip(), m_fk2.group(2).strip())

        tutor_desc = (
            f"Columna calculada automáticamente a partir de `{computed_expr}` (no requiere inserción manual)."
            if computed_expr
            else f"Columna '{col_name}' ({data_type}{f'({length})' if length else ''}) definida explícitamente en '{table_name}'."
        )

        col = ColumnModel(
            name=col_name,
            data_type=data_type,
            length=length,
            nullable=nullable,
            default_value=default_val,
            is_pk=is_pk,
            is_fk=is_fk,
            is_unique=is_unique,
            auto_increment=auto_inc,
            check_constraint=check_expr,
            computed_expression=computed_expr,
            computed_storage="VIRTUAL",
            fk_target_table=fk_info[0] if fk_info else None,
            fk_target_column=fk_info[1] if fk_info else None,
            description=spec_text[:140],
            tutor_explanation=tutor_desc,
        )
        return col, fk_info
