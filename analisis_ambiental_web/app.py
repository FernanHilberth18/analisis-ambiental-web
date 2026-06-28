from flask import Flask, render_template, jsonify, request
from db import obtener_una_fila, obtener_varias_filas
from flask import abort
import os
import math

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024
app.config["JSON_SORT_KEYS"] = False

if os.getenv("SECRET_KEY"):
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")


@app.after_request
def agregar_cabeceras_seguridad(response):
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://unpkg.com; "
        "img-src 'self' data: https://*.tile.openstreetmap.org https://server.arcgisonline.com; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'"
    )
    response.headers["Content-Security-Policy"] = csp
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(self)"

    if request.is_secure or os.getenv("FORCE_HTTPS", "").lower() == "true":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    return response

# =========================
# TABLAS EN POSTGRES
# =========================

TABLA_HUMEDAL = "humedal_bahia_panama"
TABLA_EDIFICIOS = "edificios_humedal_1km"
TABLAS_PERMITIDAS = {TABLA_HUMEDAL, TABLA_EDIFICIOS}
ZONAS_VALIDAS = {
    "Fangales intermareales",
    "Manglar",
    "Estuario",
    "Canales",
    "Borde costero",
    "Borde urbano",
}

FAUNA_EDUCATIVA = [
    {
        "nombre_comun": "Chorlito semipalmeado",
        "nombre_cientifico": "Charadrius semipalmatus",
        "grupo": "Ave playera migratoria",
        "zonas": ["Fangales intermareales", "Borde costero"],
        "descripcion": "Ave migratoria pequeña que usa playas lodosas y bancos de arena para descansar y alimentarse durante sus viajes.",
        "aprendizaje": "Su presencia indica que los fangales funcionan como una estación de alimentación para aves migratorias.",
        "amenaza": "Pérdida de habitat por rellenos, disturbio humano y cambios en la línea costera.",
        "imagen_url": "/static/img/fauna/chorlito_semipalmeado.jfif",
    },
    {
        "nombre_comun": "Correlimos occidental",
        "nombre_cientifico": "Calidris mauri",
        "grupo": "Ave playera migratoria",
        "zonas": ["Fangales intermareales", "Borde costero"],
        "descripcion": "Ave playera que se alimenta de pequeños invertebrados en el lodo expuesto durante la marea baja.",
        "aprendizaje": "Depende de máreas y sedimentos sanos; si el fangal se altera, pierde alimento.",
        "amenaza": "Urbanización cercana, contaminación y pérdida de áreas intermareales.",
        "imagen_url": "/static/img/fauna/correlimos_occidental.jfif",
    },
    {
        "nombre_comun": "Cangrejo violinista",
        "nombre_cientifico": "Minuca sp.",
        "grupo": "Crustaceo",
        "zonas": ["Fangales intermareales", "Manglar"],
        "descripcion": "Crustaceo pequeno que vive en madrigueras del lodo y ayuda a remover y oxigenar el sedimento.",
        "aprendizaje": "Es una pieza clave del alimento de muchas aves playeras.",
        "amenaza": "Compactación del suelo, contaminación y pérdida del manglar.",
        "imagen_url": "/static/img/fauna/cangrejo_violinista.jfif",
    },
    {
        "nombre_comun": "Garza blanca",
        "nombre_cientifico": "Ardea alba",
        "grupo": "Ave acuatica",
        "zonas": ["Manglar", "Estuario", "Canales"],
        "descripcion": "Garza grande que caza peces, anfibios e invertebrados en aguas someras y bordes de manglar.",
        "aprendizaje": "Usa zonas de poca profundidad porque alli encuentra presas faciles de capturar.",
        "amenaza": "Contaminacion del agua, reducción de vegetación ribereña y disturbio.",
        "imagen_url": "/static/img/fauna/garza_blanca.jfif",
    },
    {
        "nombre_comun": "Ibis blanco",
        "nombre_cientifico": "Eudocimus albus",
        "grupo": "Ave acuatica",
        "zonas": ["Manglar", "Estuario"],
        "descripcion": "Ave de pico curvo que busca crustaceos e insectos acuaticos en lodos y aguas poco profundas.",
        "aprendizaje": "Su pico curvo esta adaptado para explorar el lodo.",
        "amenaza": "Pérdida de sitios de alimentación y contaminación.",
        "imagen_url": "/static/img/fauna/ibis_blanco.jfif",
    },
    {
        "nombre_comun": "Espatula rosada",
        "nombre_cientifico": "Platalea ajaja",
        "grupo": "Ave acuatica",
        "zonas": ["Manglar", "Estuario"],
        "descripcion": "Ave rosada de pico ancho que filtra alimento moviendo el pico lateralmente en aguas someras.",
        "aprendizaje": "Su forma de alimentación depende de aguas tranquilas y poco profundas.",
        "amenaza": "Alteración hidrológica, contaminación y pérdida de manglar.",
        "imagen_url": "/static/img/fauna/espatula_rosada.jfif",
    },
    {
        "nombre_comun": "Cocodrilo americano",
        "nombre_cientifico": "Crocodylus acutus",
        "grupo": "Reptil",
        "zonas": ["Canales", "Manglar", "Estuario"],
        "descripcion": "Reptil grande asociado a estuarios, canales y manglares. Es un depredador importante del ecosistema.",
        "aprendizaje": "Los depredadores grandes ayudan a mantener el equilibrio de las poblaciones.",
        "amenaza": "Conflicto con humanos, pérdida de habitat y contaminación.",
        "imagen_url": "/static/img/fauna/cocodrilo_americano.jpg",
    },
    {
        "nombre_comun": "Pelicano pardo",
        "nombre_cientifico": "Pelecanus occidentalis",
        "grupo": "Ave marina",
        "zonas": ["Borde costero", "Estuario"],
        "descripcion": "Ave marina que se alimenta de peces y suele observarse en costas, estuarios y aguas cercanas.",
        "aprendizaje": "Conecta el humedal con el ambiente marino cercano.",
        "amenaza": "Basura marina, contaminación y disminucion de peces.",
        "imagen_url": "/static/img/fauna/pelicano_pardo.jfif",
    },
    {
        "nombre_comun": "Fragata magnifica",
        "nombre_cientifico": "Fregata magnificens",
        "grupo": "Ave marina",
        "zonas": ["Borde costero", "Estuario"],
        "descripcion": "Ave planeadora que aprovecha corrientes de aire sobre la costa y el mar para desplazarse con poco esfuerzo.",
        "aprendizaje": "Observa el humedal desde el aire y depende de ecosistemas costeros productivos.",
        "amenaza": "Disturbio en sitios de descanso y contaminación costera.",
        "imagen_url": "/static/img/fauna/fragata_magnifica.jfif",
    },
    {
        "nombre_comun": "Mapache cangrejero",
        "nombre_cientifico": "Procyon cancrivorus",
        "grupo": "Mamifero",
        "zonas": ["Manglar", "Borde urbano"],
        "descripcion": "Mamifero nocturno que consume cangrejos, frutos, insectos y otros pequeños animales.",
        "aprendizaje": "Muestra la conexión entre vegetación de borde, manglar y alimento disponible.",
        "amenaza": "Fragmentacion del habitat, atropellos y basura.",
        "imagen_url": "/static/img/fauna/mapache_cangrejero.jpg",
    },
    {
        "nombre_comun": "Iguana verde",
        "nombre_cientifico": "Iguana iguana",
        "grupo": "Reptil",
        "zonas": ["Manglar", "Borde urbano"],
        "descripcion": "Reptil arborícola que puede usar vegetación cercana a cuerpos de agua y bordes del humedal.",
        "aprendizaje": "La vegetación de borde ofrece refugio y alimento a especies terrestres.",
        "amenaza": "Pérdida de vegetación y captura.",
        "imagen_url": "/static/img/fauna/iguana_verde.jfif",
    },
    {
        "nombre_comun": "Martin pescador",
        "nombre_cientifico": "Megaceryle sp.",
        "grupo": "Ave acuatica",
        "zonas": ["Canales", "Estuario"],
        "descripcion": "Ave que se posa cerca del agua y se lanza para capturar peces pequeños.",
        "aprendizaje": "Necesita agua con peces y sitios de percha para cazar.",
        "amenaza": "Contaminacion del agua y pérdida de bordes naturales.",
        "imagen_url": "/static/img/fauna/martin_pescador.jfif",
    },
    {
        "nombre_comun": "Garza azul",
        "nombre_cientifico": "Egretta caerulea",
        "grupo": "Ave acuatica",
        "zonas": ["Manglar", "Estuario", "Canales"],
        "descripcion": "Garza de humedales costeros que busca alimento en aguas someras y bordes lodosos.",
        "aprendizaje": "Comparte habitat con otras garzas, pero puede usar microzonas distintas para alimentarse.",
        "amenaza": "Alteración de zonas de alimentación y contaminación.",
        "imagen_url": "/static/img/fauna/garza_azul.jfif",
    },
]


