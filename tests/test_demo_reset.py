"""Reset regression: two clean, repeatable synthetic demo starts."""
import os
import pathlib
import tempfile
import unittest

os.environ["HV_FORCE_SQLITE"] = "1"
os.environ["HV_SIM"] = "0"
os.environ["HV_DEMO_OPEN"] = "0"

from act import worklist
from aggregate.kpis import kpis
from app.store import DB
from api import main
from sim.live import Simulator
from store.board import Board
from store.events import EventStore
from store.screening import Screening


class DemoResetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hv-demo-reset-")
        db = DB(sqlite_path=pathlib.Path(self.tmp.name) / "events.db")
        st = EventStore(db)
        scr = Screening(db)
        main.S.update(store=st, sim=Simulator(st), board=Board(db), screening=scr)

    def tearDown(self):
        sim = main.S.get("sim")
        if sim:
            sim.stop()
        self.tmp.cleanup()

    def snapshot(self):
        st, sm = main.S["store"], main.S["sim"]
        today = worklist.worklist(st, "Laura", 5)
        selected = [
            (r["id"], r["name"], r["day"], r["step"], r["reason"])
            for r in today["rows"]
        ]
        county_tiles = {}
        for county in ("Länsi-Uusimaa", "Helsinki", "Vantaa–Kerava"):
            tile = kpis(st, county)
            county_tiles[county] = tuple(tile[k] for k in ("informed_pct", "reached_1wd_pct", "distress_pct", "nps"))
            self.assertTrue(all(value is not None for value in county_tiles[county]), (county, tile))
        total = kpis(st)
        self.assertEqual(sm.clock_mode, "paused")
        self.assertEqual(st.pending_tasks(), [])
        before_tick = st.next_id
        sm._trickle()
        self.assertEqual(st.next_id, before_tick, "paused reset must not append simulator Pulse events")
        self.assertEqual(st.db.query("select count(*) from voice_call")[0][0], 0)
        self.assertEqual(selected[0][0], "PW-D1")
        self.assertFalse(any(e["type"].startswith("companion") or e["type"] == "message" for e in st.log))
        self.assertEqual(sum(1 for e in st.log if e["type"] == "pulse:PU9b" and e["source"] == "pulse:demo-seed"), 3)
        self.assertIsNotNone(total["t0_to_dx_median"])
        self.assertIsNotNone(total["within_6wk_pct"])
        return selected, county_tiles

    def test_reset_twice_is_clean_and_repeats_demo_top_rows_and_kpis(self):
        main.demo_reset(main.ResetIn(confirm="reset"))
        old = main.S["store"]
        old.add_task("PW-D3", "callback", "synthetic old test task", assigned_to="Laura")
        old.db.execute("insert into voice_call(conversation_id, ts, caller_type, language, summary, review_needed, raw) values (?,?,?,?,?,?,?)",
                       ("synthetic-test", "2026-11-14T00:00:00+00:00", "patient", "en", "synthetic test", 0, "{}"))
        old.append("PW-D1", "companion_suggested", old.vnow, {"need": "transport"}, source="test", entered_by="test")

        main.demo_reset(main.ResetIn(confirm="reset"))
        first = self.snapshot()
        main.demo_reset(main.ResetIn(confirm="reset"))
        second = self.snapshot()
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
