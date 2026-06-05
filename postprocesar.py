import os
import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime

load_dotenv()

#Configuracion
BASE = Path("data")
PARQUET_OBRAS = BASE / "DataSet-Obras-Publicas 04-06-2026.parquet" #SQL
PARQUET_EMBEDS = BASE / "embeddings_output.parquet" #vectores
BATCH = 500
DIMS = 384

DSN = {
    "host":     os.getenv("POSTGRES_HOST", "localhost"),
    "port":     int(os.getenv("POSTGRES_PORT", 5432)),
    "dbname":   os.getenv("POSTGRES_DB"),
    "user":     os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

# Funciones
def imprimir_log(texto, tipo="INFO"):
    colores = {
        "INFO": "\033[32m",      # Verde
        "WARNING": "\033[33m",   # Amarillo
        "ERROR": "\033[31m"      # Rojo
    }
    color = colores.get(tipo.upper(), "\033[0m")
    print(f"{color}[{tipo.upper()}] {texto}\033[0m")

def limpio(v):
    if v is None: return None
    s = str(v).strip()
    return None if s.lower() in ("nan", "none", "") else s

def es_bool(v):
    return str(v).strip().lower() in ("si", "sí", "yes", "1", "true")

def upsert_catalogo(cur, tabla, nombre):
    cur.execute(
        f"INSERT INTO {tabla}(nombre) VALUES (%s) ON CONFLICT(nombre) DO NOTHING",
        (nombre,)
    )
    cur.execute(f"SELECT id FROM {tabla} WHERE nombre = %s", (nombre,))
    return cur.fetchone()[0]

def upsert_catalogo2(cur, tabla, nombre, fk_col, fk_val):
    cur.execute(
        f"INSERT INTO {tabla}(nombre, {fk_col}) VALUES (%s,%s) "
        f"ON CONFLICT(nombre, {fk_col}) DO NOTHING",
        (nombre, fk_val)
    )
    cur.execute(
        f"SELECT id FROM {tabla} WHERE nombre=%s AND {fk_col}=%s",
        (nombre, fk_val)
    )
    return cur.fetchone()[0]

def parsear_fecha(valor):
    s = limpio(valor)
    if s is None:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None 

# Carga de datos 
imprimir_log("[1/4] Cargando parquets ...")
cols_obras = [
    "Código INFOBRAS", "Nombre de obra", "Nombre proyecto", "Entidad Pública",
    "Departamento", "Provincia", "Distrito",
    "Sector de la Entidad", "Nivel de gobierno",
    "Tipo de obra - Clasificador Nivel 1",
    "Tipo de obra - Clasificador Nivel 2",
    "Tipo de obra - Clasificador Nivel 3",
    "Estado de ejecución", "Modalidad de ejecución de la obra",
    "Naturaleza de la obra",
    "Existe Paralización", "Marca Reconstrucción con Cambios (Si/No)",
    "Marca Reactivación Economicas (Si/No)",
    "Dirección o información de referencia",
    "Nombre o razón social de la empresa o consorcio",
    "Motivo en caso no se llegue al 100%",
    "Causal de paralización", "Comentarios", "Estado del proyecto",
    "Fecha de inicio de obra", "Fecha de finalización real",
    "texto_embedding",
]
# Solo carga columnas que existan
df_obras   = pd.read_parquet(PARQUET_OBRAS)
cols_exist = [c for c in cols_obras if c in df_obras.columns]
df_obras   = df_obras[cols_exist].copy()

df_emb     = pd.read_parquet(PARQUET_EMBEDS)
vcols      = [f"v{i}" for i in range(DIMS)]
imprimir_log(f"Obras: {len(df_obras):,} | Embeddings: {len(df_emb):,}")

#  Conexión 
imprimir_log("[2/4] Conectando a PostgreSQL ...")
conn = psycopg2.connect(**DSN)
conn.autocommit = False
cur  = conn.cursor()

#  Migración de catalogos
imprimir_log("[3/4] Poblando catálogos ...")

cache = {t: {} for t in [
    "cat_departamento", "cat_provincia", "cat_distrito",
    "cat_sector", "cat_nivel_gobierno", "cat_naturaleza",
    "cat_modalidad", "cat_estado_ejecucion",
    "cat_clasificador_n1", "cat_clasificador_n2", "cat_clasificador_n3",
]}

def get_or_create(tabla, nombre, fk_col=None, fk_val=None):
    key = (nombre, fk_val)
    if key not in cache[tabla]:
        if fk_col:
            cache[tabla][key] = upsert_catalogo2(cur, tabla, nombre, fk_col, fk_val)
        else:
            cache[tabla][key] = upsert_catalogo(cur, tabla, nombre)
    return cache[tabla][key]

# Migracion de obras + embeddings
imprimir_log("[4/4] Insertando obras y embeddings ...")

obras_rows  = []
embed_rows  = []
codigos_idx = {}

# Merge por codigo
df_merged = df_obras.merge(
    df_emb[["Código INFOBRAS"] + vcols],
    on="Código INFOBRAS",
    how="left"
)

total = len(df_merged)
for i, row in df_merged.iterrows():
    cod = int(row["Código INFOBRAS"])
    # Catalogos geográficos (jerarquía)
    dep_id = prov_id = dist_id = None
    dep  = limpio(row.get("Departamento"))
    prov = limpio(row.get("Provincia"))
    dist = limpio(row.get("Distrito"))
    if dep:
        dep_id  = get_or_create("cat_departamento", dep)
    if prov and dep_id:
        prov_id = get_or_create("cat_provincia", prov, "departamento_id", dep_id)
    if dist and prov_id:
        dist_id = get_or_create("cat_distrito", dist, "provincia_id", prov_id)

    # Catálogos clasificadores (jerarquía)
    n1_id = n2_id = n3_id = None
    n1 = limpio(row.get("Tipo de obra - Clasificador Nivel 1"))
    n2 = limpio(row.get("Tipo de obra - Clasificador Nivel 2"))
    n3 = limpio(row.get("Tipo de obra - Clasificador Nivel 3"))
    if n1: n1_id = get_or_create("cat_clasificador_n1", n1)
    if n2 and n1_id: n2_id = get_or_create("cat_clasificador_n2", n2, "n1_id", n1_id)
    if n3 and n2_id: n3_id = get_or_create("cat_clasificador_n3", n3, "n2_id", n2_id)

    # Otros catálogos simples
    sec_id  = get_or_create("cat_sector",           limpio(row.get("Sector de la Entidad")) or "NO ESPECIFICADO")
    niv_id  = get_or_create("cat_nivel_gobierno",   limpio(row.get("Nivel de gobierno"))    or "NO ESPECIFICADO")
    mod_id  = get_or_create("cat_modalidad",        limpio(row.get("Modalidad de ejecución de la obra")) or "NO ESPECIFICADO")
    nat_id  = get_or_create("cat_naturaleza",       limpio(row.get("Naturaleza de la obra")) or "NO ESPECIFICADO")
    est_id  = get_or_create("cat_estado_ejecucion", limpio(row.get("Estado de ejecución"))   or "NO ESPECIFICADO")

    obras_rows.append((
        cod,
        limpio(row.get("Nombre de obra")),
        limpio(row.get("Nombre proyecto")),
        limpio(row.get("Entidad Pública")),
        dep_id, prov_id, dist_id,
        sec_id, niv_id,
        n1_id, n2_id, n3_id,
        est_id, mod_id, nat_id,
        es_bool(row.get("Existe Paralización")),
        es_bool(row.get("Marca Reconstrucción con Cambios (Si/No)")),
        es_bool(row.get("Marca Reactivación Economicas (Si/No)")),
        limpio(row.get("Dirección o información de referencia")),
        limpio(row.get("Nombre o razón social de la empresa o consorcio")),
        limpio(row.get("Motivo en caso no se llegue al 100%")),
        limpio(row.get("Causal de paralización")),
        limpio(row.get("Comentarios")),
        limpio(row.get("Estado del proyecto")),
        parsear_fecha(row.get("Fecha de inicio de obra")),
        parsear_fecha(row.get("Fecha de finalización real")),
        limpio(row.get("texto_embedding")),
    ))

    # Insertar en batches
    if len(obras_rows) >= BATCH or i == total - 1:
        execute_values(cur, """
            INSERT INTO obras (
                codigo_infobras, nombre_obra, nombre_proyecto, entidad_publica,
                departamento_id, provincia_id, distrito_id,
                sector_id, nivel_gobierno_id,
                clasificador_n1_id, clasificador_n2_id, clasificador_n3_id,
                estado_ejecucion_id, modalidad_id, naturaleza_id,
                existe_paralizacion, marca_reconstruccion, marca_reactivacion,
                direccion, empresa_contratista, motivo_no_100,
                causal_paralizacion, comentarios, estado_proyecto,
                fecha_inicio_obra, fecha_fin_real, texto_embedding
            ) VALUES %s
            ON CONFLICT (codigo_infobras) DO NOTHING
            RETURNING id, codigo_infobras
        """, obras_rows)

        for obra_id, cod_ret in cur.fetchall():
            codigos_idx[cod_ret] = obra_id

        obras_rows = []
        imprimir_log(f"   {min(i+1, total):>7,} / {total:,}")

conn.commit()
imprimir_log(f"Obras procesadas: {total:,}")

# Recuperar IDs reales de TODAS las obras (incluyendo las que ya existían)
imprimir_log("Recuperando IDs de obras desde la BD ...")
cur.execute("SELECT codigo_infobras, id FROM obras")
codigos_idx = {int(cod): oid for cod, oid in cur.fetchall()}
imprimir_log(f"IDs recuperados: {len(codigos_idx):,}")

# Embeddings 
imprimir_log("Insertando vectores ...")

codigos_emb = df_emb["Código INFOBRAS"].astype(int).values
vectores    = df_emb[vcols].values.astype("float32")

total_emb  = len(df_emb)
embed_buf  = []
insertados = 0
sin_match  = 0

for i in range(total_emb):
    cod     = int(codigos_emb[i])
    obra_id = codigos_idx.get(cod)
    if obra_id is None:
        sin_match += 1
        continue

    embed_buf.append((obra_id, vectores[i].tolist()))

    if len(embed_buf) >= BATCH:
        execute_values(
            cur,
            "INSERT INTO embeddings(obra_id, vector) VALUES %s ON CONFLICT DO NOTHING",
            embed_buf,
            template="(%s, %s::vector)"
        )
        conn.commit()
        insertados += len(embed_buf)
        embed_buf  = []
        imprimir_log(f"   {insertados:>7,} / {total_emb:,}")

if embed_buf:
    execute_values(
        cur,
        "INSERT INTO embeddings(obra_id, vector) VALUES %s ON CONFLICT DO NOTHING",
        embed_buf,
        template="(%s, %s::vector)"
    )
    conn.commit()
    insertados += len(embed_buf)
    imprimir_log(f"   {insertados:>7,} / {total_emb:,}")

cur.close()
conn.close()
imprimir_log(f"Migración completada — {insertados:,} embeddings | {sin_match:,} sin match.")