# Guía de Ejecución Paso a Paso: Pipeline de Datos y Backend RAG

Sigue este orden estricto para procesar la información, cargarla en la base de datos y levantar la API. Ubícate siempre en la raíz de tu proyecto en la terminal antes de empezar.

### Paso 1: Preprocesamiento de Datos (`preprocesar.py`)
Este script limpia el Excel original y lo convierte en un formato eficiente (Parquet).

* **Archivos necesarios antes de ejecutar:**
    * La carpeta `data/` debe existir.
    * El archivo original `DataSet-Obras-Publicas 04-06-2026.xlsx` debe estar dentro de la carpeta `data/`.
* **Comando de ejecución:**
    ```bash
    python preprocesar.py
    ```
* **Resultado esperado:** Se generarán `DataSet-Obras-Publicas 04-06-2026.parquet` y `Procesado-DataSet-Obras-Publicas 04-06-2026.parquet` dentro de la carpeta `data/`.

### Paso 2: Generación de Embeddings (`procesar.ipynb`)
Este paso es el más pesado y debe ejecutarse en la nube para aprovechar la aceleración por hardware.

* **Entorno:** Sube este archivo y ábrelo en **Google Colab**.
* **⚠️ REQUISITO CRÍTICO (Modo GPU):** En Colab, ve al menú superior: `Entorno de ejecución` -> `Cambiar tipo de entorno de ejecución` -> Selecciona **T4 GPU**. Si olvidas esto, el proceso tardará horas en lugar de minutos.
* **Archivos necesarios en tu Google Drive:**
    * Sube el archivo `Procesado-DataSet-Obras-Publicas 04-06-2026.parquet` (generado en el Paso 1) a la ruta de tu Drive que especifica el cuaderno.
* **Ejecución:** Corre todas las celdas del cuaderno.
* **Resultado esperado:** Descarga desde tu Drive el archivo resultante `embeddings_output.parquet` y colócalo en la carpeta local `data/` de tu proyecto.

### Paso 3: Levantar la Base de Datos con Docker
Antes de ingestar los datos, la base de datos PostgreSQL con la extensión vectorial debe estar encendida.

* **Archivos necesarios antes de ejecutar:**
    * El archivo `docker-compose.yml`.
    * El archivo oculto `.env` configurado con tus credenciales.
    * La carpeta `init/` con el archivo `01_schema.sql` adentro.
* **Comando de ejecución (en la raíz del proyecto):**
    ```bash
    docker-compose up -d
    ```
* *Nota: La primera vez que lo ejecutes, Docker creará automáticamente las tablas usando el archivo de la carpeta init.*

### Paso 4: Ingesta de Datos (`postprocesar.py`)
Este script toma los datos relacionales y los vectores, y los inserta de forma masiva en tu base de datos PostgreSQL.

* **Archivos necesarios antes de ejecutar:**
    * El archivo `DataSet-Obras-Publicas 04-06-2026.parquet` (dentro de `data/`).
    * El archivo `embeddings_output.parquet` (dentro de `data/`).
    * El archivo `.env` en la raíz (el script lo lee para conectarse a la BD).
    * La base de datos Docker del Paso 3 debe estar corriendo.
* **Comando de ejecución:**
    ```bash
    python postprocesar.py
    ```

### Paso 5: Levantar el Backend (API)
Con la base de datos poblada, ya puedes encender el servidor web para hacer consultas.

* **Paso previo:** Navega hacia la carpeta de la API en tu terminal:
    ```bash
    cd api
    ```
* **Comando de ejecución:**
    ```bash
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    ```
* **Verificación:** Abre tu navegador y entra a `http://localhost:8000/docs`. Deberías ver la interfaz de Swagger lista para probar tus endpoints.
* **Ejecutado:** Para ver el programa en ejecucion entra a `http://localhost:8000/` desde el navegador