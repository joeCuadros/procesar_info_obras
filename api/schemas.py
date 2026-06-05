from typing import Optional, Literal
from datetime import date
from pydantic import BaseModel, Field
class CatalogoBase(BaseModel):
    id: int
    nombre: str
class DepartamentoSchema(CatalogoBase):
    pass
class SectorSchema(CatalogoBase):
    pass
class NivelGobiernoSchema(CatalogoBase):
    pass
class ClasificadorN1Schema(CatalogoBase):
    pass
class EstadoEjecucionSchema(CatalogoBase):
    pass
class ModalidadSchema(CatalogoBase):
    pass
class NaturalezaSchema(CatalogoBase):
    pass
class ProvinciaSchema(CatalogoBase):
    departamento_id: int
class DistritoSchema(CatalogoBase):
    provincia_id: int
class ClasificadorN2Schema(CatalogoBase):
    n1_id: int
class ClasificadorN3Schema(CatalogoBase):
    n2_id: int

class ObraCompletaSchema(BaseModel):
    id: int
    codigo_infobras: int
    nombre_obra: Optional[str] = None
    nombre_proyecto: Optional[str] = None
    entidad_publica: Optional[str] = None
    departamento_id: Optional[int] = None
    departamento_nombre: Optional[str] = None
    provincia_id: Optional[int] = None
    provincia_nombre: Optional[str] = None
    distrito_id: Optional[int] = None
    distrito_nombre: Optional[str] = None
    sector_id: Optional[int] = None
    sector_nombre: Optional[str] = None
    nivel_gobierno_id: Optional[int] = None
    nivel_gobierno_nombre: Optional[str] = None
    clasificador_n1_id: Optional[int] = None
    clasificador_n1_nombre: Optional[str] = None
    clasificador_n2_id: Optional[int] = None
    clasificador_n2_nombre: Optional[str] = None
    clasificador_n3_id: Optional[int] = None
    clasificador_n3_nombre: Optional[str] = None
    estado_ejecucion_id: Optional[int] = None
    estado_ejecucion_nombre: Optional[str] = None
    modalidad_id: Optional[int] = None
    modalidad_nombre: Optional[str] = None
    naturaleza_id: Optional[int] = None
    naturaleza_nombre: Optional[str] = None
    existe_paralizacion: bool = False
    marca_reconstruccion: bool = False
    marca_reactivacion: bool = False
    direccion: Optional[str] = None
    empresa_contratista: Optional[str] = None
    motivo_no_100: Optional[str] = None
    causal_paralizacion: Optional[str] = None
    comentarios: Optional[str] = None
    estado_proyecto: Optional[str] = None
    fecha_inicio_obra: Optional[date] = None
    fecha_fin_real: Optional[date] = None
    texto_embedding: Optional[str] = None

class ObraBusquedaRequest(BaseModel):
    texto: str = Field(..., min_length=1)
    limit: Literal[5, 10, 20] = 5
    offset: int = Field(0, ge=0)
    departamento_id: Optional[int] = None
    provincia_id: Optional[int] = None
    distrito_id: Optional[int] = None
    sector_id: Optional[int] = None
    nivel_gobierno_id: Optional[int] = None
    clasificador_n1_id: Optional[int] = None
    clasificador_n2_id: Optional[int] = None
    clasificador_n3_id: Optional[int] = None
    estado_ejecucion_id: Optional[int] = None
    modalidad_id: Optional[int] = None
    naturaleza_id: Optional[int] = None
    existe_paralizacion: Optional[bool] = None
    marca_reconstruccion: Optional[bool] = None
    marca_reactivacion: Optional[bool] = None
    entidad_publica: Optional[str] = None
    nombre_obra: Optional[str] = None
    nombre_proyecto: Optional[str] = None
    empresa_contratista: Optional[str] = None
    estado_proyecto: Optional[str] = None
    
class ObraBusquedaOut(ObraCompletaSchema):
    distancia: float
    similitud: float