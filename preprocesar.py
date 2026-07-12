import pandas as pd
from pathlib import Path
import re, unicodedata

NOMBRE = "DataSet-Obras-Publicas 04-06-2026"
BASE = Path("data")
XLSX_PURO = BASE / f"{NOMBRE}.xlsx"
PARQUET_COMPRIMIDO = BASE / f"{NOMBRE}.parquet"
PARQUET_PROCESADO = BASE / f"Procesado-{NOMBRE}.parquet"

# Imprimir
def imprimir_log(texto, tipo="INFO"):
    colores = {
        "INFO": "\033[32m",      # Verde
        "WARNING": "\033[33m",   # Amarillo
        "ERROR": "\033[31m"      # Rojo
    }
    color = colores.get(tipo.upper(), "\033[0m")
    print(f"{color}[{tipo.upper()}] {texto}\033[0m")
############################################### Fase 0: Comprimir data para facil lectura ###############################################
if PARQUET_COMPRIMIDO.exists():
    imprimir_log("Cargando parquet...")
    df = pd.read_parquet(PARQUET_COMPRIMIDO)
else:
    imprimir_log("Parquet no encontrado: leyendo Excel..", "WARNING")
    df = pd.read_excel(
        XLSX_PURO,
        header=3
    )
    imprimir_log("Guardando parquet...")
    df.to_parquet(
        PARQUET_COMPRIMIDO,
        index=False
    )

################################################ Fase 1: Ver Resumen ###############################################
def resumen_df(df_actual: pd.DataFrame):
    resumen = []
    for col in df_actual.columns:
        serie = df_actual[col]
        total = len(serie)
        nulos = serie.isna().sum()
        porcentaje_nulos = round((nulos / total) * 100,2)
        unicos = serie.nunique(dropna=True)
        try:
            moda = serie.mode(dropna=True)
            if len(moda) > 0:
                valor_moda = str(moda.iloc[0][:15])
                frecuencia_moda = (serie == moda.iloc[0]).sum()
            else:
                valor_moda = None
                frecuencia_moda = 0
        except:
            valor_moda = None
            frecuencia_moda = 0
        resumen.append({
            "columna": col,
            "tipo": str(serie.dtype),
            "%_nulos": porcentaje_nulos,
            "valores_unicos": unicos,
            "moda": valor_moda,
            "freq_moda": frecuencia_moda
        })

    perfil = pd.DataFrame(resumen)
    perfil = perfil.sort_values(
        by=["columna"],
        ascending=True
    )
    pd.set_option("display.max_rows", None)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", None)
    pd.set_option("display.max_colwidth", 300)
    print(perfil)

imprimir_log("Analizando el dataframe ...")
resumen_df(df)

############################################### Fase 2: Mantener las columnas inservibles ###############################################
cols_mantener = [
    "Código INFOBRAS",                      
]
cols_semanticas = [
    "Nombre de obra",
    "Naturaleza de la obra",
    "Modalidad de ejecución de la obra",
    "Estado de ejecución",
    "Existe Paralización",
    "Tipo de obra - Clasificador Nivel 1",
    "Tipo de obra - Clasificador Nivel 2",
    "Tipo de obra - Clasificador Nivel 3",
    "Nivel de gobierno",
    "Sector de la Entidad",
    "Entidad Pública",
    "Departamento",
    "Provincia",
    "Distrito",
    "Dirección o información de referencia",
    "Nombre proyecto",
]
cols_opcionales = [
    "Marca Reconstrucción con Cambios (Si/No)",
    "Marca Reactivación Economicas (Si/No)",
    "Estado del proyecto",
    "Motivo en caso no se llegue al 100%",
    "Causal de paralización",
    "Nombre o razón social de la empresa o consorcio",
    "Comentarios",
]
imprimir_log("Eliminando columnas que no ayudarán en los embeddings ...")
df_semantico = df[cols_mantener + cols_semanticas + cols_opcionales].copy()

################################################ Fase 3: Construir embedings ###############################################
# Funciones secundarias
def normalizar(texto: str) -> str:
    """
    Convierte a mayúsculas y elimina tildes/diacríticos.
    Ejemplo: "Rehabilitación" → "REHABILITACION"
    """
    sin_tildes = unicodedata.normalize("NFD", texto)
    sin_tildes = "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")
    return sin_tildes.upper()

def limpiar(valor, default="NO ESPECIFICADO") -> str:
    """Retorna el valor normalizado si es válido, caso contrario el default."""
    if valor is None:
        return default
    s = str(valor).strip()
    if not s or s.lower() in ("nan", "none", "", "no aplica"):
        return default
    return normalizar(s)

def es_afirmativo(valor) -> bool:
    """True si el valor indica afirmación."""
    return str(valor).strip().lower() in ("si", "sí", "yes", "1", "true")

def limpiar_comentario(texto: str) -> str:
    """
    Limpia comentarios de texto libre sin truncar:
    - Elimina saltos de línea y tabulaciones redundantes
    - Colapsa espacios múltiples
    - Elimina caracteres de control
    """
    texto = re.sub(r"[\r\n\t]+", " ", texto)          # saltos → espacio
    texto = re.sub(r"[^\x20-\x7E\u00C0-\u024F]", "", texto)  # solo ASCII + latinos
    texto = re.sub(r" {2,}", " ", texto)               # colapsar espacios dobles
    return normalizar(texto.strip())

