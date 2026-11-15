"""Append-only event store with an in-memory read model.
Reads are served from memory (fast, even over a WAN to Postgres). Every write is appended in memory and
written behind to the DB (Aiven PostgreSQL, SQLite fallback) by a background thread. Single-process by design."""
import json
import queue
import threading
import time
import uuid
from datetime import datetime

from app.store import DB
from engine import state as st
from engine.domain import UTC, fmt_ts, parse_ts
from store.schema import (ACCESS_LOG_DDL, EVENTS_DDL, EVENTS_IDX, PATHWAYS_DDL, TASK_DDL, TASK_IDX,
                          VOICE_CALL_DDL)

EV_COLS = "id, pathway_id, ts, type, value, unit, source, confidence, entered_by"
PW_COLS = "id, name, age, sex, language, county, cancer, onset_days, interpreter"


class EventStore:
    def __init__(self, db=None):
        self.db = db or DB()
        self.lock = threading.RLock()
        self.meta = {}        # pathway id -> meta dict
        self.events = {}      # pathway id -> [event dicts in append order]
        self.log = []         # all events in append order (the global stream)
        self.next_id = 1
        self.version = 0
        self.vnow = None      # virtual "now" (datetime, UTC): the simulator advances it
        self._facts = {}
        self.human_new = {}   # pathway id -> real time a human nurse fast-tracked it (in memory only)
        self._q = queue.Queue()
        self.write_errors = 0
        self.db.execute(EVENTS_DDL)
        self.db.execute(EVENTS_IDX)
        self.db.execute(PATHWAYS_DDL)
        self.db.execute(VOICE_CALL_DDL)
        self.db.execute(TASK_DDL)
        self.db.execute(TASK_IDX)
        self.db.execute(ACCESS_LOG_DDL)
        self.tasks = []
        self._load()
        threading.Thread(target=self._writer, daemon=True, name="event-writer").start()

    # ---- load / persist --------------------------------------------------------
    def _load(self):
        for r in self.db.query(f"select {PW_COLS} from pathways"):
            m = dict(zip(PW_COLS.replace(" ", "").split(","), r))
            m["interpreter"] = bool(m["interpreter"])
            self.meta[m["id"]] = m
            self.events[m["id"]] = []
        for r in self.db.query(f"select {EV_COLS} from events order by id"):
            e = dict(zip(EV_COLS.replace(" ", "").split(","), r))
            self.events.setdefault(e["pathway_id"], []).append(e)
            self.log.append(e)
            self.next_id = max(self.next_id, e["id"] + 1)
        if self.log:
            self.vnow = max(parse_ts(e["ts"]) for e in self.log)
        for r in self.db.query("select id, pathway_id, ts, kind, detail, done, assigned_to from task order by ts"):
            self.tasks.append(dict(zip(("id", "pathway_id", "ts", "kind", "detail", "done", "assigned_to"), r), done=bool(r[5])))

    def _writer(self):
        while True:
            batch = [self._q.get()]
            while len(batch) < 500:
                try:
                    batch.append(self._q.get_nowait())
                except queue.Empty:
                    break
            pws = [r for k, r in batch if k == "pathway"]
            evs = [r for k, r in batch if k == "event"]
            while True:
                try:
                    if pws:
                        self.db.executemany(f"insert into pathways ({PW_COLS}) values (?,?,?,?,?,?,?,?,?)", pws)
                    if evs:
                        self.db.executemany(f"insert into events ({EV_COLS}) values (?,?,?,?,?,?,?,?,?)", evs)
                    break
                except Exception:
                    self.write_errors += 1
                    time.sleep(2)  # keep the batch, retry (DB may be waking up)

    def pending_writes(self):
        return self._q.qsize()

    # ---- writes -----------------------------------------------------------------
    def add_pathway(self, m):
        with self.lock:
            self.meta[m["id"]] = m
            self.events.setdefault(m["id"], [])
            self._q.put(("pathway", (m["id"], m["name"], m["age"], m["sex"], m["language"], m["county"], m["cancer"],
                                     m["onset_days"], int(bool(m["interpreter"])))))
            self.version += 1

    def append(self, pathway_id, type_, ts, value=None, unit=None, source=None, confidence=None, entered_by=None):
        if isinstance(ts, datetime):
            ts = fmt_ts(ts)
        if value is not None and not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)
        with self.lock:
            e = dict(id=self.next_id, pathway_id=pathway_id, ts=ts, type=type_, value=value, unit=unit, source=source,
                     confidence=confidence, entered_by=entered_by)
            self.next_id += 1
            self.events[pathway_id].append(e)
            self.log.append(e)
            self._facts.pop(pathway_id, None)
            self.version += 1
            t = parse_ts(ts)
            if self.vnow is None or t > self.vnow:
                self.vnow = t
            self._q.put(("event", (e["id"], pathway_id, ts, type_, value, unit, source, confidence, entered_by)))
            return e

    # ---- reads --------------------------------------------------------------------
    def facts(self, pid):
        with self.lock:
            f = self._facts.get(pid)
            if f is None:
                f = st.build(self.meta[pid], self.events[pid])
                self._facts[pid] = f
            return f

    def view(self, pid, now=None):
        return st.view(self.facts(pid), now or self.vnow)

    def ids(self):
        with self.lock:
            return list(self.meta)

    def events_for(self, pid):
        with self.lock:
            return list(self.events.get(pid, []))

    # ---- voice service records and coordinator tasks --------------------------
    def add_voice_call(self, conversation_id, ts, caller_type, language, summary, review_needed, raw):
        self.db.execute("""insert into voice_call (conversation_id, ts, caller_type, language, summary, review_needed, raw)
          values (?,?,?,?,?,?,?) on conflict (conversation_id) do update set ts=excluded.ts,
          caller_type=excluded.caller_type, language=excluded.language, summary=excluded.summary,
          review_needed=excluded.review_needed, raw=excluded.raw""",
          (conversation_id, ts, caller_type, language, summary, int(bool(review_needed)), raw))

    def add_task(self, pathway_id, kind, detail, ts=None, assigned_to=None):
        ts = fmt_ts(ts or datetime.now(UTC))
        row = dict(id=str(uuid.uuid4()), pathway_id=pathway_id, ts=ts, kind=kind, detail=detail,
                   done=False, assigned_to=assigned_to)
        self.db.execute("insert into task (id, pathway_id, ts, kind, detail, done, assigned_to) values (?,?,?,?,?,?,?)",
                        (row["id"], pathway_id, ts, kind, detail, 0, assigned_to))
        with self.lock:
            self.tasks.append(row)
        return row

    def pending_tasks(self, assigned_to=None, pathway_id=None):
        with self.lock:
            return [dict(t) for t in self.tasks if not t["done"]
                    and (assigned_to is None or t["assigned_to"] == assigned_to)
                    and (pathway_id is None or t["pathway_id"] == pathway_id)]

    def complete_task(self, task_id):
        """Mark one existing coordinator task done in both the live read model and DB."""
        with self.lock:
            task = next((t for t in self.tasks if t["id"] == task_id), None)
            if not task:
                return False
            if task["done"]:
                return True
            self.db.execute("update task set done=1 where id=?", (task_id,))
            task["done"] = True
            self.version += 1
            return True

    def log_access(self, staff_id, role, action, ok, pathway_id="", ts=None):
        self.db.execute("insert into access_log (id, ts, staff_id, role, action, ok, pathway_id) values (?,?,?,?,?,?,?)",
                        (str(uuid.uuid4()), fmt_ts(ts or datetime.now(UTC)), staff_id, role, action, int(bool(ok)), pathway_id))