# =========================
# RUTA PRINCIPAL
# =========================

@app.route("/")
def index():
    sql = f"""
    SELECT
        COUNT(*) AS total_humedal
    FROM {TABLA_HUMEDAL};
    """

    datos = obtener_una_fila(sql)

    return render_template("index.html", datos=datos)


# =========================
# API: TABLAS
# =========================

@app.route("/api/tablas")
def api_tablas():
    sql = """
    SELECT 
        table_name
    FROM information_schema.tables
    WHERE table_schema = 'public'
    ORDER BY table_name;
    """

    datos = obtener_varias_filas(sql)

    return jsonify(datos)


# =========================
# API: COLUMNAS
# =========================

@app.route("/api/columnas/<tabla>")
def api_columnas(tabla):
    if tabla not in TABLAS_PERMITIDAS:
        abort(404)

    sql = f"""
    SELECT 
        column_name,
        data_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
    AND table_name = :tabla
    ORDER BY ordinal_position;
    """

    datos = obtener_varias_filas(sql, {"tabla": tabla})

    return jsonify(datos)


# =========================
# API: RESUMEN GENERAL
# =========================

@app.route("/api/resumen")
def api_resumen():
    sql = f"""
    SELECT
        (SELECT COUNT(*) FROM {TABLA_HUMEDAL}) AS total_humedal,
        (SELECT COUNT(*) FROM {TABLA_EDIFICIOS}) AS total_edificios,
        (
            SELECT ROUND(SUM(hectares)::numeric, 2)
            FROM {TABLA_HUMEDAL}
        ) AS hectareas_humedal;
    """

    datos = obtener_una_fila(sql)

    return jsonify(datos)


