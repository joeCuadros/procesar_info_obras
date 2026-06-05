from typing import Any, Dict, List, Optional
from fastapi import FastAPI, APIRouter, Query
from psycopg2.extras import RealDictCursor
from fastembed import TextEmbedding
from fastapi.responses import FileResponse

from schemas import (
    DepartamentoSchema,
    ProvinciaSchema,
    DistritoSchema,
    SectorSchema,
    NivelGobiernoSchema,
    ClasificadorN1Schema,
    ClasificadorN2Schema,
    ClasificadorN3Schema,
    EstadoEjecucionSchema,
    ModalidadSchema,
    NaturalezaSchema,
    ObraBusquedaRequest,
    ObraBusquedaOut,
)

from db import get_conn, put_conn


app = FastAPI(title="Obras API")

router_select = APIRouter(prefix="/select", tags=["select"])
router_obras = APIRouter(prefix="/obras", tags=["obras"])


EMBED_MODEL = TextEmbedding(
    model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)


BASE_SELECT = """SELECT o.id,o.codigo_infobras,o.nombre_obra,o.nombre_proyecto,o.entidad_publica,o.departamento_id,d.nombre AS departamento_nombre,o.provincia_id,p.nombre AS provincia_nombre,o.distrito_id,di.nombre AS distrito_nombre,o.sector_id,s.nombre AS sector_nombre,o.nivel_gobierno_id,ng.nombre AS nivel_gobierno_nombre,o.clasificador_n1_id,c1.nombre AS clasificador_n1_nombre,o.clasificador_n2_id,c2.nombre AS clasificador_n2_nombre,o.clasificador_n3_id,c3.nombre AS clasificador_n3_nombre,o.estado_ejecucion_id,ee.nombre AS estado_ejecucion_nombre,o.modalidad_id,m.nombre AS modalidad_nombre,o.naturaleza_id,n.nombre AS naturaleza_nombre,o.existe_paralizacion,o.marca_reconstruccion,o.marca_reactivacion,o.direccion,o.empresa_contratista,o.motivo_no_100,o.causal_paralizacion,o.comentarios,o.estado_proyecto,o.fecha_inicio_obra,o.fecha_fin_real,o.texto_embedding FROM obras o LEFT JOIN cat_departamento d ON d.id=o.departamento_id LEFT JOIN cat_provincia p ON p.id=o.provincia_id LEFT JOIN cat_distrito di ON di.id=o.distrito_id LEFT JOIN cat_sector s ON s.id=o.sector_id LEFT JOIN cat_nivel_gobierno ng ON ng.id=o.nivel_gobierno_id LEFT JOIN cat_clasificador_n1 c1 ON c1.id=o.clasificador_n1_id LEFT JOIN cat_clasificador_n2 c2 ON c2.id=o.clasificador_n2_id LEFT JOIN cat_clasificador_n3 c3 ON c3.id=o.clasificador_n3_id LEFT JOIN cat_estado_ejecucion ee ON ee.id=o.estado_ejecucion_id LEFT JOIN cat_modalidad m ON m.id=o.modalidad_id LEFT JOIN cat_naturaleza n ON n.id=o.naturaleza_id"""


def fetch_all(sql: str, params: Optional[list] = None):
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params or [])
            return cur.fetchall()
    finally:
        put_conn(conn)


def embed_text(texto: str):
    return list(next(EMBED_MODEL.embed([texto])))


def build_where(filters: Dict[str, Any], alias: str = "o"):
    where = []
    params = []

    def eq(f):
        v = filters.get(f)
        if v is not None:
            where.append(f"{alias}.{f}=%s")
            params.append(v)

    def like(f):
        v = filters.get(f)
        if v:
            where.append(f"{alias}.{f} ILIKE %s")
            params.append(f"%{v}%")

    for f in [
        "departamento_id","provincia_id","distrito_id","sector_id",
        "nivel_gobierno_id","clasificador_n1_id","clasificador_n2_id",
        "clasificador_n3_id","estado_ejecucion_id","modalidad_id",
        "naturaleza_id","existe_paralizacion","marca_reconstruccion","marca_reactivacion"
    ]:
        eq(f)

    for f in [
        "entidad_publica","nombre_obra","nombre_proyecto",
        "empresa_contratista","estado_proyecto"
    ]:
        like(f)

    return ("WHERE " + " AND ".join(where), params) if where else ("", params)


