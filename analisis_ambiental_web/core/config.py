import os


class Config:
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024
    JSON_SORT_KEYS = False
    SECRET_KEY = os.getenv("SECRET_KEY", "clave-local-de-desarrollo")