# =========================
# API: HUMEDAL GEOJSON
# =========================

@app.route("/api/humedal")
def api_humedal():
    sql = f"""
    SELECT
        gid,
        id,
        hectares,
        estab_yr,
        ST_AsGeoJSON(geom)::json AS geometry
    FROM {TABLA_HUMEDAL}
    WHERE geom IS NOT NULL;
    """

    filas = obtener_varias_filas(sql)

    features = []

    for fila in filas:
        feature = {
            "type": "Feature",
            "geometry": fila.get("geometry"),
            "properties": {
                "gid": fila.get("gid"),
                "id": fila.get("id"),
                "hectares": fila.get("hectares"),
                "estab_yr": fila.get("estab_yr")
            }
        }

        features.append(feature)

    geojson = {
        "type": "FeatureCollection",
        "features": features
    }

    return jsonify(geojson)


# =========================
# API: EDIFICIOS GEOJSON
# =========================

@app.route("/api/edificios")
def api_edificios():
    sql = f"""
    SELECT
        gid,
        fid,
        ST_AsGeoJSON(geom)::json AS geometry
    FROM {TABLA_EDIFICIOS}
    WHERE geom IS NOT NULL
    LIMIT 10000;
    """

    filas = obtener_varias_filas(sql)

    features = []

    for fila in filas:
        feature = {
            "type": "Feature",
            "geometry": fila.get("geometry"),
            "properties": {
                "gid": fila.get("gid"),
                "fid": fila.get("fid")
            }
        }

        features.append(feature)

    geojson = {
        "type": "FeatureCollection",
        "features": features
    }

    return jsonify(geojson)


# =========================
# API: PUNTOS DE EDIFICIOS PARA HEATMAP
# =========================

@app.route("/api/edificios-puntos")
def api_edificios_puntos():
    sql = f"""
    SELECT
        gid,
        ST_Y(ST_PointOnSurface(geom)) AS lat,
        ST_X(ST_PointOnSurface(geom)) AS lon
    FROM {TABLA_EDIFICIOS}
    WHERE geom IS NOT NULL
    LIMIT 10000;
    """

    datos = obtener_varias_filas(sql)

    puntos = []

    for fila in datos:
        puntos.append([
            fila.get("lat"),
            fila.get("lon"),
            1
        ])

    return jsonify(puntos)


# =========================
# API: ANILLOS DE PRESIÓN URBANA
# =========================

