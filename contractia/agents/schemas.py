"""
Esquemas Pydantic para las salidas de los agentes.
"""

from typing import List

from pydantic import BaseModel, Field


class SalidaJurista(BaseModel):
    referencias_externas: List[str] = Field(
        description="Lista de leyes, decretos, códigos o artículos externos mencionados."
    )


class Hallazgo(BaseModel):
    clausula_afectada: str = Field(description="Número específico de la cláusula (ej. '5.1').")
    tipo: str = Field(description="Tipo de error.")
    cita: str = Field(description="Texto exacto.")
    explicacion: str = Field(description="Detalle del error.")
    severidad: str = Field(description="ALTA, MEDIA, BAJA")


class SalidaAuditor(BaseModel):
    hay_inconsistencias: bool
    hallazgos: List[Hallazgo]


class SalidaCronista(BaseModel):
    hay_procedimientos: bool
    hay_errores_logicos: bool
    hay_inconsistencia_plazos: bool
    hallazgos_procesos: List[Hallazgo]
