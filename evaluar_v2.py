import os, json, time, statistics, warnings
from datetime import datetime
import numpy as np
import psycopg2
from dotenv import load_dotenv
warnings.filterwarnings("ignore", category=UserWarning)
from fastembed import TextEmbedding
load_dotenv()

# Config
MODELO_ID    = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
TOP_K_LISTA  = [1, 3, 5, 10]
MAX_K        = max(TOP_K_LISTA)
UMBRAL_SIM   = 0.50
TEST_JSON    = "test.json"
EXPORT_JSON  = "resultados.json"

DSN = {
    "host":     os.getenv("POSTGRES_HOST", "localhost"),
    "port":     int(os.getenv("POSTGRES_PORT", 5432)),
    "dbname":   os.getenv("POSTGRES_DB"),
    "user":     os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}


# Helpers
def log(msg, tipo="INFO"):
    c = {"INFO": "\033[32m", "WARN": "\033[33m", "ERR": "\033[31m"}.get(tipo, "\033[0m")
    print(f"{c}[{tipo}] {msg}\033[0m")


def conectar():
    conn = psycopg2.connect(**DSN)
    conn.autocommit = True
    return conn


def normalizar(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def cargar_test(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def buscar_filtrado(cur, vec: np.ndarray, cat_n1: int, top_k: int, codigo_excluir: int = None):
    """
    Busca dentro de la misma categoría n1. Si se pasa codigo_excluir, se pide
    un margen extra de resultados y se filtra en Python -- excluir por SQL con
    '!=' rompe el uso del índice ANN de pgvector y dispara la latencia.
    """
    vec_str = "[" + ",".join(f"{x:.6f}" for x in vec.tolist()) + "]"
    margen = top_k + 3 if codigo_excluir is not None else top_k
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
    """, (vec_str, cat_n1, vec_str, margen))
    filas = cur.fetchall()
    if codigo_excluir is not None:
        filas = [f for f in filas if int(f[0]) != codigo_excluir]
    return filas[:top_k]


# Métricas
def recall_at_k(rel, cods, k):
    hits = sum(1 for c in cods[:k] if c in rel)
    return hits / min(len(rel), k) if rel else 0.0


def precision_at_k(rel, cods, k):
    return sum(1 for c in cods[:k] if c in rel) / k


def ndcg_at_k(rel, cods, k):
    dcg  = sum(1 / np.log2(i + 2) for i, c in enumerate(cods[:k]) if c in rel)
    idcg = sum(1 / np.log2(i + 2) for i in range(min(len(rel), k)))
    return dcg / idcg if idcg else 0.0


def avg_precision(rel, cods):
    hits = s = 0
    for i, c in enumerate(cods, 1):
        if c in rel:
            hits += 1
            s += hits / i
    return s / len(rel) if rel else 0.0


def ild(res, k):
    top = res[:k]
    if not top:
        return 0.0, 0.0
    b = len(top)
    return (
        len({r[2] for r in top if r[2]}) / b,
        len({r[3] for r in top if r[3]}) / b,
    )


def spread(scores, k):
    top = scores[:k]
    return float(np.std(top)) if len(top) > 1 else 0.0


def normalizar_gt(raw_gt) -> set:
    """
    Acepta 'ground_truth' como lista de códigos (int) o lista de dicts
    {'codigo':.., 'titulo':..}. Resistente a formatos mixtos o inesperados.
    """
    try:
        return {int(x) for x in raw_gt}
    except (TypeError, ValueError):
        try:
            return {int(x["codigo"]) for x in raw_gt}
        except Exception:
            return set()


# Evaluación
def evaluar(casos, vectores_query, cur) -> dict:
    acum = {k: {
        "recall": [], "prec": [], "hr": [], "ndcg": [],
        "ild_cat": [], "ild_dep": [], "spread": []
    } for k in TOP_K_LISTA}
    mrr_l, ap_l, lat_l, sim1_l, cons_l, fallos = [], [], [], [], [], []
    score_gaps = []
    detalle = []

    for i, (caso, vec_q) in enumerate(zip(casos, vectores_query), 1):
        gt = normalizar_gt(caso["ground_truth"])
        if not gt:
            print(f"\r  {i:>4}/{len(casos)} [skip]", end="", flush=True)
            continue

        t0  = time.perf_counter()
        res = buscar_filtrado(cur, vec_q, caso["cat_n1"], MAX_K, codigo_excluir=caso["codigo"])
        lat_l.append((time.perf_counter() - t0) * 1000)

        cods   = [int(r[0]) for r in res]
        scores = [float(r[1]) for r in res]
        fallos.append(0 if (scores and scores[0] >= UMBRAL_SIM) else 1)
        if scores:
            sim1_l.append(scores[0])

        first_gt_score = next((scores[j] for j, c in enumerate(cods) if c in gt), None)
        if first_gt_score and scores:
            score_gaps.append(scores[0] - first_gt_score)

        res2  = buscar_filtrado(cur, vec_q, caso["cat_n1"], 5, codigo_excluir=caso["codigo"])
        cods2 = [int(r[0]) for r in res2]
        cons_l.append(len(set(cods[:5]) & set(cods2)) / max(len(cods[:5]), 1))

        mrr = next((1 / (j + 1) for j, c in enumerate(cods) if c in gt), 0.0)
        ap  = avg_precision(gt, cods)
        mrr_l.append(mrr)
        ap_l.append(ap)

        caso_metricas = {"id_caso": caso["id_caso"], "query": caso["query"], "mrr": round(mrr, 4), "ap": round(ap, 4)}

        for k in TOP_K_LISTA:
            ic, id_ = ild(res, k)
            acum[k]["recall"].append(recall_at_k(gt, cods, k))
            acum[k]["prec"].append(precision_at_k(gt, cods, k))
            acum[k]["hr"].append(1.0 if any(c in gt for c in cods[:k]) else 0.0)
            acum[k]["ndcg"].append(ndcg_at_k(gt, cods, k))
            acum[k]["ild_cat"].append(ic)
            acum[k]["ild_dep"].append(id_)
            acum[k]["spread"].append(spread(scores, k))
            if k == 5:
                caso_metricas["ndcg@5"] = round(ndcg_at_k(gt, cods, k), 4)
                caso_metricas["precision@5"] = round(precision_at_k(gt, cods, k), 4)

        detalle.append(caso_metricas)
        print(f"\r  {i:>4}/{len(casos)}", end="", flush=True)
    print()

    m = lambda lst: round(statistics.mean(lst), 4) if lst else 0.0
    return {
        "fecha":             datetime.now().isoformat(),
        "modelo":            MODELO_ID,
        "total_queries":     len(casos),
        "queries_efectivas": len(mrr_l),
        "umbral":            UMBRAL_SIM,
        "metricas": {
            "MRR":             m(mrr_l),
            "MAP":             m(ap_l),
            "Latencia_P50_ms": round(float(np.percentile(lat_l, 50)), 2) if lat_l else 0,
            "Latencia_P95_ms": round(float(np.percentile(lat_l, 95)), 2) if lat_l else 0,
            "Similitud_top1":  m(sim1_l),
            "Score_gap_avg":   m(score_gaps),
            "Tasa_fallos_%":   round(sum(fallos) / len(fallos) * 100, 2) if fallos else 0,
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
        "detalle_por_caso": detalle,
    }


def cobertura(cur):
    cur.execute("SELECT COUNT(*) FROM obras;")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT obra_id) FROM embeddings;")
    con = cur.fetchone()[0]
    return total, con


def reporte(res, total, con_emb):
    if not res:
        return
    sep = "─" * 60
    pct = round(con_emb / total * 100, 1) if total else 0
    m = res["metricas"]
    print(f"\n{sep}")
    print(f"  Evaluación RAG — Obras Públicas  (v2 · test.json)")
    print(f"  Modelo : {res['modelo']}")
    print(f"  Fecha  : {res['fecha'][:19]}")
    print(f"  Queries: {res['queries_efectivas']} / {res['total_queries']}")
    print(sep)
    print(f"  Cobertura: {con_emb:,} / {total:,}  ({pct}%)")
    print(sep)
    for nombre, val in m.items():
        print(f"  {nombre:<24} {val}")
    print(f"\n  {'K':<3} {'Recall':>7} {'Prec':>7} {'Hit':>7} {'NDCG':>7} {'ILD_d':>6} {'Spread':>7}")
    for k, kv in res["por_k"].items():
        v = list(kv.values())
        print(f"  {k:<3} {v[0]:>7} {v[1]:>7} {v[2]:>7} {v[3]:>7} {v[4]:>6} {v[5]:>7}")
    print(f"\n  → {EXPORT_JSON}")
    print(sep + "\n")


def main():
    log(f"Cargando casos de {TEST_JSON}...")
    test_data = cargar_test(TEST_JSON)
    casos = test_data["casos"]
    log(f"Casos cargados: {len(casos)}")

    log("Conectando a PostgreSQL...")
    conn = conectar()
    cur  = conn.cursor()

    total, con_emb = cobertura(cur)
    log(f"Obras: {total:,} | Con embedding: {con_emb:,}")

    log("Embebiendo queries desde test.json...")
    model = TextEmbedding(model_name=MODELO_ID)
    queries = [c["query"] for c in casos]
    vectores_query = np.array([
        normalizar(np.array(v, dtype="float32"))
        for v in model.embed(queries)
    ])
    log("Embeddings generados.")

    log("Evaluando...")
    res = evaluar(casos, vectores_query, cur)
    res["cobertura"] = {"total": total, "con_embedding": con_emb}
    res["origen_casos"] = TEST_JSON

    reporte(res, total, con_emb)

    with open(EXPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    log(f"Exportado → {EXPORT_JSON}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()