@app.route("/api/anillos-presion")
def api_anillos_presion():
    sql = f"""
    WITH humedal AS (
        SELECT ST_UnaryUnion(ST_Collect(geom)) AS geom
        FROM {TABLA_HUMEDAL}
    ),
    buffers AS (
        SELECT
            ST_Buffer(geom::geography, 250)::geometry AS b250,
            ST_Buffer(geom::geography, 500)::geometry AS b500,
            ST_Buffer(geom::geography, 750)::geometry AS b750,
            ST_Buffer(geom::geography, 1000)::geometry AS b1000
        FROM humedal
    ),
    anillos AS (
        SELECT 
            '0 - 250 m' AS rango,
            1 AS orden,
            'Presión muy alta' AS nivel,
            b250 AS geom
        FROM buffers

        UNION ALL

        SELECT 
            '250 - 500 m' AS rango,
            2 AS orden,
            'Presión alta' AS nivel,
            ST_Difference(b500, b250) AS geom
        FROM buffers

        UNION ALL

        SELECT 
            '500 - 750 m' AS rango,
            3 AS orden,
            'Presión media' AS nivel,
            ST_Difference(b750, b500) AS geom
        FROM buffers

        UNION ALL

        SELECT 
            '750 - 1000 m' AS rango,
            4 AS orden,
            'Presión baja' AS nivel,
            ST_Difference(b1000, b750) AS geom
        FROM buffers
    )
    SELECT
        rango,
        orden,
        nivel,
        ST_AsGeoJSON(geom)::json AS geometry
    FROM anillos
    ORDER BY orden;
    """

    filas = obtener_varias_filas(sql)

    features = []

    for fila in filas:
        feature = {
            "type": "Feature",
            "geometry": fila.get("geometry"),
            "properties": {
                "rango": fila.get("rango"),
                "orden": fila.get("orden"),
                "nivel": fila.get("nivel")
            }
        }

        features.append(feature)

    geojson = {
        "type": "FeatureCollection",
        "features": features
    }

    return jsonify(geojson)


# =========================
# API: CONTEO DE EDIFICIOS POR DISTANCIA
# =========================

@app.route("/api/presion-distancia")
def api_presion_distancia():
    sql = f"""
    WITH humedal AS (
        SELECT ST_UnaryUnion(ST_Collect(geom)) AS geom
        FROM {TABLA_HUMEDAL}
    ),
    edificios AS (
        SELECT
            gid,
            geom
        FROM {TABLA_EDIFICIOS}
        WHERE geom IS NOT NULL
    ),
    distancias AS (
        SELECT
            e.gid,
            ST_Distance(
                ST_PointOnSurface(e.geom)::geography,
                h.geom::geography
            ) AS distancia_m
        FROM edificios e
        CROSS JOIN humedal h
    )
    SELECT
        CASE
            WHEN distancia_m <= 250 THEN '0 - 250 m'
            WHEN distancia_m <= 500 THEN '250 - 500 m'
            WHEN distancia_m <= 750 THEN '500 - 750 m'
            WHEN distancia_m <= 1000 THEN '750 - 1000 m'
            ELSE 'Más de 1000 m'
        END AS rango,
        CASE
            WHEN distancia_m <= 250 THEN 1
            WHEN distancia_m <= 500 THEN 2
            WHEN distancia_m <= 750 THEN 3
            WHEN distancia_m <= 1000 THEN 4
            ELSE 5
        END AS orden,
        COUNT(*) AS total_edificios,
        ROUND(AVG(distancia_m)::numeric, 2) AS distancia_promedio_m
    FROM distancias
    GROUP BY rango, orden
    ORDER BY orden;
    """

    datos = obtener_varias_filas(sql)

    return jsonify(datos)


# =========================
# API: DIAGNÓSTICO
# =========================

# =========================
# API: PUNTO DE MAYOR CONCENTRACION EN ZONA CRITICA
# =========================

