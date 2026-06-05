# Documentación de Arquitectura: Estructura del Proyecto y Base de Datos (pgvector)

Este documento describe la arquitectura integral del sistema, dividida en la organización de los componentes de software (Pipeline ETL y API) basada en el directorio del proyecto, y el modelo de datos relacional/vectorial estructurado en PostgreSQL con pgvector.

## 1. Arquitectura de Software (Pipeline y API)

```mermaid
graph TD
    classDef frontend fill:#3498db,stroke:#2980b9,stroke-width:2px,color:#fff;
    classDef backend fill:#2ecc71,stroke:#27ae60,stroke-width:2px,color:#fff;
    classDef pipeline fill:#9b59b6,stroke:#8e44ad,stroke-width:2px,color:#fff;
    classDef infra fill:#f39c12,stroke:#d35400,stroke-width:2px,color:#fff;

    subgraph Capa_Presentacion [Capa de Presentación]
        UI[api/obras.html<br>Frontend Web]
    end

    subgraph Capa_API [Capa de Servicios - FastAPI]
        API[api/main.py<br>Endpoints y Lógica REST]
        Schemas[api/schemas.py<br>Modelos Pydantic]
        DB[api/db.py<br>Conexión PostgreSQL]
        
        API --> Schemas
        API --> DB
    end

    subgraph Capa_Datos [Pipeline de Datos / ETL]
        Pre[preprocesar.py<br>Limpieza de Datos]
        Proc[procesar.ipynb<br>Generación Embeddings]
        Post[postprocesar.py<br>Ingesta a Base de Datos]
        Eval[evaluar.py<br>Evaluación de Resultados]
        
        Pre --> Proc
        Proc --> Post
        Post -.-> Eval
    end

    subgraph Capa_Infraestructura [Infraestructura y Configuración]
        Docker[docker-compose.yml<br>Orquestación]
        SQL[init/01_schema.sql<br>Inicialización DB]
        Data[Directorio /data<br>Parquets y Archivos]
    end

    UI -->|Consultas| API
    DB -->|Ejecuta SQL| SQL
    Post -->|Lee Parquets| Data

    class UI frontend;
    class API,Schemas,DB backend;
    class Pre,Proc,Post,Eval pipeline;
    class Docker,SQL,Data infra;

```

### Explicación de la Arquitectura de Software

La disposición de los archivos refleja una separación clara de responsabilidades:

* **Pipeline de Datos (Raíz del proyecto):** Los scripts `preprocesar.py`, `procesar.ipynb` y `postprocesar.py` conforman el flujo secuencial ETL (Extracción, Transformación, Carga). Toman los archivos crudos del directorio `data/`, construyen los vectores y los inyectan en la base de datos. `evaluar.py` se encarga de medir el rendimiento de estas operaciones.
* **Capa de Servicios (`api/`):** Contiene el núcleo de la aplicación web (FastAPI). `main.py` expone los servicios, `schemas.py` valida las entradas/salidas, y `db.py` administra el *pool* de conexiones hacia PostgreSQL. Incluye también `obras.html` como interfaz ligera de consumo.
* **Infraestructura (`init/` y Raíz):** Orquestación mediante `docker-compose.yml`, dependencias en `requirements.txt` y la definición inicial de la base de datos en `01_schema.sql`.

---

## 2. Diagrama de Entidad-Relación (ERD)

```mermaid
erDiagram
    OBRAS {
        int id PK "SERIAL"
        int codigo_infobras UK
        string nombre_obra
        string nombre_proyecto
        string entidad_publica
        boolean existe_paralizacion
        boolean marca_reconstruccion
        boolean marca_reactivacion
        string direccion
        string empresa_contratista
        string motivo_no_100
        string causal_paralizacion
        string comentarios
        string estado_proyecto
        date fecha_inicio_obra
        date fecha_fin_real
        string texto_embedding
    }
    
    EMBEDDINGS {
        int id PK "SERIAL"
        int obra_id FK "ON DELETE CASCADE"
        vector vector_384 "pgvector (HNSW Index)"
    }

    CAT_DEPARTAMENTO {
        smallint id PK
        string nombre UK
    }
    CAT_PROVINCIA {
        smallint id PK
        string nombre
        smallint departamento_id FK
    }
    CAT_DISTRITO {
        smallint id PK
        string nombre
        smallint provincia_id FK
    }

    CAT_CLASIFICADOR_N1 {
        smallint id PK
        string nombre UK
    }
    CAT_CLASIFICADOR_N2 {
        smallint id PK
        string nombre
        smallint n1_id FK
    }
    CAT_CLASIFICADOR_N3 {
        smallint id PK
        string nombre
        smallint n2_id FK
    }

    CAT_SECTOR {
        smallint id PK
        string nombre UK
    }
    CAT_NIVEL_GOBIERNO {
        smallint id PK
        string nombre UK
    }
    CAT_ESTADO_EJECUCION {
        smallint id PK
        string nombre UK
    }
    CAT_MODALIDAD {
        smallint id PK
        string nombre UK
    }
    CAT_NATURALEZA {
        smallint id PK
        string nombre UK
    }

    CAT_DEPARTAMENTO ||--o{ CAT_PROVINCIA : "contiene"
    CAT_PROVINCIA ||--o{ CAT_DISTRITO : "contiene"
    CAT_DISTRITO ||--o{ OBRAS : "ubica"

    CAT_CLASIFICADOR_N1 ||--o{ CAT_CLASIFICADOR_N2 : "subdivide"
    CAT_CLASIFICADOR_N2 ||--o{ CAT_CLASIFICADOR_N3 : "subdivide"
    CAT_CLASIFICADOR_N3 ||--o{ OBRAS : "clasifica"

    CAT_SECTOR ||--o{ OBRAS : "pertenece"
    CAT_NIVEL_GOBIERNO ||--o{ OBRAS : "pertenece"
    CAT_ESTADO_EJECUCION ||--o{ OBRAS : "estado"
    CAT_MODALIDAD ||--o{ OBRAS : "ejecuta_por"
    CAT_NATURALEZA ||--o{ OBRAS : "tiene"

    OBRAS ||--|| EMBEDDINGS : "posee_vector"

```

### Explicación del Modelo de Base de Datos

El esquema SQL `01_schema.sql` define un modelo de estrella/copo de nieve optimizado para recuperación vectorial (RAG):

* **Tablas de Catálogo Jerárquicas:** Se estructuran niveles de dependencia para ubicaciones (Departamento -> Provincia -> Distrito) y clasificaciones de obra (N1 -> N2 -> N3), utilizando restricciones `UNIQUE` compuestas para mantener la integridad de los datos jerárquicos.
* **Optimización de Espacio:** Todos los catálogos utilizan identificadores `SMALLINT` (`SMALLSERIAL`), reduciendo drásticamente el peso de almacenamiento de la tabla central `obras`, la cual posee llaves foráneas apuntando a todos estos catálogos.
* **Tabla Principal (`obras`):** Concentra la metadata y llaves foráneas de la obra, usando un `codigo_infobras` como identificador de negocio único.
* **Aislamiento del Embedding (`embeddings`):** Se separa la representación matemática (`vector(384)`) en su propia tabla. Esto mejora el rendimiento general del motor relacional. Posee un índice `HNSW` con similitud coseno (`vector_cosine_ops`) que acelera las búsquedas aproximadas de alta dimensionalidad.
