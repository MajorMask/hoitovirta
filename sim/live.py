"""Live simulator: synthetic pathways advance in real time (about 1 event every 2-5 s), new suspicions arrive,
and the nurse's incoming-call queue refills. Coordinator actions (bookings) reschedule a pathway immediately."""
import heapq
import itertools
import random
import threading
import time
from datetime import timedelta

from engine import pulse, rules
from engine.domain import COORDINATORS, COUNTIES, FLAG_CANCER, RED_FLAGS, STEPS
from sim import apply as ap
from sim import model
from sim.people import FLAG_W, make_call, person, pick

CALLS_PER_COUNTY = 5
# Virtual seconds that pass per real second. 'normal' = one virtual day per 6 real hours, so the demo patients stay at about day 12.
# 'fast' = one virtual day per minute, to show pathways and the 14-day forecast playing out. 'paused' freezes time, but activity
# (new fast-tracks, Pulse answers, SMS replies) and every human action keep working.
CLOCK_RATES = {"paused": 0, "normal": 4, "fast": 1440}
MAX_EVENTS_PER_TICK = 40


class Simulator:
    def __init__(self, store):
        self.store = store
        self.heap, self.tok, self.seq = [], {}, itertools.count()
        self.calls = {c: [] for c in COUNTIES}
        self.call_seq = itertools.count(1)
        self.r = random.Random()
        self.clock_mode = "normal"
        self._clock_real = time.time()
        self._tried = set()     # (pathway, moment) pairs the Pulse trickle already tried
        self.running = False
        self.ticks = 0
        self.last_event = None
        self.screening = None      # set by the API: the screening list, for outreach replies
        self.out_q = []            # (real due time, seq, invite id, outcome) replies to approved SMS
        self.thread = None
        with store.lock:
            for pid in store.ids():
                self.schedule(pid)
        self.refill_calls()

    # ---- scheduling ------------------------------------------------------------------
    def schedule(self, pid):
        with self.store.lock:
            self.tok[pid] = self.tok.get(pid, 0) + 1
            for item in model.plan_items(self.store.facts(pid)):
                heapq.heappush(self.heap, (item[1], next(self.seq), pid, self.tok[pid], item))

    def _pop(self):
        while self.heap:
            ts, _, pid, tok, item = heapq.heappop(self.heap)
            if tok == self.tok.get(pid):
                return pid, item
        return None, None

    # ---- calls queue -------------------------------------------------------------------
    def refill_calls(self):
        for c in COUNTIES:
            while len(self.calls[c]) < CALLS_PER_COUNTY:
                self.calls[c].append(make_call(self.r, c, f"C{next(self.call_seq):04d}"))

    def take_call(self, call_id):
        with self.store.lock:
            for c, lst in self.calls.items():
                for i, call in enumerate(lst):
                    if call["id"] == call_id:
                        return lst.pop(i)
        return None

    # ---- outreach replies (synthetic) -----------------------------------------------------------------
    def schedule_outreach(self, invite_ids):
        """After an approved SMS: some people book and are screened, some reply with their barrier (PU3). Real-time delays, so the
        participation numbers move while you watch. SYNTHETIC response rates."""
        now = time.time()
        with self.store.lock:
            for i in invite_ids:
                lang = self.screening.invites[i]["language"]
                p_scr = 0.30 if lang in ("fi", "sv") else 0.22
                x = self.r.random()
                if x < p_scr:
                    heapq.heappush(self.out_q, (now + self.r.uniform(6, 45), next(self.seq), i, "screened"))
                elif x < p_scr + 0.35:
                    heapq.heappush(self.out_q, (now + self.r.uniform(4, 30), next(self.seq), i, "barrier"))

    def _process_outreach(self):
        if not self.screening:
            return
        from sim.screening import barrier_for
        now = time.time()
        while self.out_q and self.out_q[0][0] <= now:
            _, _, i, outcome = heapq.heappop(self.out_q)
            inv = self.screening.invites[i]
            if self.screening.state(i, self.store.vnow)["status"] == "screened":
                continue
            if outcome == "screened":
                self.screening.append(i, "screened", self.store.vnow, inv["programme"], "system")
            else:
                self.screening.append(i, "barrier", self.store.vnow, barrier_for(self.r, inv["language"]), "patient")

    # ---- clock + one tick ------------------------------------------------------------------
    def set_clock(self, mode):
        if mode not in CLOCK_RATES:
            raise ValueError(mode)
        with self.store.lock:
            self._advance_clock()
            self.clock_mode = mode

    def _advance_clock(self):
        now = time.time()
        dt, self._clock_real = now - self._clock_real, now
        rate = CLOCK_RATES[self.clock_mode]
        if rate and self.store.vnow is not None:
            self.store.vnow = self.store.vnow + timedelta(seconds=dt * rate)

    def _due(self):
        """Pop scheduled items whose virtual time has arrived (stale ones are dropped)."""
        out = []
        while self.heap and len(out) < MAX_EVENTS_PER_TICK:
            ts, _, pid, tok, item = self.heap[0]
            if tok != self.tok.get(pid):
                heapq.heappop(self.heap)
                continue
            if ts > self.store.vnow:
                break
            heapq.heappop(self.heap)
            out.append((pid, item))
        return out

    def tick(self):
        with self.store.lock:
            self._advance_clock()
            for pid, item in self._due():
                ap.apply_item(self.store, pid, item)
                self.last_event = (pid, item[0], item[1])
                if item[0] == "step":
                    self.schedule(pid)
            self._maybe_spawn()
            self._trickle()
            self._process_outreach()
            for pid in self._active_unbooked():
                ap.scan(self.store, pid, self.store.vnow)
            self.ticks += 1
        self.refill_calls()

    def _trickle(self):
        """Synthetic patients answer Pulse questions as time goes by, so the dashboards move even when the clock is slow."""
        if self.clock_mode == "paused":
            return
        if self.r.random() > 0.3:
            return
        ids = self.store.ids()
        for pid in self.r.sample(ids, min(40, len(ids))):
            f = self.store.facts(pid)
            if f["done"] or f["t0_by"] == "nurse:Petra" or f["coordinator"] == ap.DEMO_COORDINATOR.get(f["county"]):
                continue
            pend = pulse.pending(f, self.store.vnow)
            if not pend or (pid, pend["moment"]) in self._tried:
                continue
            self._tried.add((pid, pend["moment"]))
            for item, value in pulse.synth_answers(pid, pend["kind"], f).items():
                self.store.append(pid, f"pulse:{item}", self.store.vnow, value, unit=pend["moment"], source="pulse:sms", entered_by="patient")
            return

    def _active_unbooked(self):
        out = []
        for pid in self.store.ids():
            f = self.store.facts(pid)
            if not f["done"] and not f["booking"] and f["last_ts"] is not None and not f["open_loop"]:
                out.append(pid)
        return out

    def _maybe_spawn(self):
        """A new suspicion arrives via triage roughly every 12 ticks (the simulated nurse's click)."""
        if self.clock_mode == "paused":
            return
        if self.r.random() > {"paused": 0.02, "normal": 0.025, "fast": 0.2}[self.clock_mode]:
            return
        county = self.r.choices(COUNTIES, weights=[0.4, 0.2, 0.15, 0.15, 0.1])[0]
        call = make_call(self.r, county, "sim")
        from act import fasttrack
        fasttrack.start(self.store, self, call, call["suggested_flag"], nurse="sim", take=False)

    # ---- thread ------------------------------------------------------------------------------
    def start(self):
        if self.running:
            return
        self.running = True

        def loop():
            while self.running:
                time.sleep(self.r.uniform(2, 5))
                try:
                    self.tick()
                except Exception as e:  # never kill the simulator
                    self.error = f"{type(e).__name__}: {e}"
        self.thread = threading.Thread(target=loop, daemon=True, name="simulator")
        self.thread.start()

    def stop(self):
        self.running = False