@app.route("/api/zona-critica-punto")
def api_zona_critica_punto():
    sql = f"""
    WITH humedal AS (
        SELECT ST_UnaryUnion(ST_Collect(geom)) AS geom
        FROM {TABLA_HUMEDAL}
    ),
    edificios_cercanos AS (
        SELECT
            ST_PointOnSurface(e.geom) AS punto
        FROM {TABLA_EDIFICIOS} e
        CROSS JOIN humedal h
        WHERE e.geom IS NOT NULL
        AND ST_DWithin(
            ST_PointOnSurface(e.geom)::geography,
            h.geom::geography,
            250
        )
    ),
    celdas AS (
        SELECT
            ST_SnapToGrid(punto, 0.005) AS celda,
            ST_Collect(punto) AS puntos,
            COUNT(*) AS total_edificios
        FROM edificios_cercanos
        GROUP BY ST_SnapToGrid(punto, 0.005)
        ORDER BY total_edificios DESC
        LIMIT 1
    )
    SELECT
        ST_Y(ST_Centroid(puntos)) AS lat,
        ST_X(ST_Centroid(puntos)) AS lon,
        total_edificios
    FROM celdas;
    """

    datos = obtener_una_fila(sql)

    return jsonify(datos)


@app.route("/api/zonas-criticas-rangos")
def api_zonas_criticas_rangos():
    sql = f"""
    WITH humedal AS (
        SELECT ST_UnaryUnion(ST_Collect(geom)) AS geom
        FROM {TABLA_HUMEDAL}
    ),
    edificios AS (
        SELECT
            ST_PointOnSurface(e.geom) AS punto,
            ST_Distance(
                ST_PointOnSurface(e.geom)::geography,
                h.geom::geography
            ) AS distancia_m
        FROM {TABLA_EDIFICIOS} e
        CROSS JOIN humedal h
        WHERE e.geom IS NOT NULL
    ),
    clasificados AS (
        SELECT
            punto,
            CASE
                WHEN distancia_m <= 250 THEN '0 - 250 m'
                WHEN distancia_m <= 500 THEN '250 - 500 m'
                WHEN distancia_m <= 750 THEN '500 - 750 m'
                WHEN distancia_m <= 1000 THEN '750 - 1000 m'
            END AS rango,
            CASE
                WHEN distancia_m <= 250 THEN 1
                WHEN distancia_m <= 500 THEN 2
                WHEN distancia_m <= 750 THEN 3
                WHEN distancia_m <= 1000 THEN 4
            END AS orden,
            CASE
                WHEN distancia_m <= 250 THEN 'Presión muy alta'
                WHEN distancia_m <= 500 THEN 'Presión alta'
                WHEN distancia_m <= 750 THEN 'Presión media'
                WHEN distancia_m <= 1000 THEN 'Presión baja'
            END AS nivel
        FROM edificios
        WHERE distancia_m <= 1000
    ),
    celdas AS (
        SELECT
            rango,
            orden,
            nivel,
            ST_SnapToGrid(punto, 0.005) AS celda,
            ST_Collect(punto) AS puntos,
            COUNT(*) AS total_edificios
        FROM clasificados
        GROUP BY rango, orden, nivel, ST_SnapToGrid(punto, 0.005)
    ),
    ranking AS (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY rango
                ORDER BY total_edificios DESC
            ) AS posicion
        FROM celdas
    )
    SELECT
        rango,
        orden,
        nivel,
        ST_Y(ST_Centroid(puntos)) AS lat,
        ST_X(ST_Centroid(puntos)) AS lon,
        total_edificios
    FROM ranking
    WHERE posicion = 1
    ORDER BY orden;
    """

    datos = obtener_varias_filas(sql)

    return jsonify(datos)


def clasificar_zona_ecologica(lat, lon):
    zonas_educativas = [
        (9.0065, -79.4026, 10500, "Fangales intermareales"),
        (9.0006, -79.1911, 11800, "Manglar"),
        (8.9550, -79.2750, 10500, "Estuario"),
        (9.0820, -79.2450, 8500, "Canales"),
        (8.9000, -79.0900, 11200, "Borde costero"),
        (8.9050, -78.9800, 9600, "Manglar"),
        (8.8150, -78.9050, 10500, "Borde costero"),
        (8.9550, -79.0550, 8200, "Estuario"),
        (9.0200, -79.3300, 7600, "Borde urbano"),
    ]

    for centro_lat, centro_lon, radio_m, zona in zonas_educativas:
        metros_por_grado_lat = 111_320
        metros_por_grado_lon = 111_320 * math.cos(math.radians(centro_lat))
        delta_lat_m = (lat - centro_lat) * metros_por_grado_lat
        delta_lon_m = (lon - centro_lon) * metros_por_grado_lon
        distancia_aproximada_m = (delta_lat_m ** 2 + delta_lon_m ** 2) ** 0.5

        if distancia_aproximada_m <= radio_m:
            return zona

    return "Fuera de zona ecológica educativa"


