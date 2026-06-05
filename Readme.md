# Buscador Semántico de Obras Públicas

Este proyecto implementa un sistema de **Generación Aumentada por Recuperación (RAG)** y búsqueda semántica para un dataset de Obras Públicas (InfoBras)[cite: 2, 3]. Convierte descripciones textuales en vectores matemáticos (embeddings) mediante modelos de NLP y realiza búsquedas de similitud ultrarrápidas utilizando **PostgreSQL** y la extensión **pgvector**[cite: 2, 3].

---
## Tecnologías Principales

* **Procesamiento de Datos (ETL):** Python, Pandas, PyArrow[cite: 1, 2].
* **Inteligencia Artificial (NLP):** Hugging Face `sentence-transformers` (`paraphrase-multilingual-MiniLM-L12-v2`)[cite: 1, 2].
* **Base de Datos:** PostgreSQL 16 + `pgvector` (Índice HNSW optimizado para similitud coseno)[cite: 2, 3].
* **Backend (API):** FastAPI, Pydantic (Validación de esquemas), Psycopg2, Uvicorn[cite: 2, 3].
* **Frontend (UI):** HTML5, CSS3, Vanilla JavaScript (Dashboard interactivo responsive)[cite: 3].
* **Infraestructura:** Docker & Docker Compose[cite: 3].
---

## Estructura del Proyecto

El sistema sigue una arquitectura modular separando el pipeline de datos de la capa de servicios web[cite: 3]:

```text
procesar_info/
│
├── Pipeline de Datos
│   ├── preprocesar.py         # Limpieza del dataset original a formato Parquet base
│   ├── procesar.ipynb         # Generación de Embeddings en GPU (Google Colab)
│   ├── postprocesar.py        # Ingesta masiva relacional y vectorial hacia PostgreSQL
│   └── evaluar.py             # Script de evaluación de métricas de búsqueda
│
├── Capa de Servicio (API)
│   └── api/
│       ├── main.py            # Endpoints REST (FastAPI)
│       ├── db.py              # Gestor del pool de conexiones a PostgreSQL
│       ├── schemas.py         # Modelos de validación de datos (Pydantic)
│       └── obras.html         # Interfaz gráfica de usuario (Frontend)
│
├── Infraestructura & Datos
│   ├── init/
│   │   └── 01_schema.sql      # DDL: Creación de tablas, jerarquías e índices pgvector
│   ├── data/                  # Caché local (Requiere el Excel original aquí)
│   ├── docker-compose.yml     # Orquestación del contenedor PostgreSQL + pgvector
│   ├── requirements.txt       # Dependencias de Python
│   └── .env                   # Variables de entorno y credenciales

```

---
## Requisitos Previos

1. **Python 3.11 o superior** instalado en el sistema local.
2. **Docker y Docker Compose** instalados y en ejecución.
3. Cuenta de **Google Colab** (Requerida para la aceleración por hardware - GPU T4).


4. El archivo crudo `DataSet-Obras-Publicas 04-06-2026.xlsx` ubicado dentro del directorio `data/`.
---

## Guía de Ejecución Paso a Paso
Sigue este orden estricto para garantizar la correcta transformación de datos y el despliegue del sistema.

### Paso 1: Configuración del Entorno Base
Abre tu terminal en la raíz del proyecto y configura tu entorno virtual y variables.

```bash
# 1. Crear y activar entorno virtual
python -m venv env
source env/bin/activate  # En Windows usa: env\Scripts\activate

# 2. Instalar dependencias requeridas
pip install -r requirements.txt
```

Crea un archivo `.env` en la raíz del proyecto con las credenciales de la base de datos:

```env
POSTGRES_DB=obras_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=tu_contraseña_segura
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

```

### Paso 2: Preprocesamiento (ETL)
Limpia el archivo Excel original y genera las estructuras columnares iniciales.

```bash
python preprocesar.py

```

* **Resultado:** Se creará `Procesado-DataSet-Obras-Publicas 04-06-2026.parquet` en la carpeta `data/`.*

### Paso 3: Generación de Embeddings Vectoriales (Nube)

Debido a la carga computacional, este paso se realiza en la nube.

1. Sube el archivo `Procesado-DataSet-Obras-Publicas 04-06-2026.parquet` a tu Google Drive.


2. Abre el archivo `procesar.ipynb` en **Google Colab**.


3. **IMPORTANTE:** Ve a la barra superior: `Entorno de ejecución` > `Cambiar tipo de entorno de ejecución` y selecciona **T4 GPU**.


4. Ejecuta todas las celdas del cuaderno.


5. Descarga el archivo resultante `embeddings_output.parquet` y guárdalo en tu carpeta local `data/`.



### Paso 4: Inicialización de la Base de Datos

Levanta el contenedor de PostgreSQL. Automáticamente leerá `01_schema.sql` para construir el esquema relacional y vectorial.

```bash
docker-compose up -d

```

### Paso 5: Ingesta Masiva (Postprocesamiento)

Migra los datos estructurados y los tensores a PostgreSQL en lotes (*batches*) transaccionales.

```bash
python postprocesar.py

```

* **Nota:** Este proceso normaliza los catálogos e inserta los vectores. Espera el mensaje de "Migración completada" en la terminal.

### Paso 6: Despliegue del Servidor Web (Backend)

Con la base de datos poblada, levanta el motor de la API.

```bash
cd api
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---
## Uso del Sistema

Una vez que Uvicorn esté en ejecución, puedes acceder a las siguientes rutas desde tu navegador:

* **Dashboard de Búsqueda (UI):** [http://localhost:8000/](https://www.google.com/search?q=http://localhost:8000/)
* Interfaz para búsquedas en lenguaje natural y filtros en cascada (Geográficos, Clasificadores, Estados).

* **Documentación Interactiva API:** [http://localhost:8000/docs](https://www.google.com/search?q=http://localhost:8000/docs)
* Entorno Swagger UI para auditar y probar directamente los endpoints REST con validación Pydantic.
---

## Mantenimiento y Detención
* **Apagar la API:** Presiona `Ctrl + C` en la terminal de Uvicorn.
* **Apagar la Base de Datos:** Desde la raíz del proyecto, ejecuta `docker-compose down`. Los datos se mantienen seguros en el volumen administrado por Docker.
