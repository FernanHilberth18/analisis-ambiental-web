from flask import Flask, render_template, jsonify, request
from db import ejecutar_sql, obtener_una_fila, obtener_varias_filas
from flask import abort
from flask import redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
try:
    from authlib.integrations.flask_client import OAuth
    AUTHLIB_IMPORT_ERROR = ""
except ImportError as error:
    OAuth = None
    AUTHLIB_IMPORT_ERROR = str(error)
import os
import math
import json
import random
import re
import secrets
import hashlib
import smtplib
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024
app.config["JSON_SORT_KEYS"] = False

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "clave-local-de-desarrollo")
oauth = OAuth(app) if OAuth is not None else None
google_oauth_registrado = False
github_oauth_registrado = False
microsoft_oauth_registrado = False


def google_oauth_configurado():
    return bool(oauth and os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"))


def github_oauth_configurado():
    return bool(oauth and os.getenv("GITHUB_CLIENT_ID") and os.getenv("GITHUB_CLIENT_SECRET"))


def microsoft_oauth_configurado():
    return bool(oauth and os.getenv("MICROSOFT_CLIENT_ID") and os.getenv("MICROSOFT_CLIENT_SECRET"))


def registrar_google_oauth():
    global google_oauth_registrado

    if google_oauth_registrado or not google_oauth_configurado():
        return google_oauth_registrado

    oauth.register(
        name="google",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"}
    )
    google_oauth_registrado = True
    return google_oauth_registrado


def registrar_github_oauth():
    global github_oauth_registrado

    if github_oauth_registrado or not github_oauth_configurado():
        return github_oauth_registrado

    oauth.register(
        name="github",
        client_id=os.getenv("GITHUB_CLIENT_ID"),
        client_secret=os.getenv("GITHUB_CLIENT_SECRET"),
        authorize_url="https://github.com/login/oauth/authorize",
        access_token_url="https://github.com/login/oauth/access_token",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "read:user user:email"}
    )
    github_oauth_registrado = True
    return github_oauth_registrado


def registrar_microsoft_oauth():
    global microsoft_oauth_registrado

    if microsoft_oauth_registrado or not microsoft_oauth_configurado():
        return microsoft_oauth_registrado

    tenant = os.getenv("MICROSOFT_TENANT_ID", "common")
    oauth.register(
        name="microsoft",
        client_id=os.getenv("MICROSOFT_CLIENT_ID"),
        client_secret=os.getenv("MICROSOFT_CLIENT_SECRET"),
        server_metadata_url=f"https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"}
    )
    microsoft_oauth_registrado = True
    return microsoft_oauth_registrado


registrar_google_oauth()
registrar_github_oauth()
registrar_microsoft_oauth()


@app.after_request
def agregar_cabeceras_seguridad(response):
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net https://www.google.com/recaptcha/ https://www.gstatic.com/recaptcha/; "
        "style-src 'self' 'unsafe-inline' https://unpkg.com; "
        "img-src 'self' data: https://*.tile.openstreetmap.org https://server.arcgisonline.com; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "frame-src 'self' https://www.google.com/recaptcha/ https://recaptcha.google.com/recaptcha/; "
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
TABLA_USUARIOS = "usuarios_comentarios"
TABLA_COMENTARIOS = "comentarios_humedal"
TABLA_RECUPERACION = "recuperacion_password"
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
        "imagen_url": "/static/img/fauna/chorlito_semipalmeado.jpg",
    },
    {
        "nombre_comun": "Correlimos occidental",
        "nombre_cientifico": "Calidris mauri",
        "grupo": "Ave playera migratoria",
        "zonas": ["Fangales intermareales", "Borde costero"],
        "descripcion": "Ave playera que se alimenta de pequeños invertebrados en el lodo expuesto durante la marea baja.",
        "aprendizaje": "Depende de máreas y sedimentos sanos; si el fangal se altera, pierde alimento.",
        "amenaza": "Urbanización cercana, contaminación y pérdida de áreas intermareales.",
        "imagen_url": "/static/img/fauna/correlimos_occidental.jpg",
    },
    {
        "nombre_comun": "Cangrejo violinista",
        "nombre_cientifico": "Minuca sp.",
        "grupo": "Crustaceo",
        "zonas": ["Fangales intermareales", "Manglar"],
        "descripcion": "Crustaceo pequeno que vive en madrigueras del lodo y ayuda a remover y oxigenar el sedimento.",
        "aprendizaje": "Es una pieza clave del alimento de muchas aves playeras.",
        "amenaza": "Compactación del suelo, contaminación y pérdida del manglar.",
        "imagen_url": "/static/img/fauna/cangrejo_violinista.jpg",
    },
    {
        "nombre_comun": "Garza blanca",
        "nombre_cientifico": "Ardea alba",
        "grupo": "Ave acuatica",
        "zonas": ["Manglar", "Estuario", "Canales"],
        "descripcion": "Garza grande que caza peces, anfibios e invertebrados en aguas someras y bordes de manglar.",
        "aprendizaje": "Usa zonas de poca profundidad porque alli encuentra presas faciles de capturar.",
        "amenaza": "Contaminacion del agua, reducción de vegetación ribereña y disturbio.",
        "imagen_url": "/static/img/fauna/garza_blanca.jpg",
    },
    {
        "nombre_comun": "Ibis blanco",
        "nombre_cientifico": "Eudocimus albus",
        "grupo": "Ave acuatica",
        "zonas": ["Manglar", "Estuario"],
        "descripcion": "Ave de pico curvo que busca crustaceos e insectos acuaticos en lodos y aguas poco profundas.",
        "aprendizaje": "Su pico curvo esta adaptado para explorar el lodo.",
        "amenaza": "Pérdida de sitios de alimentación y contaminación.",
        "imagen_url": "/static/img/fauna/ibis_blanco.jpg",
    },
    {
        "nombre_comun": "Espatula rosada",
        "nombre_cientifico": "Platalea ajaja",
        "grupo": "Ave acuatica",
        "zonas": ["Manglar", "Estuario"],
        "descripcion": "Ave rosada de pico ancho que filtra alimento moviendo el pico lateralmente en aguas someras.",
        "aprendizaje": "Su forma de alimentación depende de aguas tranquilas y poco profundas.",
        "amenaza": "Alteración hidrológica, contaminación y pérdida de manglar.",
        "imagen_url": "/static/img/fauna/espatula_rosada.jpg",
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
        "imagen_url": "/static/img/fauna/pelicano_pardo.jpg",
    },
    {
        "nombre_comun": "Fragata magnifica",
        "nombre_cientifico": "Fregata magnificens",
        "grupo": "Ave marina",
        "zonas": ["Borde costero", "Estuario"],
        "descripcion": "Ave planeadora que aprovecha corrientes de aire sobre la costa y el mar para desplazarse con poco esfuerzo.",
        "aprendizaje": "Observa el humedal desde el aire y depende de ecosistemas costeros productivos.",
        "amenaza": "Disturbio en sitios de descanso y contaminación costera.",
        "imagen_url": "/static/img/fauna/fragata_magnifica.jpg",
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
        "imagen_url": "/static/img/fauna/iguana_verde.jpg",
    },
    {
        "nombre_comun": "Martin pescador",
        "nombre_cientifico": "Megaceryle sp.",
        "grupo": "Ave acuatica",
        "zonas": ["Canales", "Estuario"],
        "descripcion": "Ave que se posa cerca del agua y se lanza para capturar peces pequeños.",
        "aprendizaje": "Necesita agua con peces y sitios de percha para cazar.",
        "amenaza": "Contaminacion del agua y pérdida de bordes naturales.",
        "imagen_url": "/static/img/fauna/martin_pescador.jpg",
    },
    {
        "nombre_comun": "Garza azul",
        "nombre_cientifico": "Egretta caerulea",
        "grupo": "Ave acuatica",
        "zonas": ["Manglar", "Estuario", "Canales"],
        "descripcion": "Garza de humedales costeros que busca alimento en aguas someras y bordes lodosos.",
        "aprendizaje": "Comparte habitat con otras garzas, pero puede usar microzonas distintas para alimentarse.",
        "amenaza": "Alteración de zonas de alimentación y contaminación.",
        "imagen_url": "/static/img/fauna/garza_azul.jpg",
    },
]

