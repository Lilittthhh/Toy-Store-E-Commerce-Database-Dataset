from __future__ import annotations
import psycopg2
import config as cfg

def connect(autocommit: bool = False):
    conn = psycopg2.connect(
        host=cfg.PG_HOST,
        port=cfg.PG_PORT,
        dbname=cfg.PG_DATABASE,
        user=cfg.PG_USER,
        password=cfg.PG_PASSWORD,
    )
    conn.autocommit = autocommit
    return conn
