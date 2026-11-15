"""Board decision log (append-only). The county board accepts or defers suggested decisions; the log is persisted
with the same DB layer as the event store (Aiven PostgreSQL, SQLite fallback)."""
import threading

from engine.domain import UTC, fmt_ts
from datetime import datetime

DDL = """create table if not exists board_decisions (
  id bigint primary key, ts text not null, county text not null, key text not null,
  title text, decision text not null, decided_by text, note text)"""
COLS = "id, ts, county, key, title, decision, decided_by, note"


class Board:
    def __init__(self, db):
        self.db = db
        self.lock = threading.RLock()
        self.rows = []
        db.execute(DDL)
        for r in db.query(f"select {COLS} from board_decisions order by id"):
            self.rows.append(dict(zip(COLS.replace(" ", "").split(","), r)))

    def decide(self, county, key, title, decision, by, note=""):
        with self.lock:
            row = dict(id=(self.rows[-1]["id"] + 1) if self.rows else 1, ts=fmt_ts(datetime.now(UTC)), county=county, key=key,
                       title=title, decision=decision, decided_by=by, note=note)
            self.db.execute(f"insert into board_decisions ({COLS}) values (?,?,?,?,?,?,?,?)", tuple(row[c.strip()] for c in COLS.split(",")))
            self.rows.append(row)
            return row

    def latest(self, county):
        """key -> latest decision row for this county."""
        out = {}
        with self.lock:
            for r in self.rows:
                if r["county"] == county:
                    out[r["key"]] = r
        return out