tablas_comentarios_listas = False


@app.before_request
def preparar_tablas_comentarios():
    global tablas_comentarios_listas

    if tablas_comentarios_listas:
        return

    ejecutar_sql(f"""
        CREATE TABLE IF NOT EXISTS {TABLA_USUARIOS} (
            id SERIAL PRIMARY KEY,
            nombre VARCHAR(40) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            proveedor VARCHAR(20) NOT NULL DEFAULT 'local',
            proveedor_id VARCHAR(120),
            email VARCHAR(160),
            creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    ejecutar_sql(f"ALTER TABLE {TABLA_USUARIOS} ADD COLUMN IF NOT EXISTS proveedor VARCHAR(20) NOT NULL DEFAULT 'local';")
    ejecutar_sql(f"ALTER TABLE {TABLA_USUARIOS} ADD COLUMN IF NOT EXISTS proveedor_id VARCHAR(120);")
    ejecutar_sql(f"ALTER TABLE {TABLA_USUARIOS} ADD COLUMN IF NOT EXISTS email VARCHAR(160);")
    ejecutar_sql(f"ALTER TABLE {TABLA_USUARIOS} ADD COLUMN IF NOT EXISTS rol VARCHAR(20) NOT NULL DEFAULT 'usuario';")
    ejecutar_sql(f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{TABLA_USUARIOS}_proveedor_id ON {TABLA_USUARIOS} (proveedor, proveedor_id) WHERE proveedor_id IS NOT NULL;")
    ejecutar_sql(f"CREATE INDEX IF NOT EXISTS idx_{TABLA_USUARIOS}_email_local ON {TABLA_USUARIOS} (LOWER(email)) WHERE proveedor = 'local' AND email IS NOT NULL;")

    ejecutar_sql(f"""
        CREATE TABLE IF NOT EXISTS {TABLA_COMENTARIOS} (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER NOT NULL REFERENCES {TABLA_USUARIOS}(id) ON DELETE CASCADE,
            contenido VARCHAR(800) NOT NULL,
            estado VARCHAR(20) NOT NULL DEFAULT 'pendiente',
            creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    ejecutar_sql(f"ALTER TABLE {TABLA_COMENTARIOS} ALTER COLUMN estado SET DEFAULT 'pendiente';")
    ejecutar_sql(f"ALTER TABLE {TABLA_COMENTARIOS} ADD COLUMN IF NOT EXISTS revisado_en TIMESTAMPTZ;")
    ejecutar_sql(f"ALTER TABLE {TABLA_COMENTARIOS} ADD COLUMN IF NOT EXISTS revisado_por INTEGER REFERENCES {TABLA_USUARIOS}(id) ON DELETE SET NULL;")
    ejecutar_sql(f"ALTER TABLE {TABLA_COMENTARIOS} ADD COLUMN IF NOT EXISTS editado_en TIMESTAMPTZ;")

    ejecutar_sql(f"""
        CREATE TABLE IF NOT EXISTS {TABLA_RECUPERACION} (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER NOT NULL REFERENCES {TABLA_USUARIOS}(id) ON DELETE CASCADE,
            token_hash VARCHAR(64) UNIQUE NOT NULL,
            usado BOOLEAN NOT NULL DEFAULT FALSE,
            expira_en TIMESTAMPTZ NOT NULL,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    ejecutar_sql(f"CREATE INDEX IF NOT EXISTS idx_{TABLA_RECUPERACION}_token ON {TABLA_RECUPERACION} (token_hash);")

    admin_user = os.getenv("ADMIN_USER", "").strip()
    admin_password = os.getenv("ADMIN_PASSWORD", "").strip()

    if admin_user and admin_password:
        ejecutar_sql(
            f"""
            INSERT INTO {TABLA_USUARIOS} (nombre, password_hash, rol)
            VALUES (:nombre, :password_hash, 'admin')
            ON CONFLICT (nombre) DO UPDATE SET
                password_hash = EXCLUDED.password_hash,
                rol = 'admin';
            """,
            {"nombre": admin_user, "password_hash": generate_password_hash(admin_password)}
        )

    tablas_comentarios_listas = True


def usuario_actual():
    if "usuario_id" not in session:
        return None

    return {
        "id": session["usuario_id"],
        "nombre": session.get("usuario_nombre", "Usuario"),
        "rol": session.get("usuario_rol", "usuario"),
        "proveedor": session.get("usuario_proveedor", "local"),
        "es_admin": session.get("usuario_rol") == "admin"
    }


def requiere_admin(funcion):
    @wraps(funcion)
    def wrapper(*args, **kwargs):
        usuario = usuario_actual()

        if usuario is None:
            guardar_mensaje("Inicia sesión como administrador.")
            return redirect(url_for("index", _anchor="comentarios"))

        if not usuario["es_admin"]:
            abort(403)

        return funcion(*args, **kwargs)

    return wrapper


def guardar_mensaje(texto):
    session["mensaje"] = texto


def mensaje_flash():
    return session.pop("mensaje", None)


def csrf_token():
    token = session.get("csrf_token")

    if not token:
        token = os.urandom(24).hex()
        session["csrf_token"] = token

    return token


app.jinja_env.globals["csrf_token"] = csrf_token


def csrf_valido():
    token_formulario = request.form.get("csrf_token", "")
    token_sesion = session.get("csrf_token", "")
    return bool(token_formulario and token_sesion and token_formulario == token_sesion)


def rechazar_si_csrf_invalido():
    if not csrf_valido():
        guardar_mensaje("Solicitud rechazada por seguridad. Recarga la página e intenta otra vez.")
        return True

    return False


def captcha_nuevo():
    a = random.randint(2, 9)
    b = random.randint(2, 9)
    session["captcha_comentario"] = str(a + b)
    return f"{a} + {b}"


def captcha_valido(valor):
    esperado = session.pop("captcha_comentario", None)
    return esperado is not None and valor.strip() == esperado


def recaptcha_site_key():
    return os.getenv("RECAPTCHA_SITE_KEY", "")


def recaptcha_secret_key():
    return os.getenv("RECAPTCHA_SECRET_KEY", "")


def recaptcha_configurado():
    return bool(recaptcha_site_key() and recaptcha_secret_key())


def recaptcha_valido(token, ip_remota):
    if not token:
        return False

    datos = urllib.parse.urlencode({
        "secret": recaptcha_secret_key(),
        "response": token,
        "remoteip": ip_remota or ""
    }).encode("utf-8")

    solicitud = urllib.request.Request(
        "https://www.google.com/recaptcha/api/siteverify",
        data=datos,
        method="POST"
    )

    try:
        with urllib.request.urlopen(solicitud, timeout=6) as respuesta:
            resultado = json.loads(respuesta.read().decode("utf-8"))
            return bool(resultado.get("success"))
    except Exception as error:
        print("Error verificando reCAPTCHA:", error)
        return False


def nombre_usuario_valido(nombre):
    return re.fullmatch(r"[A-Za-zÁÉÍÓÚáéíóúÑñ0-9_ ]{3,40}", nombre or "") is not None


def email_valido(email):
    return re.fullmatch(r"[^@\s]{3,80}@[^@\s]{2,80}\.[^@\s]{2,20}", email or "") is not None


def nombre_unico(nombre_base):
    limpio = re.sub(r"[^A-Za-zÁÉÍÓÚáéíóúÑñ0-9_ ]", "", nombre_base or "Usuario").strip()
    limpio = limpio[:32] or "Usuario"
    candidato = limpio
    contador = 2

    while obtener_una_fila(
        f"SELECT id FROM {TABLA_USUARIOS} WHERE LOWER(nombre) = LOWER(:nombre);",
        {"nombre": candidato}
    ):
        candidato = f"{limpio[:28]} {contador}"
        contador += 1

    return candidato


def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def smtp_configurado():
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM"))


def enviar_email(destinatario, asunto, contenido):
    if not smtp_configurado():
        return False

    mensaje = EmailMessage()
    mensaje["From"] = os.getenv("SMTP_FROM")
    mensaje["To"] = destinatario
    mensaje["Subject"] = asunto
    mensaje.set_content(contenido)

    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    usuario = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    usar_tls = os.getenv("SMTP_TLS", "true").lower() == "true"

    try:
        with smtplib.SMTP(host, port, timeout=10) as servidor:
            if usar_tls:
                servidor.starttls()

            if usuario and password:
                servidor.login(usuario, password)

            servidor.send_message(mensaje)
        return True
    except Exception as error:
        print("Error enviando correo:", error)
        return False


def url_externa(endpoint, **valores):
    url = url_for(endpoint, _external=True, **valores)

    if os.getenv("FORCE_HTTPS", "").lower() == "true":
        url = url.replace("http://", "https://", 1)

    return url


def buscar_o_crear_usuario_oauth(proveedor, proveedor_id, nombre_base, email):
    usuario = obtener_una_fila(
        f"""
        SELECT id, nombre, rol, proveedor
        FROM {TABLA_USUARIOS}
        WHERE proveedor = :proveedor
        AND proveedor_id = :proveedor_id;
        """,
        {"proveedor": proveedor, "proveedor_id": proveedor_id}
    )

    if usuario:
        return usuario

    nombre = nombre_unico(nombre_base or (email.split("@")[0] if email else f"Usuario {proveedor}"))
    ejecutar_sql(
        f"""
        INSERT INTO {TABLA_USUARIOS}
            (nombre, password_hash, proveedor, proveedor_id, email)
        VALUES
            (:nombre, :password_hash, :proveedor, :proveedor_id, :email);
        """,
        {
            "nombre": nombre,
            "password_hash": generate_password_hash(os.urandom(24).hex()),
            "proveedor": proveedor,
            "proveedor_id": proveedor_id,
            "email": email
        }
    )
    return obtener_una_fila(
        f"""
        SELECT id, nombre, rol, proveedor
        FROM {TABLA_USUARIOS}
        WHERE proveedor = :proveedor
        AND proveedor_id = :proveedor_id;
        """,
        {"proveedor": proveedor, "proveedor_id": proveedor_id}
    )


def iniciar_sesion_usuario(usuario, mensaje):
    session["usuario_id"] = usuario["id"]
    session["usuario_nombre"] = usuario["nombre"]
    session["usuario_rol"] = usuario["rol"]
    session["usuario_proveedor"] = usuario["proveedor"]
    guardar_mensaje(mensaje)


def comentarios_recientes():
    return obtener_varias_filas(f"""
        SELECT
            c.contenido,
            c.creado_en,
            u.nombre AS usuario
        FROM {TABLA_COMENTARIOS} c
        JOIN {TABLA_USUARIOS} u ON u.id = c.usuario_id
        WHERE c.estado = 'aprobado'
        ORDER BY c.creado_en DESC
        LIMIT 20;
    """)


def comentarios_del_usuario(usuario_id):
    if not usuario_id:
        return []

    return obtener_varias_filas(f"""
        SELECT
            id,
            contenido,
            estado,
            creado_en,
            editado_en
        FROM {TABLA_COMENTARIOS}
        WHERE usuario_id = :usuario_id
        ORDER BY creado_en DESC
        LIMIT 30;
    """, {"usuario_id": usuario_id})


def comentario_senales(contenido):
    texto = (contenido or "").lower()
    senales = []

    if "http://" in texto or "https://" in texto or "www." in texto:
        senales.append("contiene enlace")

    if re.search(r"\b(select|insert|update|delete|drop|union|script)\b", texto):
        senales.append("parece contener comandos o codigo")

    if len(re.findall(r"[!?]", texto)) >= 5:
        senales.append("uso repetido de signos")

    if len(contenido or "") > 500:
        senales.append("comentario largo")

    return ", ".join(senales) if senales else "sin alertas"


def comentarios_admin():
    comentarios = obtener_varias_filas(f"""
        SELECT
            c.id,
            c.contenido,
            c.estado,
            c.creado_en,
            c.revisado_en,
            u.nombre AS usuario,
            COALESCE(revisor.nombre, '') AS revisor
        FROM {TABLA_COMENTARIOS} c
        JOIN {TABLA_USUARIOS} u ON u.id = c.usuario_id
        LEFT JOIN {TABLA_USUARIOS} revisor ON revisor.id = c.revisado_por
        ORDER BY
            CASE c.estado
                WHEN 'pendiente' THEN 0
                WHEN 'aprobado' THEN 1
                ELSE 2
            END,
            c.creado_en DESC
        LIMIT 80;
    """)

    for comentario in comentarios:
        comentario["senales"] = comentario_senales(comentario.get("contenido", ""))

    return comentarios


def resumen_admin():
    return obtener_una_fila(f"""
        SELECT
            COUNT(*) FILTER (WHERE estado = 'pendiente') AS pendientes,
            COUNT(*) FILTER (WHERE estado = 'aprobado') AS aprobados,
            COUNT(*) FILTER (WHERE estado = 'rechazado') AS rechazados,
            COUNT(*) AS total
        FROM {TABLA_COMENTARIOS};
    """)


def diagnostico_admin():
    admin_user = os.getenv("ADMIN_USER", "").strip()

    if not admin_user:
        return {
            "admin_usuario_existe": False,
            "admin_rol_correcto": False
        }

    usuario = obtener_una_fila(
        f"""
        SELECT rol
        FROM {TABLA_USUARIOS}
        WHERE LOWER(nombre) = LOWER(:nombre);
        """,
        {"nombre": admin_user}
    )

    return {
        "admin_usuario_existe": bool(usuario),
        "admin_rol_correcto": usuario.get("rol") == "admin" if usuario else False
    }


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
    usuario = usuario_actual()

    return render_template(
        "index.html",
        datos=datos,
        usuario=usuario,
        comentarios=comentarios_recientes(),
        mis_comentarios=comentarios_del_usuario(usuario["id"]) if usuario else [],
        captcha_pregunta=captcha_nuevo(),
        recaptcha_site_key=recaptcha_site_key(),
        google_login_disponible=registrar_google_oauth(),
        github_login_disponible=registrar_github_oauth(),
        microsoft_login_disponible=registrar_microsoft_oauth(),
        recuperacion_disponible=smtp_configurado(),
        mensaje=mensaje_flash()
    )


@app.post("/registro")
def registrar_usuario():
    if rechazar_si_csrf_invalido():
        return redirect(url_for("index", _anchor="comentarios"))

    if request.form.get("sitio_web", "").strip():
        guardar_mensaje("No se pudo procesar el registro.")
        return redirect(url_for("index"))

    nombre = request.form.get("nombre", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not nombre_usuario_valido(nombre):
        guardar_mensaje("El nombre debe tener entre 3 y 40 caracteres.")
        return redirect(url_for("index"))

    if not email_valido(email):
        guardar_mensaje("Escribe un correo válido para recuperar tu cuenta.")
        return redirect(url_for("index", _anchor="comentarios"))

    if len(password) < 6:
        guardar_mensaje("La contraseña debe tener al menos 6 caracteres.")
        return redirect(url_for("index"))

    existente = obtener_una_fila(
        f"SELECT id FROM {TABLA_USUARIOS} WHERE LOWER(nombre) = LOWER(:nombre);",
        {"nombre": nombre}
    )

    if existente:
        guardar_mensaje("Ese usuario ya existe.")
        return redirect(url_for("index"))

    ejecutar_sql(
        f"INSERT INTO {TABLA_USUARIOS} (nombre, email, password_hash) VALUES (:nombre, :email, :password_hash);",
        {"nombre": nombre, "email": email, "password_hash": generate_password_hash(password)}
    )
    usuario = obtener_una_fila(
        f"SELECT id, nombre, rol, proveedor FROM {TABLA_USUARIOS} WHERE LOWER(nombre) = LOWER(:nombre);",
        {"nombre": nombre}
    )
    iniciar_sesion_usuario(usuario, "Registro completado. Ya puedes comentar.")

    return redirect(url_for("index"))


@app.post("/login")
def iniciar_sesion():
    if rechazar_si_csrf_invalido():
        return redirect(url_for("index", _anchor="comentarios"))

    nombre = request.form.get("nombre", "").strip()
    password = request.form.get("password", "")
    usuario = obtener_una_fila(
        f"SELECT id, nombre, password_hash, rol, proveedor FROM {TABLA_USUARIOS} WHERE LOWER(nombre) = LOWER(:nombre);",
        {"nombre": nombre}
    )

    if not usuario or not check_password_hash(usuario["password_hash"], password):
        guardar_mensaje("Usuario o contraseña incorrectos.")
        return redirect(url_for("index"))

    iniciar_sesion_usuario(usuario, "Sesión iniciada.")

    return redirect(url_for("index"))


@app.post("/recuperar-password")
def solicitar_recuperacion_password():
    if rechazar_si_csrf_invalido():
        return redirect(url_for("index", _anchor="comentarios"))

    email = request.form.get("email", "").strip().lower()

    if not email_valido(email):
        guardar_mensaje("Escribe un correo válido.")
        return redirect(url_for("index", _anchor="comentarios"))

    usuario = obtener_una_fila(
        f"""
        SELECT id, nombre, email
        FROM {TABLA_USUARIOS}
        WHERE proveedor = 'local'
        AND LOWER(email) = LOWER(:email);
        """,
        {"email": email}
    )

    mensaje_generico = "Si ese correo existe, enviaremos un enlace de recuperación."

    if not usuario:
        guardar_mensaje(mensaje_generico)
        return redirect(url_for("index", _anchor="comentarios"))

    if not smtp_configurado():
        guardar_mensaje("La recuperación por correo todavía no está configurada en el servidor.")
        return redirect(url_for("index", _anchor="comentarios"))

    token = secrets.token_urlsafe(32)
    expira = datetime.now(timezone.utc) + timedelta(minutes=30)
    ejecutar_sql(
        f"""
        INSERT INTO {TABLA_RECUPERACION} (usuario_id, token_hash, expira_en)
        VALUES (:usuario_id, :token_hash, :expira_en);
        """,
        {"usuario_id": usuario["id"], "token_hash": token_hash(token), "expira_en": expira}
    )

    enlace = url_externa("formulario_restablecer_password", token=token)
    enviado = enviar_email(
        usuario["email"],
        "Recuperación de contraseña",
        f"Hola {usuario['nombre']},\n\nUsa este enlace para cambiar tu contraseña:\n{enlace}\n\nEl enlace vence en 30 minutos."
    )

    guardar_mensaje(mensaje_generico if enviado else "No se pudo enviar el correo de recuperación.")
    return redirect(url_for("index", _anchor="comentarios"))


@app.get("/recuperar-password/<token>")
def formulario_restablecer_password(token):
    recuperacion = obtener_una_fila(
        f"""
        SELECT id
        FROM {TABLA_RECUPERACION}
        WHERE token_hash = :token_hash
        AND usado = FALSE
        AND expira_en > NOW();
        """,
        {"token_hash": token_hash(token)}
    )

    if not recuperacion:
        guardar_mensaje("El enlace de recuperación no es válido o ya venció.")
        return redirect(url_for("index", _anchor="comentarios"))

    return render_template("reset_password.html", token=token, mensaje=mensaje_flash())


@app.post("/recuperar-password/<token>")
def restablecer_password(token):
    if rechazar_si_csrf_invalido():
        return redirect(url_for("formulario_restablecer_password", token=token))

    password = request.form.get("password", "")
    confirmacion = request.form.get("password_confirmacion", "")

    if len(password) < 8:
        guardar_mensaje("La nueva contraseña debe tener al menos 8 caracteres.")
        return redirect(url_for("formulario_restablecer_password", token=token))

    if password != confirmacion:
        guardar_mensaje("La confirmación de contraseña no coincide.")
        return redirect(url_for("formulario_restablecer_password", token=token))

    recuperacion = obtener_una_fila(
        f"""
        SELECT id, usuario_id
        FROM {TABLA_RECUPERACION}
        WHERE token_hash = :token_hash
        AND usado = FALSE
        AND expira_en > NOW();
        """,
        {"token_hash": token_hash(token)}
    )

    if not recuperacion:
        guardar_mensaje("El enlace de recuperación no es válido o ya venció.")
        return redirect(url_for("index", _anchor="comentarios"))

    ejecutar_sql(
        f"UPDATE {TABLA_USUARIOS} SET password_hash = :password_hash WHERE id = :usuario_id AND proveedor = 'local';",
        {"password_hash": generate_password_hash(password), "usuario_id": recuperacion["usuario_id"]}
    )
    ejecutar_sql(
        f"UPDATE {TABLA_RECUPERACION} SET usado = TRUE WHERE id = :recuperacion_id;",
        {"recuperacion_id": recuperacion["id"]}
    )
    guardar_mensaje("Contraseña restablecida. Ya puedes iniciar sesión.")
    return redirect(url_for("index", _anchor="comentarios"))


@app.get("/login/google")
def iniciar_sesion_google():
    if not registrar_google_oauth():
        guardar_mensaje("El inicio con Google todavía no está configurado.")
        return redirect(url_for("index"))

    return oauth.google.authorize_redirect(url_externa("google_callback"))


@app.get("/auth/google")
def google_callback():
    if not registrar_google_oauth():
        guardar_mensaje("El inicio con Google todavía no está configurado.")
        return redirect(url_for("index"))

    try:
        token = oauth.google.authorize_access_token()
        info = token.get("userinfo") or oauth.google.userinfo()
    except Exception as error:
        print("Error en login con Google:", error)
        guardar_mensaje("No se pudo iniciar sesión con Google.")
        return redirect(url_for("index"))

    proveedor_id = info.get("sub")
    email = info.get("email", "")
    nombre = info.get("name") or email.split("@")[0] or "Usuario Google"

    if not proveedor_id:
        guardar_mensaje("Google no devolvió un identificador válido.")
        return redirect(url_for("index"))

    usuario = buscar_o_crear_usuario_oauth("google", proveedor_id, nombre, email)
    iniciar_sesion_usuario(usuario, "Sesión iniciada con Google.")

    return redirect(url_for("index"))


@app.get("/login/github")
def iniciar_sesion_github():
    if not registrar_github_oauth():
        guardar_mensaje("El inicio con GitHub todavía no está configurado.")
        return redirect(url_for("index"))

    return oauth.github.authorize_redirect(url_externa("github_callback"))


@app.get("/auth/github")
def github_callback():
    if not registrar_github_oauth():
        guardar_mensaje("El inicio con GitHub todavía no está configurado.")
        return redirect(url_for("index"))

    try:
        oauth.github.authorize_access_token()
        perfil = oauth.github.get("user").json()
        emails = oauth.github.get("user/emails").json()
    except Exception as error:
        print("Error en login con GitHub:", error)
        guardar_mensaje("No se pudo iniciar sesión con GitHub.")
        return redirect(url_for("index"))

    proveedor_id = str(perfil.get("id") or "")
    email = perfil.get("email") or ""

    if not email:
        principal = next((item for item in emails if item.get("primary") and item.get("verified")), {})
        email = principal.get("email", "")

    if not proveedor_id:
        guardar_mensaje("GitHub no devolvió un identificador válido.")
        return redirect(url_for("index"))

    nombre = perfil.get("name") or perfil.get("login") or "Usuario GitHub"
    usuario = buscar_o_crear_usuario_oauth("github", proveedor_id, nombre, email)
    iniciar_sesion_usuario(usuario, "Sesión iniciada con GitHub.")
    return redirect(url_for("index"))


@app.get("/login/microsoft")
def iniciar_sesion_microsoft():
    if not registrar_microsoft_oauth():
        guardar_mensaje("El inicio con Microsoft todavía no está configurado.")
        return redirect(url_for("index"))

    return oauth.microsoft.authorize_redirect(url_externa("microsoft_callback"))


@app.get("/auth/microsoft")
def microsoft_callback():
    if not registrar_microsoft_oauth():
        guardar_mensaje("El inicio con Microsoft todavía no está configurado.")
        return redirect(url_for("index"))

    try:
        token = oauth.microsoft.authorize_access_token()
        info = token.get("userinfo") or oauth.microsoft.userinfo()
    except Exception as error:
        print("Error en login con Microsoft:", error)
        guardar_mensaje("No se pudo iniciar sesión con Microsoft.")
        return redirect(url_for("index"))

    proveedor_id = info.get("sub") or info.get("oid")
    email = info.get("email") or info.get("preferred_username") or ""
    nombre = info.get("name") or (email.split("@")[0] if email else "Usuario Microsoft")

    if not proveedor_id:
        guardar_mensaje("Microsoft no devolvió un identificador válido.")
        return redirect(url_for("index"))

    usuario = buscar_o_crear_usuario_oauth("microsoft", proveedor_id, nombre, email)
    iniciar_sesion_usuario(usuario, "Sesión iniciada con Microsoft.")
    return redirect(url_for("index"))


@app.post("/logout")
def cerrar_sesion():
    if rechazar_si_csrf_invalido():
        return redirect(url_for("index", _anchor="comentarios"))

    session.clear()
    guardar_mensaje("Sesión cerrada.")
    return redirect(url_for("index"))


@app.post("/comentarios")
def crear_comentario():
    if rechazar_si_csrf_invalido():
        return redirect(url_for("index", _anchor="comentarios"))

    usuario = usuario_actual()

    if usuario is None:
        guardar_mensaje("Inicia sesión para comentar.")
        return redirect(url_for("index"))

    if request.form.get("sitio_web", "").strip():
        guardar_mensaje("Comentario bloqueado por validación anti-bot.")
        return redirect(url_for("index"))

    if recaptcha_configurado():
        token = request.form.get("g-recaptcha-response", "")

        if not recaptcha_valido(token, request.remote_addr):
            guardar_mensaje("Verificación reCAPTCHA incorrecta. Intenta de nuevo.")
            return redirect(url_for("index"))
    else:
        if not captcha_valido(request.form.get("captcha", "")):
            guardar_mensaje("Captcha incorrecto. Intenta de nuevo.")
            return redirect(url_for("index"))

    contenido = request.form.get("contenido", "").strip()

    if len(contenido) < 5:
        guardar_mensaje("El comentario debe tener al menos 5 caracteres.")
        return redirect(url_for("index"))

    if len(contenido) > 800:
        guardar_mensaje("El comentario no puede superar 800 caracteres.")
        return redirect(url_for("index"))

    ejecutar_sql(
        f"""
        INSERT INTO {TABLA_COMENTARIOS} (usuario_id, contenido, estado)
        VALUES (:usuario_id, :contenido, 'pendiente');
        """,
        {"usuario_id": usuario["id"], "contenido": contenido}
    )
    guardar_mensaje("Comentario enviado. Se publicará cuando el administrador lo apruebe.")

    return redirect(url_for("index"))


@app.post("/comentarios/<int:comentario_id>/editar")
def editar_comentario(comentario_id):
    if rechazar_si_csrf_invalido():
        return redirect(url_for("index", _anchor="mis-comentarios"))

    usuario = usuario_actual()

    if usuario is None:
        guardar_mensaje("Inicia sesión para editar comentarios.")
        return redirect(url_for("index", _anchor="comentarios"))

    contenido = request.form.get("contenido", "").strip()

    if len(contenido) < 5:
        guardar_mensaje("El comentario debe tener al menos 5 caracteres.")
        return redirect(url_for("index", _anchor="mis-comentarios"))

    if len(contenido) > 800:
        guardar_mensaje("El comentario no puede superar 800 caracteres.")
        return redirect(url_for("index", _anchor="mis-comentarios"))

    actualizado = ejecutar_sql(
        f"""
        UPDATE {TABLA_COMENTARIOS}
        SET contenido = :contenido,
            estado = 'pendiente',
            editado_en = NOW(),
            revisado_en = NULL,
            revisado_por = NULL
        WHERE id = :comentario_id
        AND usuario_id = :usuario_id;
        """,
        {
            "contenido": contenido,
            "comentario_id": comentario_id,
            "usuario_id": usuario["id"]
        }
    )

    guardar_mensaje(
        "Comentario actualizado y enviado de nuevo a revisión."
        if actualizado else
        "No se pudo editar ese comentario."
    )
    return redirect(url_for("index", _anchor="mis-comentarios"))


@app.post("/comentarios/<int:comentario_id>/eliminar")
def eliminar_comentario(comentario_id):
    if rechazar_si_csrf_invalido():
        return redirect(url_for("index", _anchor="mis-comentarios"))

    usuario = usuario_actual()

    if usuario is None:
        guardar_mensaje("Inicia sesión para eliminar comentarios.")
        return redirect(url_for("index", _anchor="comentarios"))

    eliminado = ejecutar_sql(
        f"""
        DELETE FROM {TABLA_COMENTARIOS}
        WHERE id = :comentario_id
        AND usuario_id = :usuario_id;
        """,
        {
            "comentario_id": comentario_id,
            "usuario_id": usuario["id"]
        }
    )

    guardar_mensaje("Comentario eliminado." if eliminado else "No se pudo eliminar ese comentario.")
    return redirect(url_for("index", _anchor="mis-comentarios"))


@app.post("/cuenta/cambiar-password")
def cambiar_password():
    if rechazar_si_csrf_invalido():
        return redirect(url_for("index", _anchor="cuenta"))

    usuario = usuario_actual()

    if usuario is None:
        guardar_mensaje("Inicia sesión para cambiar tu contraseña.")
        return redirect(url_for("index", _anchor="comentarios"))

    if usuario["proveedor"] != "local":
        guardar_mensaje("Las cuentas de Google cambian su contraseña desde Google.")
        return redirect(url_for("index", _anchor="cuenta"))

    password_actual = request.form.get("password_actual", "")
    password_nueva = request.form.get("password_nueva", "")
    password_confirmacion = request.form.get("password_confirmacion", "")

    if len(password_nueva) < 8:
        guardar_mensaje("La nueva contraseña debe tener al menos 8 caracteres.")
        return redirect(url_for("index", _anchor="cuenta"))

    if password_nueva != password_confirmacion:
        guardar_mensaje("La confirmación de contraseña no coincide.")
        return redirect(url_for("index", _anchor="cuenta"))

    cuenta = obtener_una_fila(
        f"SELECT password_hash FROM {TABLA_USUARIOS} WHERE id = :usuario_id AND proveedor = 'local';",
        {"usuario_id": usuario["id"]}
    )

    if not cuenta or not check_password_hash(cuenta["password_hash"], password_actual):
        guardar_mensaje("La contraseña actual no es correcta.")
        return redirect(url_for("index", _anchor="cuenta"))

    ejecutar_sql(
        f"UPDATE {TABLA_USUARIOS} SET password_hash = :password_hash WHERE id = :usuario_id;",
        {"password_hash": generate_password_hash(password_nueva), "usuario_id": usuario["id"]}
    )
    guardar_mensaje("Contraseña actualizada.")
    return redirect(url_for("index", _anchor="cuenta"))


@app.post("/cuenta/cambiar-email")
def cambiar_email():
    if rechazar_si_csrf_invalido():
        return redirect(url_for("index", _anchor="cuenta"))

    usuario = usuario_actual()

    if usuario is None:
        guardar_mensaje("Inicia sesión para cambiar tu correo.")
        return redirect(url_for("index", _anchor="comentarios"))

    if usuario["proveedor"] != "local":
        guardar_mensaje("Las cuentas externas administran su correo desde su proveedor.")
        return redirect(url_for("index", _anchor="cuenta"))

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not email_valido(email):
        guardar_mensaje("Escribe un correo válido.")
        return redirect(url_for("index", _anchor="cuenta"))

    cuenta = obtener_una_fila(
        f"SELECT password_hash FROM {TABLA_USUARIOS} WHERE id = :usuario_id AND proveedor = 'local';",
        {"usuario_id": usuario["id"]}
    )

    if not cuenta or not check_password_hash(cuenta["password_hash"], password):
        guardar_mensaje("La contraseña no es correcta.")
        return redirect(url_for("index", _anchor="cuenta"))

    ejecutar_sql(
        f"UPDATE {TABLA_USUARIOS} SET email = :email WHERE id = :usuario_id;",
        {"email": email, "usuario_id": usuario["id"]}
    )
    guardar_mensaje("Correo de recuperación actualizado.")
    return redirect(url_for("index", _anchor="cuenta"))


@app.post("/cuenta/eliminar")
def eliminar_cuenta():
    if rechazar_si_csrf_invalido():
        return redirect(url_for("index", _anchor="cuenta"))

    usuario = usuario_actual()

    if usuario is None:
        guardar_mensaje("Inicia sesión para eliminar tu cuenta.")
        return redirect(url_for("index", _anchor="comentarios"))

    confirmacion = request.form.get("confirmacion", "").strip()

    if confirmacion != "ELIMINAR":
        guardar_mensaje("Escribe ELIMINAR para confirmar la eliminación de tu cuenta.")
        return redirect(url_for("index", _anchor="cuenta"))

    if usuario["proveedor"] == "local":
        password = request.form.get("password", "")
        cuenta = obtener_una_fila(
            f"SELECT password_hash FROM {TABLA_USUARIOS} WHERE id = :usuario_id AND proveedor = 'local';",
            {"usuario_id": usuario["id"]}
        )

        if not cuenta or not check_password_hash(cuenta["password_hash"], password):
            guardar_mensaje("La contraseña no es correcta.")
            return redirect(url_for("index", _anchor="cuenta"))

    ejecutar_sql(
        f"DELETE FROM {TABLA_USUARIOS} WHERE id = :usuario_id;",
        {"usuario_id": usuario["id"]}
    )
    session.clear()
    guardar_mensaje("Cuenta eliminada.")
    return redirect(url_for("index", _anchor="comentarios"))


@app.get("/admin")
@requiere_admin
def panel_admin():
    return render_template(
        "admin.html",
        usuario=usuario_actual(),
        comentarios=comentarios_admin(),
        resumen=resumen_admin(),
        mensaje=mensaje_flash()
    )


@app.post("/admin/comentarios/<int:comentario_id>/<accion>")
@requiere_admin
def moderar_comentario(comentario_id, accion):
    if rechazar_si_csrf_invalido():
        return redirect(url_for("panel_admin"))

    if accion not in {"aprobar", "rechazar"}:
        abort(404)

    nuevo_estado = "aprobado" if accion == "aprobar" else "rechazado"
    administrador = usuario_actual()
    actualizado = ejecutar_sql(
        f"""
        UPDATE {TABLA_COMENTARIOS}
        SET estado = :estado,
            revisado_en = NOW(),
            revisado_por = :admin_id
        WHERE id = :comentario_id;
        """,
        {
            "estado": nuevo_estado,
            "admin_id": administrador["id"],
            "comentario_id": comentario_id
        }
    )

    guardar_mensaje("Comentario actualizado." if actualizado else "No se pudo actualizar el comentario.")
    return redirect(url_for("panel_admin"))


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
    seguridad = {
        "authlib_disponible": OAuth is not None,
        "authlib_error": AUTHLIB_IMPORT_ERROR,
        "google_client_id_configurado": bool(os.getenv("GOOGLE_CLIENT_ID")),
        "google_client_secret_configurado": bool(os.getenv("GOOGLE_CLIENT_SECRET")),
        "google_login_disponible": registrar_google_oauth(),
        "github_login_disponible": registrar_github_oauth(),
        "microsoft_login_disponible": registrar_microsoft_oauth(),
        "smtp_recuperacion_configurado": smtp_configurado(),
        "recaptcha_site_key_configurado": bool(recaptcha_site_key()),
        "recaptcha_secret_key_configurado": bool(recaptcha_secret_key()),
        "admin_configurado": bool(os.getenv("ADMIN_USER") and os.getenv("ADMIN_PASSWORD"))
    }
    seguridad.update(diagnostico_admin())

    datos = {
        "tabla_humedal": TABLA_HUMEDAL,
        "tabla_edificios": TABLA_EDIFICIOS,
        "seguridad": seguridad,
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



