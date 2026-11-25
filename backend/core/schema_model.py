"""
Definición estricta del Contrato Maestro JSON (Single Source of Truth) de SGBD-Smart.
Comunica el motor de inferencia NLP, el lienzo visual ER, el auditor proactivo,
el transpilador multi-dialecto, el motor SQLite y el Modo Tutor.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class ColumnModel(BaseModel):
    name: str = Field(..., description="Nombre de la columna en snake_case")
    data_type: str = Field(
        default="VARCHAR",
        description="Tipo SQL canónico: INTEGER, VARCHAR, DECIMAL(10,2), DATE, DATETIME, BOOLEAN, TEXT, FLOAT",
    )
    length: Optional[int] = Field(default=None, description="Longitud para VARCHAR si aplica")
    nullable: bool = Field(default=True, description="Permite valores NULL")
    default_value: Optional[str] = Field(default=None, description="Valor por defecto SQL")
    is_pk: bool = Field(default=False, description="Es clave primaria")
    is_fk: bool = Field(default=False, description="Es clave foránea")
    is_unique: bool = Field(default=False, description="Tiene restricción UNIQUE")
    auto_increment: bool = Field(default=False, description="Autoincremental")
    check_constraint: Optional[str] = Field(default=None, description="Expresión CHECK opcional")
    computed_expression: Optional[str] = Field(
        default=None,
        description="Expresión de columna calculada/generada (ej. largo * ancho)",
    )
    computed_storage: Literal["VIRTUAL", "STORED"] = Field(
        default="VIRTUAL",
        description="Modo de almacenamiento de columna calculada (VIRTUAL o STORED)",
    )
    fk_target_table: Optional[str] = Field(default=None, description="Tabla destino si es FK")
    fk_target_column: Optional[str] = Field(default=None, description="Columna destino si es FK")
    description: str = Field(default="", description="Descripción funcional de la columna")
    tutor_explanation: str = Field(
        default="",
        description="Explicación didáctica contextual para el Modo Tutor",
    )


class TableModel(BaseModel):
    name: str = Field(..., description="Nombre de la tabla en snake_case plural o singular coherente")
    description: str = Field(default="", description="Propósito funcional de la entidad")
    is_associative: bool = Field(
        default=False,
        description="Indica si es una tabla intermedia generada para resolver una relación N:M",
    )
    is_historical: bool = Field(
        default=False,
        description="Indica si almacena registros históricos o contables (facturas, pagos, pedidos, ventas, reparaciones)",
    )
    position_x: float = Field(default=80.0, description="Coordenada X en el lienzo ER")
    position_y: float = Field(default=80.0, description="Coordenada Y en el lienzo ER")
    primary_key: List[str] = Field(
        default_factory=list,
        description="Columnas que conforman la clave primaria (simple o compuesta)",
    )
    columns: List[ColumnModel] = Field(default_factory=list)
    indexes: List[str] = Field(
        default_factory=list,
        description="Nombres de columnas que cuentan con un índice explícito idx_<table>_<col>",
    )
    tutor_explanation: str = Field(
        default="",
        description="Explicación didáctica del rol de esta tabla en el modelo relacional",
    )


class RelationModel(BaseModel):
    id: str = Field(..., description="Identificador único de la relación")
    source_table: str = Field(..., description="Tabla que contiene la clave foránea (lado N o hija)")
    source_column: str = Field(..., description="Columna clave foránea en la tabla origen")
    target_table: str = Field(..., description="Tabla referenciada (lado 1 o padre)")
    target_column: str = Field(default="id", description="Columna clave primaria/única en la tabla destino")
    cardinality: Literal["1:1", "1:N", "N:M"] = Field(default="1:N")
    on_delete: Literal["RESTRICT", "CASCADE", "SET NULL", "NO ACTION"] = Field(default="RESTRICT")
    on_update: Literal["RESTRICT", "CASCADE", "SET NULL", "NO ACTION"] = Field(default="CASCADE")
    via_table: Optional[str] = Field(
        default=None,
        description="Nombre de la tabla asociativa si forma parte de una relación N:M",
    )
    tutor_explanation: str = Field(
        default="",
        description="Explicación pedagógica de la relación y su política de integridad referencial",
    )


class AuditAlertModel(BaseModel):
    id: str
    severity: Literal["critical", "warning", "suggestion", "info"] = "warning"
    category: Literal[
        "integridad_claves",
        "normalizacion_1fn",
        "tipos_datos",
        "cascada_peligrosa",
        "rendimiento_indices",
        "escudo_ejecucion",
    ]
    title: str
    technical_message: str
    affected_table: Optional[str] = None
    affected_column: Optional[str] = None
    affected_relation_id: Optional[str] = None
    auto_fix_action: Optional[str] = None
    auto_fix_label: Optional[str] = None
    auto_fix_payload: Dict[str, Any] = Field(default_factory=dict)
    tutor_lesson: Dict[str, Any] = Field(default_factory=dict)


class MasterSchemaContract(BaseModel):
    db_name: str = Field(default="proyecto_chemysql", description="Nombre técnico del archivo .db (sin extensión)")
    title: str = Field(default="Nuevo Proyecto Relacional", description="Título legible del proyecto")
    description: str = Field(default="", description="Resumen funcional del proyecto")
    source_prompt: str = Field(default="", description="Descripción en lenguaje natural original")
    dialect: Literal["sqlite", "mysql", "postgresql", "sqlserver"] = Field(default="sqlite")
    collation: Optional[str] = Field(
        default=None,
        description="Cotejamiento de base de datos (ej. utf8mb4_0900_ai_ci, utf8mb4_spanish_ci, Modern_Spanish_CI_AI)",
    )
    is_deployed: bool = Field(default=False, description="Indica si el esquema actual ya fue desplegado en disco")
    version: int = Field(default=1, description="Versión incremental del esquema")
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    tables: List[TableModel] = Field(default_factory=list)
    relations: List[RelationModel] = Field(default_factory=list)
    audit_alerts: List[AuditAlertModel] = Field(default_factory=list)
    tutor_metadata: Dict[str, Any] = Field(default_factory=dict)


class NLPInferenceRequest(BaseModel):
    text: str = Field(..., description="Descripción en texto libre en español")
    db_name: Optional[str] = Field(default=None)
    dialect: Literal["sqlite", "mysql", "postgresql", "sqlserver"] = "sqlite"


class AutoFixRequest(BaseModel):
    schema_contract: MasterSchemaContract
    alert_id: str


class DeploySchemaRequest(BaseModel):
    schema_contract: MasterSchemaContract
    populate_mock_data: bool = False
    mock_rows_per_table: int = 12


class MockDataRequest(BaseModel):
    db_name: str
    rows_per_table: int = 15


class QueryExecutionRequest(BaseModel):
    db_name: str
    sql: str
    confirmed_dangerous: bool = False
    page: int = 1
    page_size: int = 50


class CellUpdateRequest(BaseModel):
    db_name: str
    table_name: str
    pk_column: Optional[str] = None
    pk_value: Any = None
    pk_values: Optional[Dict[str, Any]] = None
    target_column: str
    new_value: Any


class RowInsertRequest(BaseModel):
    db_name: str
    table_name: str
    values: Dict[str, Any]


class CreateIndexRequest(BaseModel):
    db_name: str
    table_name: str
    column_name: str
    schema_contract: Optional[MasterSchemaContract] = None


class WorkspaceSelectRequest(BaseModel):
    path: Optional[str] = None


class SaveSQLRequest(BaseModel):
    content: str = ""
    path: Optional[str] = None
    filename: Optional[str] = None
    save_as: bool = False


class SaveDBAsRequest(BaseModel):
    db_name: str


class ParseDDLRequest(BaseModel):
    sql: str
    schema_contract: Optional[MasterSchemaContract] = None


class QueryDecomposeRequest(BaseModel):
    sql: str = ""
