"""Screening list and outreach log. Invites are static rows; everything that happens to them is an append-only outreach event
(screened, barrier = Pulse PU3, sms_sent, call_listed, called). Status is derived. SYNTHETIC data. Same DB layer as the event store."""
import json
import queue
import threading
import time

from engine.domain import parse_ts, fmt_ts, days_between

INV_DDL = """create table if not exists screening_invites (
  id text primary key, county text, programme text, name text, age integer, language text, invited_ts text)"""
EV_DDL = """create table if not exists outreach_events (
  id bigint primary key, ts text not null, invite_id text not null, type text not null, value text, entered_by text)"""
INV_COLS = "id, county, programme, name, age, language, invited_ts"
EV_COLS = "id, ts, invite_id, type, value, entered_by"
PENDING_DAYS = 28   # invited less than this long ago and not screened: still pending, not a non-responder


class Screening:
    def __init__(self, db):
        self.db = db
        self.lock = threading.RLock()
        self.invites, self.events = {}, {}
        self.next_id, self.version, self.write_errors = 1, 0, 0
        self._q = queue.Queue()
        db.execute(INV_DDL)
        db.execute(EV_DDL)
        for r in db.query(f"select {INV_COLS} from screening_invites"):
            d = dict(zip(INV_COLS.replace(" ", "").split(","), r))
            self.invites[d["id"]] = d
            self.events[d["id"]] = []
        for r in db.query(f"select {EV_COLS} from outreach_events order by id"):
            e = dict(zip(EV_COLS.replace(" ", "").split(","), r))
            self.events.setdefault(e["invite_id"], []).append(e)
            self.next_id = max(self.next_id, e["id"] + 1)
        threading.Thread(target=self._writer, daemon=True, name="screening-writer").start()

    def _writer(self):
        while True:
            batch = [self._q.get()]
            while len(batch) < 500:
                try:
                    batch.append(self._q.get_nowait())
                except queue.Empty:
                    break
            inv = [r for k, r in batch if k == "inv"]
            evs = [r for k, r in batch if k == "ev"]
            while True:
                try:
                    if inv:
                        self.db.executemany(f"insert into screening_invites ({INV_COLS}) values (?,?,?,?,?,?,?)", inv)
                    if evs:
                        self.db.executemany(f"insert into outreach_events ({EV_COLS}) values (?,?,?,?,?,?)", evs)
                    break
                except Exception:
                    self.write_errors += 1
                    time.sleep(2)

    def add_invite(self, d):
        with self.lock:
            self.invites[d["id"]] = d
            self.events.setdefault(d["id"], [])
            self._q.put(("inv", tuple(d[c.strip()] for c in INV_COLS.split(","))))

    def append(self, invite_id, type_, ts, value=None, by=None):
        if not isinstance(ts, str):
            ts = fmt_ts(ts)
        if value is not None and not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)
        with self.lock:
            e = dict(id=self.next_id, ts=ts, invite_id=invite_id, type=type_, value=value, entered_by=by)
            self.next_id += 1
            self.events[invite_id].append(e)
            self.version += 1
            self._q.put(("ev", (e["id"], ts, invite_id, type_, value, by)))
            return e

    def state(self, invite_id, now):
        """Derived status of one invite."""
        inv, evs = self.invites[invite_id], self.events[invite_id]
        types = [e["type"] for e in evs]
        screened = "screened" in types
        days = days_between(parse_ts(inv["invited_ts"]), now)
        barrier = next((e["value"] for e in reversed(evs) if e["type"] == "barrier"), None)
        listed = next((e for e in reversed(evs) if e["type"] == "call_listed"), None)
        called = next((e for e in reversed(evs) if e["type"] == "called"), None)
        return dict(**inv, status="screened" if screened else ("pending" if days <= PENDING_DAYS else "non_responder"), days=int(days),
                    contacted="sms_sent" in types, barrier=barrier,
                    on_call_list=bool(listed and not (called and called["id"] > listed["id"])), called=bool(called and (not listed or called["id"] > listed["id"])))