# SELECTS (CATALOGOS)

@router_select.get("/departamentos", response_model=List[DepartamentoSchema])
def departamentos():
    """Lista de departamentos"""
    return fetch_all("SELECT id,nombre FROM cat_departamento ORDER BY nombre")


@router_select.get("/provincias", response_model=List[ProvinciaSchema])
def provincias(departamento_id: int = Query(..., ge=1)):
    """Lista de provincias por departamento"""
    return fetch_all(
        "SELECT id,nombre,departamento_id FROM cat_provincia WHERE departamento_id=%s ORDER BY nombre",
        [departamento_id],
    )


@router_select.get("/distritos", response_model=List[DistritoSchema])
def distritos(provincia_id: int = Query(..., ge=1)):
    """Lista de distritos por provincia"""
    return fetch_all(
        "SELECT id,nombre,provincia_id FROM cat_distrito WHERE provincia_id=%s ORDER BY nombre",
        [provincia_id],
    )


@router_select.get("/sectores", response_model=List[SectorSchema])
def sectores():
    """Lista de sectores"""
    return fetch_all("SELECT id,nombre FROM cat_sector ORDER BY nombre")


@router_select.get("/niveles-gobierno", response_model=List[NivelGobiernoSchema])
def niveles_gobierno():
    """Lista de niveles de gobierno"""
    return fetch_all("SELECT id,nombre FROM cat_nivel_gobierno ORDER BY nombre")


@router_select.get("/clasificador-n1", response_model=List[ClasificadorN1Schema])
def clasificador_n1():
    """Lista clasificador nivel 1"""
    return fetch_all("SELECT id,nombre FROM cat_clasificador_n1 ORDER BY nombre")


@router_select.get("/clasificador-n2", response_model=List[ClasificadorN2Schema])
def clasificador_n2(n1_id: int = Query(..., ge=1)):
    """Lista clasificador nivel 2"""
    return fetch_all(
        "SELECT id,nombre,n1_id FROM cat_clasificador_n2 WHERE n1_id=%s ORDER BY nombre",
        [n1_id],
    )


@router_select.get("/clasificador-n3", response_model=List[ClasificadorN3Schema])
def clasificador_n3(n2_id: int = Query(..., ge=1)):
    """Lista clasificador nivel 3"""
    return fetch_all(
        "SELECT id,nombre,n2_id FROM cat_clasificador_n3 WHERE n2_id=%s ORDER BY nombre",
        [n2_id],
    )


@router_select.get("/estados-ejecucion", response_model=List[EstadoEjecucionSchema])
def estados_ejecucion():
    """Lista estados de ejecución"""
    return fetch_all("SELECT id,nombre FROM cat_estado_ejecucion ORDER BY nombre")


@router_select.get("/modalidades", response_model=List[ModalidadSchema])
def modalidades():
    """Lista modalidades"""
    return fetch_all("SELECT id,nombre FROM cat_modalidad ORDER BY nombre")


@router_select.get("/naturalezas", response_model=List[NaturalezaSchema])
def naturalezas():
    """Lista naturalezas"""
    return fetch_all("SELECT id,nombre FROM cat_naturaleza ORDER BY nombre")


# BUSCADOR
@router_obras.post("/buscar", response_model=List[ObraBusquedaOut])
def buscar(req: ObraBusquedaRequest):
    """Busqueda de obras con texto + filtros + top K"""
    vector_raw = embed_text(req.texto)
    
    vector = [float(v) for v in vector_raw]
    filters = req.model_dump(exclude={"texto", "limit", "offset"})
    where_sql, where_params = build_where(filters)

    sql = f"""
    SELECT o.*,
           (e.vector <=> %s::vector(384)) AS distancia,
           1 - (e.vector <=> %s::vector(384)) AS similitud
    FROM ({BASE_SELECT}) o
    INNER JOIN embeddings e ON e.obra_id = o.id
    {where_sql}
    ORDER BY e.vector <=> %s::vector(384)
    LIMIT %s OFFSET %s
    """
    params = [vector, vector] + where_params + [vector, req.limit, req.offset]

    return fetch_all(sql, params)

# CONEXION FINAL APP
app.include_router(router_select)
app.include_router(router_obras)

# frontend
@app.get("/")
def index():
    return FileResponse("obras.html")

# Ejecuta con: uvicorn main:app --host 0.0.0.0 --port 8000 --reload