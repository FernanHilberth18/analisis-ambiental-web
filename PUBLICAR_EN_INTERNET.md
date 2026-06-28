# Publicar la pagina en internet

La pagina es una aplicacion Flask con PostgreSQL/PostGIS. Para verla en internet, el camino mas directo es Render.

## 1. Subir el proyecto a GitHub

1. Crea un repositorio nuevo en GitHub.
2. Sube la carpeta completa `Proyecto Final`.
3. No subas archivos `.env`, contrasenas, dumps de base de datos ni la carpeta `.venv`.

## 2. Crear la base de datos en Render

1. En Render, entra a New > PostgreSQL.
2. Crea la base de datos.
3. Copia la External Database URL para restaurar datos.
4. Copia la Internal Database URL para conectar la pagina.

Activa PostGIS en la base:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

## 3. Exportar la base local

Desde tu computadora:

```bash
pg_dump -Fc -d analisis_ambiental -U postgres -f analisis_ambiental.dump
```

## 4. Restaurar la base en Render

Usa la URL externa de Render:

```bash
pg_restore --clean --if-exists --no-owner --dbname "URL_EXTERNA_DE_RENDER" analisis_ambiental.dump
```

## 5. Crear el sitio web en Render

Opcion recomendada:

1. New > Blueprint.
2. Selecciona el repositorio de GitHub.
3. Render detectara el archivo `render.yaml`.
4. En `DATABASE_URL`, pega la Internal Database URL.
5. Inicia el deploy.

Opcion manual:

1. New > Web Service.
2. Conecta el repositorio.
3. Root Directory: `analisis_ambiental_web`
4. Build Command: `pip install -r requirements.txt`
5. Start Command: `gunicorn app:app`
6. Agrega estas variables:

```text
DATABASE_URL=URL_INTERNA_DE_RENDER
SECRET_KEY=un_valor_largo_y_secreto
FORCE_HTTPS=true
FLASK_DEBUG=false
```

## 6. Enlace final

Cuando termine el deploy, Render te dara un enlace parecido a:

```text
https://analisis-ambiental-web.onrender.com
```

Ese sera tu sitio web publico.
