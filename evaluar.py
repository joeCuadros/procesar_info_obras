import os, json, time, statistics, warnings
from datetime import datetime
import numpy as np
import psycopg2
from dotenv import load_dotenv

warnings.filterwarnings("ignore", category=UserWarning)
from fastembed import TextEmbedding

load_dotenv()

# Config 
MODELO_ID   = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
TOP_K_LISTA = [1, 3, 5, 10]
MAX_K       = max(TOP_K_LISTA)
UMBRAL_SIM  = 0.50
N_CASOS     = 200
GT_SIZE     = 10
EXPORT_JSON = "resultados_evaluacion.json"

DSN = {
    "host":     os.getenv("POSTGRES_HOST", "localhost"),
    "port":     int(os.getenv("POSTGRES_PORT", 5432)),
    "dbname":   os.getenv("POSTGRES_DB"),
    "user":     os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

# Helpers 
def log(msg, tipo="INFO"):
    c = {"INFO":"\033[32m","WARN":"\033[33m","ERR":"\033[31m"}.get(tipo,"\033[0m")
    print(f"{c}[{tipo}] {msg}\033[0m")

def conectar():
    conn = psycopg2.connect(**DSN)
    conn.autocommit = True
    return conn

def normalizar(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 0 else v

def parse_vec(v) -> np.ndarray:
    if isinstance(v, str):
        return np.array(json.loads(v), dtype="float32")
    return np.array(v, dtype="float32")

# Carga de catalogos (para enriquecer query) 
def cargar_catalogos(cur) -> tuple[dict, dict]:
    cur.execute("SELECT id, nombre FROM cat_clasificador_n1;")
    cats = {r[0]: r[1] for r in cur.fetchall()}
    cur.execute("SELECT id, nombre FROM cat_departamento;")
    deptos = {r[0]: r[1] for r in cur.fetchall()}
    return cats, deptos

# Carga de casos 
def cargar_casos(cur, n: int) -> list[dict]:
    cur.execute("""
        SELECT o.codigo_infobras,
               o.nombre_obra,
               o.clasificador_n1_id,
               o.departamento_id,
               e.vector
        FROM   obras o
        JOIN   embeddings e ON e.obra_id = o.id
        WHERE  o.nombre_obra        IS NOT NULL
          AND  o.clasificador_n1_id IS NOT NULL
          AND  o.departamento_id    IS NOT NULL
        ORDER  BY RANDOM()
        LIMIT  %s;
    """, (n,))
    return [
        {
            "codigo":   int(r[0]),
            "titulo":   r[1].strip(),
            "cat_n1":   int(r[2]),
            "depto":    int(r[3]),
            "vec_orig": normalizar(parse_vec(r[4])),
        }
        for r in cur.fetchall()
    ]

# GT semantico top-N dentro de misma categoria
def construir_gt(cur, caso: dict, gt_size: int) -> set[int]:
    vec_str = "[" + ",".join(f"{x:.6f}" for x in caso["vec_orig"].tolist()) + "]"
    cur.execute("""
        SELECT o.codigo_infobras
        FROM   embeddings e
        JOIN   obras o ON o.id = e.obra_id
        WHERE  o.clasificador_n1_id = %s
          AND  o.codigo_infobras   != %s
        ORDER  BY e.vector <=> %s::vector
        LIMIT  %s;
    """, (caso["cat_n1"], caso["codigo"], vec_str, gt_size))
    return {int(r[0]) for r in cur.fetchall()}

# Busqueda filtrada por categoria
def buscar_filtrado(cur, vec: np.ndarray, cat_n1: int, top_k: int) -> list[tuple]:
    """
    Busca solo dentro de la misma categoría n1.
    Más justo: evalúa si el modelo rankea bien dentro del mismo dominio.
    Retorna [(codigo, score, cat_n1_id, departamento_id)].
    """
    vec_str = "[" + ",".join(f"{x:.6f}" for x in vec.tolist()) + "]"
    cur.execute("""
        SELECT o.codigo_infobras,
               1 - (e.vector <=> %s::vector) AS score,
               o.clasificador_n1_id,
               o.departamento_id
        FROM   embeddings e
        JOIN   obras o ON o.id = e.obra_id
        WHERE  o.clasificador_n1_id = %s
        ORDER  BY e.vector <=> %s::vector
        LIMIT  %s;
    """, (vec_str, cat_n1, vec_str, top_k))
    return cur.fetchall()

# Metricas 
def recall_at_k(rel, cods, k):
    hits = sum(1 for c in cods[:k] if c in rel)
    return hits / min(len(rel), k) if rel else 0.0

def precision_at_k(rel, cods, k):
    return sum(1 for c in cods[:k] if c in rel) / k

def ndcg_at_k(rel, cods, k):
    dcg  = sum(1/np.log2(i+2) for i,c in enumerate(cods[:k]) if c in rel)
    idcg = sum(1/np.log2(i+2) for i in range(min(len(rel), k)))
    return dcg/idcg if idcg else 0.0

def avg_precision(rel, cods):
    hits = s = 0
    for i, c in enumerate(cods, 1):
        if c in rel:
            hits += 1
            s    += hits / i
    return s / len(rel) if rel else 0.0

def ild(res, k):
    top = res[:k]
    if not top: return 0.0, 0.0
    b = len(top)
    return (
        len({r[2] for r in top if r[2]}) / b,
        len({r[3] for r in top if r[3]}) / b,
    )

def spread(scores, k):
    top = scores[:k]
    return float(np.std(top)) if len(top) > 1 else 0.0

# Construccion de query enriquecida 
def build_query(caso: dict, cats: dict, deptos: dict) -> str:
    """
    Enriquece el título con categoría y departamento.
    Acerca el embedding de la query al espacio del texto original.
    Ejemplo: "MEJORAMIENTO DE PISTAS Y VEREDAS | Transportes Y Comunicaciones | Lima"
    """
    cat_name   = cats.get(caso["cat_n1"], "")
    depto_name = deptos.get(caso["depto"], "")
    partes = [caso["titulo"]]
    if cat_name:   partes.append(cat_name)
    if depto_name: partes.append(depto_name)
    return " | ".join(partes)

# Evaluacion 
def evaluar(casos, vectores_query, cur) -> dict:

    acum = {k: {
        "recall":[], "prec":[], "hr":[], "ndcg":[],
        "ild_cat":[], "ild_dep":[], "spread":[]
    } for k in TOP_K_LISTA}

    mrr_l, ap_l, lat_l, sim1_l, cons_l, fallos = [], [], [], [], [], []
    score_gaps = []   # similitud top-1 GT vs posición real

    for i, (caso, vec_q) in enumerate(zip(casos, vectores_query), 1):

        gt = construir_gt(cur, caso, GT_SIZE)
        if not gt:
            print(f"\r  {i:>4}/{len(casos)} [skip]", end="", flush=True)
            continue

        t0  = time.perf_counter()
        res = buscar_filtrado(cur, vec_q, caso["cat_n1"], MAX_K)
        lat_l.append((time.perf_counter() - t0) * 1000)

        cods   = [int(r[0]) for r in res]
        scores = [float(r[1]) for r in res]

        fallos.append(0 if (scores and scores[0] >= UMBRAL_SIM) else 1)
        if scores: sim1_l.append(scores[0])

        # Score gap: score del primer GT encontrado vs score top-1
        first_gt_score = next((scores[j] for j,c in enumerate(cods) if c in gt), None)
        if first_gt_score and scores:
            score_gaps.append(scores[0] - first_gt_score)

        # Consistencia
        res2  = buscar_filtrado(cur, vec_q, caso["cat_n1"], 5)
        cods2 = [int(r[0]) for r in res2]
        cons_l.append(len(set(cods[:5]) & set(cods2)) / max(len(cods[:5]), 1))

        mrr_l.append(next((1/(j+1) for j,c in enumerate(cods) if c in gt), 0.0))
        ap_l.append(avg_precision(gt, cods))

        for k in TOP_K_LISTA:
            ic, id_ = ild(res, k)
            acum[k]["recall"].append(recall_at_k(gt, cods, k))
            acum[k]["prec"].append(precision_at_k(gt, cods, k))
            acum[k]["hr"].append(1.0 if any(c in gt for c in cods[:k]) else 0.0)
            acum[k]["ndcg"].append(ndcg_at_k(gt, cods, k))
            acum[k]["ild_cat"].append(ic)
            acum[k]["ild_dep"].append(id_)
            acum[k]["spread"].append(spread(scores, k))

        print(f"\r  {i:>4}/{len(casos)}", end="", flush=True)

    print()
    m = lambda lst: round(statistics.mean(lst), 4) if lst else 0.0

    return {
        "fecha":             datetime.now().isoformat(),
        "modelo":            MODELO_ID,
        "total_queries":     len(casos),
        "queries_efectivas": len(mrr_l),
        "gt_size":           GT_SIZE,
        "umbral":            UMBRAL_SIM,
        "metodologia":       f"query_enriquecida(titulo+cat+depto) → busqueda_filtrada_por_cat | GT=top{GT_SIZE}_semantico",
        "metricas": {
            "MRR":             m(mrr_l),
            "MAP":             m(ap_l),
            "Latencia_P50_ms": round(float(np.percentile(lat_l,50)),2) if lat_l else 0,
            "Latencia_P95_ms": round(float(np.percentile(lat_l,95)),2) if lat_l else 0,
            "Similitud_top1":  m(sim1_l),
            "Score_gap_avg":   m(score_gaps),
            "Tasa_fallos_%":   round(sum(fallos)/len(fallos)*100,2) if fallos else 0,
            "Consistencia":    m(cons_l),
        },
        "por_k": {
            str(k): {
                f"Recall@{k}":    m(acum[k]["recall"]),
                f"Precision@{k}": m(acum[k]["prec"]),
                f"HitRate@{k}":   m(acum[k]["hr"]),
                f"NDCG@{k}":      m(acum[k]["ndcg"]),
                f"ILD_dep@{k}":   m(acum[k]["ild_dep"]),
                f"Spread@{k}":    m(acum[k]["spread"]),
            } for k in TOP_K_LISTA
        },
    }

# Cobertura
def cobertura(cur):
    cur.execute("SELECT COUNT(*) FROM obras;")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT obra_id) FROM embeddings;")
    con = cur.fetchone()[0]
    return total, con

# Reporte
def reporte(res, total, con_emb):
    if not res: return
    sep = "─" * 60
    pct = round(con_emb/total*100,1) if total else 0

    def sem(v, b, g, inv=False):
        ok = v <= g if inv else v >= g
        mid= v <= b if inv else v >= b
        if ok:  return f"{v}  (ok)"
        if mid: return f"{v}  (mid)"
        return        f"{v}  (X)"

    m = res["metricas"]
    print(f"\n{sep}")
    print(f"  Evaluación RAG — Obras Públicas  (v5 · query enriquecida)")
    print(f"  Modelo : {res['modelo']}")
    print(f"  Método : {res['metodologia']}")
    print(f"  Fecha  : {res['fecha'][:19]}")
    print(f"  Queries: {res['queries_efectivas']} / {res['total_queries']}")
    print(f"  GT     : top-{res['gt_size']} vecinos semánticos por categoría")
    print(sep)
    print(f"  Cobertura: {con_emb:,} / {total:,}  ({pct}%)")
    print(sep)
    print(f"\n  {'Métrica':<24} {'Valor':>8}   Estado")
    print(f"  {'─'*24} {'─'*8}   {'─'*12}")
    print(f"  {'MRR':<24} {sem(m['MRR'],          0.30, 0.55)}")
    print(f"  {'MAP':<24} {sem(m['MAP'],          0.15, 0.35)}")
    print(f"  {'Latencia P50 ms':<24} {m['Latencia_P50_ms']:>8}")
    print(f"  {'Latencia P95 ms':<24} {m['Latencia_P95_ms']:>8}")
    print(f"  {'Similitud top-1':<24} {sem(m['Similitud_top1'],  0.65, 0.80)}")
    print(f"  {'Score gap (top1-GTtop1)':<24} {sem(m['Score_gap_avg'],  0.0, 0.05, inv=True)}")
    print(f"  {'Tasa fallos %':<24} {m['Tasa_fallos_%']:>8}")
    print(f"  {'Consistencia':<24} {sem(m['Consistencia'],    0.90, 1.00)}")

    print(f"\n  {'K':<3} {'Recall':>7} {'Prec':>7} {'Hit':>7} {'NDCG':>7} {'ILD_d':>6} {'Spread':>7}")
    print(f"  {'─'*3} {'─'*7} {'─'*7} {'─'*7} {'─'*7} {'─'*6} {'─'*7}")
    for k, kv in res["por_k"].items():
        v = list(kv.values())
        print(f"  {k:<3} {v[0]:>7} {v[1]:>7} {v[2]:>7} {v[3]:>7} {v[4]:>6} {v[5]:>7}")

    print(f"""
  Guía:
    Score gap ≈ 0   → el modelo rankea el GT casi igual que top-1 (ok)
    Score gap > 0.1 → el modelo prefiere obras fuera del GT (X)
    HitRate@10      → métrica más útil para RAG en producción
    ILD_dep@K       → diversidad geográfica en top-K
  → {EXPORT_JSON}""")
    print(sep + "\n")

def main():
    log("Conectando a PostgreSQL...")
    conn = conectar()
    cur  = conn.cursor()

    total, con_emb = cobertura(cur)
    log(f"Obras: {total:,} | Con embedding: {con_emb:,}")

    log("Cargando catálogos para enriquecer queries...")
    cats, deptos = cargar_catalogos(cur)
    log(f"Categorías n1: {len(cats)} | Departamentos: {len(deptos)}")

    log(f"Cargando {N_CASOS} casos con vector original...")
    casos = cargar_casos(cur, N_CASOS)
    log(f"Casos cargados: {len(casos)}")

    log(f"Embebiendo queries enriquecidas (título + categoría + depto)...")
    model = TextEmbedding(model_name=MODELO_ID)
    queries = [build_query(c, cats, deptos) for c in casos]
    log(f"Ejemplo de query: '{queries[0]}'")
    vectores_query = np.array([
        normalizar(np.array(v, dtype="float32"))
        for v in model.embed(queries)
    ])
    log("Embeddings generados.")

    log(f"Evaluando con GT semántico top-{GT_SIZE}...")
    res = evaluar(casos, vectores_query, cur)

    if res:
        res["cobertura"] = {"total": total, "con_embedding": con_emb}
        reporte(res, total, con_emb)
        with open(EXPORT_JSON, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        log(f"Exportado → {EXPORT_JSON}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()