def zona_ecologica_valida(zona):
    return zona != "Fuera de zona ecológica educativa"


def coordenadas_validas(lat, lon):
    return (
        lat is not None
        and lon is not None
        and math.isfinite(lat)
        and math.isfinite(lon)
        and -90 <= lat <= 90
        and -180 <= lon <= 180
    )


def nivel_presion_por_distancia(distancia):
    if distancia is None:
        return "Sin dato"

    if distancia <= 250:
        return "Presión muy alta"

    if distancia <= 500:
        return "Presión alta"

    if distancia <= 750:
        return "Presión media"

    if distancia <= 1000:
        return "Presión baja"

    return "Fuera del buffer de 1 km"


def coordenada_fauna(especie, indice):
    coordenadas_zona = {
        "Fangales intermareales": (9.0065, -79.4026),
        "Manglar": (9.0006, -79.1911),
        "Estuario": (8.9550, -79.2750),
        "Canales": (9.0820, -79.2450),
        "Borde costero": (8.9000, -79.0900),
        "Borde urbano": (9.0200, -79.3300),
    }

    zona = especie["zonas"][0]
    lat, lon = coordenadas_zona.get(zona, (9.0065, -79.4026))
    offset = (indice % 5) * 0.006

    return {
        "lat": lat + offset,
        "lon": lon - offset,
        "zona_principal": zona,
    }


def fauna_con_coordenadas(especies):
    datos = []

    for indice, especie in enumerate(especies):
        item = dict(especie)
        item.update(coordenada_fauna(especie, indice))
        datos.append(item)

    return datos


@app.route("/api/fauna-todas")
def api_fauna_todas():
    return jsonify({
        "total": len(FAUNA_EDUCATIVA),
        "especies": fauna_con_coordenadas(FAUNA_EDUCATIVA)
    })


@app.route("/api/fauna-educativa")
def api_fauna_educativa():
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    zona_solicitada = request.args.get("zona", type=str)

    if lat is None or lon is None:
        lat = 9.006498533218249
        lon = -79.40257397547522

    if not coordenadas_validas(lat, lon):
        return jsonify({"error": "Coordenadas invalidas"}), 400

    if zona_solicitada in ZONAS_VALIDAS:
        zona = zona_solicitada
    else:
        zona = clasificar_zona_ecologica(lat, lon)

    sql = f"""
    WITH humedal AS (
        SELECT ST_UnaryUnion(ST_Collect(geom)) AS geom
        FROM {TABLA_HUMEDAL}
    ),
    punto AS (
        SELECT ST_SetSRID(ST_Point(:lon, :lat), 4326) AS geom
    )
    SELECT
        ROUND(ST_Distance(p.geom::geography, h.geom::geography)::numeric, 2) AS distancia_humedal_m
    FROM punto p
    CROSS JOIN humedal h;
    """

    contexto = obtener_una_fila(sql, {"lat": lat, "lon": lon})
    distancia = contexto.get("distancia_humedal_m")
    nivel_presion = nivel_presion_por_distancia(float(distancia) if distancia is not None else None)

    especies = []

    if zona_ecologica_valida(zona):
        for especie in FAUNA_EDUCATIVA:
            if zona in especie["zonas"]:
                especies.append(especie)

    if zona_ecologica_valida(zona) and len(especies) == 0:
        especies = FAUNA_EDUCATIVA[:4]

    especies = fauna_con_coordenadas(especies)

    return jsonify({
        "zona": zona,
        "lat": lat,
        "lon": lon,
        "distancia_humedal_m": distancia,
        "nivel_presion": nivel_presion,
        "tipo_dato_fauna": "Guía educativa aproximada" if zona_ecologica_valida(zona) else "Fuera de zona educativa",
        "especies": especies
    })


@app.route("/api/diagnostico")
def api_diagnostico():
    datos = {
        "tabla_humedal": TABLA_HUMEDAL,
        "tabla_edificios": TABLA_EDIFICIOS,
        "columnas_humedal": obtener_varias_filas(f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = :tabla
            ORDER BY ordinal_position;
        """, {"tabla": TABLA_HUMEDAL}),
        "columnas_edificios": obtener_varias_filas(f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = :tabla
            ORDER BY ordinal_position;
        """, {"tabla": TABLA_EDIFICIOS})
    }

    return jsonify(datos)


# =========================
# EJECUTAR APP
# =========================

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)



