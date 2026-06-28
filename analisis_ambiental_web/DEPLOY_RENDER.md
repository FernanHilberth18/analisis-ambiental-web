# Despliegue en Render

Esta app es Flask + PostgreSQL/PostGIS. Para compartirla con un enlace publico necesitas subir tanto el codigo como la base de datos.

## 1. Subir el codigo a GitHub

Sube la carpeta `analisis_ambiental_web` a un repositorio de GitHub.

## 2. Crear una base PostgreSQL en Render

En Render:

1. New
2. PostgreSQL
3. Crea la base de datos
4. Copia el `Internal Database URL`

Dentro de la base debes activar PostGIS:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

## 3. Exportar tu base local

Desde tu computadora:

```bash
pg_dump -Fc -d analisis_ambiental -U postgres -f analisis_ambiental.dump
```

## 4. Restaurar la base en Render

Usa la URL externa de Render para restaurar el dump:

```bash
pg_restore --clean --if-exists --no-owner --dbname "URL_EXTERNA_DE_RENDER" analisis_ambiental.dump
```

## 5. Crear el Web Service

En Render:

1. New
2. Web Service
3. Conecta el repositorio de GitHub
4. Root Directory: `analisis_ambiental_web`
5. Build Command:

```bash
pip install -r requirements.txt
```

6. Start Command:

```bash
gunicorn app:app
```

7. Environment Variable:

```text
DATABASE_URL=URL_INTERNA_DE_RENDER
```

## 6. Compartir el enlace

Cuando el deploy termine, Render te dara un enlace parecido a:

```text
https://analisis-ambiental-web.onrender.com
```

Ese es el link que puedes compartir.

## Notas importantes

- No subas contrasenas reales al repositorio.
- La app lee `DATABASE_URL` en produccion.
- Localmente puedes usar `DATABASE_URL` o definir `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` y `DB_NAME`.
- Las imagenes dentro de `static/img/fauna` deben estar subidas al repositorio.
