"""DB layer: Aiven PostgreSQL via DATABASE_URL, falling back to a local SQLite file so the demo never breaks.
SQL is written with `?` placeholders and translated for Postgres. One connection, guarded by a lock.
Free Aiven plans sleep when idle: the first connect can take several seconds."""
import os
import pathlib
import sqlite3
import threading

from app import llm  # noqa: F401  (loads .env for local runs)

LOCAL = pathlib.Path(__file__).parent.parent / "data" / "hoitovirta.db"


class DB:
    def __init__(self, sqlite_path=None):
        self.lock = threading.RLock()
        self.sqlite_path = pathlib.Path(sqlite_path) if sqlite_path else LOCAL
        self.backend = "none"
        self.error = None
        self.conn = None
        self._connect()

    def _connect(self):
        url = os.getenv("DATABASE_URL")
        if url and not os.getenv("HV_FORCE_SQLITE"):
            try:
                import psycopg
                self.conn = psycopg.connect(url, connect_timeout=15, autocommit=True)
                # own schema: never touches tables from earlier prototypes in the same database
                self.conn.execute("create schema if not exists hv")
                self.conn.execute("set search_path to hv")
                self.backend = "postgres"
                return
            except Exception as e:  # keep the reason, never the URL
                self.error = type(e).__name__
        self.conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
        self.conn.execute("pragma journal_mode=wal")
        self.backend = "sqlite"

    @property
    def label(self):
        return "Aiven PostgreSQL" if self.backend == "postgres" else "local SQLite"

    def _sql(self, sql):
        return sql.replace("?", "%s") if self.backend == "postgres" else sql

    def execute(self, sql, params=()):
        with self.lock:
            cur = self.conn.execute(self._sql(sql), params)
            if self.backend == "sqlite":
                self.conn.commit()
            return cur

    def executemany(self, sql, rows):
        with self.lock:
            cur = self.conn.cursor()
            cur.executemany(self._sql(sql), rows)
            if self.backend == "sqlite":
                self.conn.commit()

    def query(self, sql, params=()):
        with self.lock:
            cur = self.conn.execute(self._sql(sql), params)
            return cur.fetchall()
