import os, json, warnings
from datetime import datetime
import numpy as np
import psycopg2
from dotenv import load_dotenv
warnings.filterwarnings("ignore", category=UserWarning)
load_dotenv()

# Config
N_CASOS  = 30          # casos manejables para revisar a mano
GT_SIZE  = 10
TEST_JSON = "test.json"

DSN = {
    "host":     os.getenv("POSTGRES_HOST", "localhost"),
    "port":     int(os.getenv("POSTGRES_PORT", 5432)),
    "dbname":   os.getenv("POSTGRES_DB"),
    "user":     os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}


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


def parse_vec(v) -> np.ndarray:
    if isinstance(v, str):
        return np.array(json.loads(v), dtype="float32")
    return np.array(v, dtype="float32")


def cargar_catalogos(cur):
    cur.execute("SELECT id, nombre FROM cat_clasificador_n1;")
    cats = {r[0]: r[1] for r in cur.fetchall()}
    cur.execute("SELECT id, nombre FROM cat_departamento;")
    deptos = {r[0]: r[1] for r in cur.fetchall()}
    return cats, deptos


def cargar_casos(cur, n: int):
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


def construir_gt(cur, caso: dict, gt_size: int):
    vec_str = "[" + ",".join(f"{x:.6f}" for x in caso["vec_orig"].tolist()) + "]"
    cur.execute("""
        SELECT o.codigo_infobras, o.nombre_obra
        FROM   embeddings e
        JOIN   obras o ON o.id = e.obra_id
        WHERE  o.clasificador_n1_id = %s
          AND  o.codigo_infobras   != %s
        ORDER  BY e.vector <=> %s::vector
        LIMIT  %s;
    """, (caso["cat_n1"], caso["codigo"], vec_str, gt_size))
    return [
        {"codigo": int(r[0]), "titulo": (r[1].strip() if r[1] else "")}
        for r in cur.fetchall()
    ]


def build_query(caso: dict, cats: dict, deptos: dict) -> str:
    cat_name   = cats.get(caso["cat_n1"], "")
    depto_name = deptos.get(caso["depto"], "")
    partes = [caso["titulo"]]
    if cat_name:   partes.append(cat_name)
    if depto_name: partes.append(depto_name)
    return " | ".join(partes)


def main():
    log("Conectando a PostgreSQL...")
    conn = conectar()
    cur  = conn.cursor()

    log("Cargando catálogos...")
    cats, deptos = cargar_catalogos(cur)

    log(f"Sampleando {N_CASOS} casos...")
    casos = cargar_casos(cur, N_CASOS)
    log(f"Casos cargados: {len(casos)}")

    log(f"Calculando GT semántico (top-{GT_SIZE} por categoría)...")
    salida = []
    for i, caso in enumerate(casos, 1):
        gt = construir_gt(cur, caso, GT_SIZE)
        query = build_query(caso, cats, deptos)
        salida.append({
            "id_caso":      i,
            "codigo":       caso["codigo"],
            "query":        query,
            "cat_n1":       caso["cat_n1"],
            "depto":        caso["depto"],
            "ground_truth": gt,
        })
        print(f"\r  {i:>4}/{len(casos)}", end="", flush=True)
    print()

    payload = {
        "generado":  datetime.now().isoformat(),
        "gt_size":   GT_SIZE,
        "n_casos":   len(salida),
        "casos":     salida,
    }

    with open(TEST_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    log(f"Exportado → {TEST_JSON}")
    log("Revisa/edita 'query' y 'ground_truth' a mano si lo necesitas antes de evaluar.", "WARN")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()