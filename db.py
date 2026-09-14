"""
Small MySQL connection helper built on PyMySQL's DictCursor,
so every query already returns rows as dicts (easy to json.dumps).
"""
import pymysql
import pymysql.cursors
from contextlib import contextmanager

from config import DB_CONFIG


def get_connection():
    return pymysql.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
        charset=DB_CONFIG["charset"],
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


@contextmanager
def get_cursor(commit=False):
    """
    Usage:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM bookings")
            rows = cur.fetchall()

        with get_cursor(commit=True) as cur:
            cur.execute("INSERT INTO bookings ...")
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
