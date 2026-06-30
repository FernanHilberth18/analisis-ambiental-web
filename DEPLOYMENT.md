# Guia de despliegue

La web se despliega con **GitHub + Render**.

## Flujo normal

```bash
git add analisis_ambiental_web
git commit -m "Mensaje del cambio"
git push origin main
```

Render ejecuta un nuevo despliegue cuando `main` recibe cambios.

## Configuracion clave en Render

- Root Directory: `analisis_ambiental_web`
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app`

Variables necesarias:

```text
DATABASE_URL=URL_INTERNA_DE_RENDER
SECRET_KEY=valor_largo_y_secreto
FORCE_HTTPS=true
FLASK_DEBUG=false
```

## Base de datos

Activar PostGIS:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

Exportar local:

```bash
pg_dump -Fc -d analisis_ambiental -U postgres -f analisis_ambiental.dump
```

Restaurar en Render:

```bash
pg_restore --clean --if-exists --no-owner --dbname "URL_EXTERNA_DE_RENDER" analisis_ambiental.dump
```