# Contructor de embedding
def construir_texto_embedding(row) -> str:
    """
    Construye el texto semántico normalizado (mayúsculas sin tildes)
    que será enviado al modelo de embeddings para representar una obra pública.
    Sin truncado — se limpia pero se preserva todo el contenido.
    """

    # --- Bloque principal (siempre presente) ---
    texto = (
        f"Obra \"{limpiar(row.get('Nombre de obra'))}\", "
        f"de naturaleza {limpiar(row.get('Naturaleza de la obra'))}. "
        f"Corresponde a {limpiar(row.get('Tipo de obra - Clasificador Nivel 1'))} > "
        f"{limpiar(row.get('Tipo de obra - Clasificador Nivel 2'))} > "
        f"{limpiar(row.get('Tipo de obra - Clasificador Nivel 3'))}. "
        f"Ubicada en {limpiar(row.get('Distrito'))}, "
        f"{limpiar(row.get('Provincia'))}, {limpiar(row.get('Departamento'))}."
    )
    # --- Dirección (condicional) ---
    direccion = limpiar(row.get("Dirección o información de referencia"), default="")
    if direccion:
        texto += f"REFERENCIA DE UBICACION: {direccion}. "

    # --- Estado de ejecución ---
    texto += f"ESTADO ACTUAL DE EJECUCION: {limpiar(row.get('Estado de ejecución'))}. "

    # --- Estado del proyecto (OPCIONAL) ---
    estado_proyecto = limpiar(row.get("Estado del proyecto"), default="")
    if estado_proyecto:
        texto += f"ESTADO DEL PROYECTO DE INVERSION: {estado_proyecto}. "

    # --- Paralización (OPCIONAL) ---
    if es_afirmativo(row.get("Existe Paralización")):
        texto += "LA OBRA SE ENCUENTRA ACTUALMENTE PARALIZADA."
        causal = limpiar(row.get("Causal de paralización"), default="")
        if causal:
            texto += f" CAUSAL DE PARALIZACION: {causal}."
        texto += " "

    # --- Marcas especiales (OPCIONALES) ---
    if es_afirmativo(row.get("Marca Reconstrucción con Cambios (Si/No)")):
        texto += "INCLUYE MARCA DE RECONSTRUCCION CON CAMBIOS. "

    if es_afirmativo(row.get("Marca Reactivación Economicas (Si/No)")):
        texto += "INCLUYE MARCA DE REACTIVACION ECONOMICA. "

    # --- Proyecto de inversión (OPCIONAL) ---
    nombre_proyecto = limpiar(row.get("Nombre proyecto"), default="")
    if nombre_proyecto:
        texto += f"FORMA PARTE DEL PROYECTO DE INVERSION: {nombre_proyecto}. "

    # --- Motivo de incumplimiento (OPCIONAL) ---
    motivo = limpiar(row.get("Motivo en caso no se llegue al 100%"), default="")
    if motivo and motivo not in ("OTROS", "NO ESPECIFICADO"):
        texto += f"MOTIVO DE NO ALCANZAR EL 100 POR CIENTO DE AVANCE: {motivo}. "

    # --- Empresa contratista (OPCIONAL) ---
    empresa = limpiar(row.get("Nombre o razón social de la empresa o consorcio"), default="")
    if empresa:
        texto += f"EJECUTADO POR LA EMPRESA O CONSORCIO: {empresa}. "

    # --- Comentarios libres (OPCIONAL — limpieza sin truncado) ---
    comentario_raw = str(row.get("Comentarios", "") or "").strip()
    if comentario_raw and comentario_raw.lower() not in ("nan", "none", ""):
        comentario = limpiar_comentario(comentario_raw)
        if comentario:
            texto += f"OBSERVACIONES: {comentario}"

    return texto.strip()

imprimir_log("Construyendo textos para embeddings ...")
df_semantico["texto_embedding"] = df_semantico.apply(construir_texto_embedding, axis=1)
############################################### Fase 4: Revision de calidad ###############################################
# Metricas 
total = len(df_semantico)
vacios = df_semantico["texto_embedding"].str.strip().eq("").sum()
largo_min = df_semantico["texto_embedding"].str.len().min()
largo_max = df_semantico["texto_embedding"].str.len().max()
largo_promedio = df_semantico["texto_embedding"].str.len().mean()

imprimir_log(f"Textos generados : {total - vacios:,} / {total:,}")
imprimir_log(f"Textos vacios    : {vacios}")
imprimir_log(f"Largo minimo     : {largo_min:,} caracteres")
imprimir_log(f"Largo maximo     : {largo_max:,} caracteres")
imprimir_log(f"Largo promedio   : {largo_promedio:,.0f} caracteres")

# Muestra de ejemplo
print("\n--- EJEMPLO DE TEXTO GENERADO ---")
print(df_semantico["texto_embedding"].iloc[0])
print("---------------------------------\n")
# Exportar solo las columnas necesarias para la siguiente fase
df_final = df_semantico[["Código INFOBRAS", "texto_embedding"]].copy()
imprimir_log(f"DataFrame listo para embeddings: {df_final.shape}")

#Fase 5: Exportar a un packet para google colab 
imprimir_log("Exportando parquet procesado...")
df_final.to_parquet(
    PARQUET_PROCESADO,
    index=False
)
imprimir_log(f"Archivo generado: {PARQUET_PROCESADO}")
imprimir_log(f"Registros exportados: {len(df_final):,}")