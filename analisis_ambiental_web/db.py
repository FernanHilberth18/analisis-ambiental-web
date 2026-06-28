import os

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "analisis_ambiental")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300
)


def obtener_una_fila(sql, parametros=None):
    try:
        with engine.connect() as conn:
            resultado = conn.execute(text(sql), parametros or {})
            fila = resultado.mappings().first()

            if fila is None:
                return {}

            return dict(fila)

    except SQLAlchemyError as error:
        print("Error en obtener_una_fila:", error)
        return {}


def obtener_varias_filas(sql, parametros=None):
    try:
        with engine.connect() as conn:
            resultado = conn.execute(text(sql), parametros or {})
            filas = resultado.mappings().all()

            return [dict(fila) for fila in filas]

    except SQLAlchemyError as error:
        print("Error en obtener_varias_filas:", error)
        return []


def ejecutar_sql(sql, parametros=None):
    try:
        with engine.begin() as conn:
            conn.execute(text(sql), parametros or {})
            return True

    except SQLAlchemyError as error:
        print("Error en ejecutar_sql:", error)
        return False
