"""Tests for ingest.py. Run: python -m unittest discover -s scripts"""
import copy
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone

import ingest

HERE = os.path.dirname(os.path.abspath(__file__))
TOP50 = json.load(open(os.path.join(HERE, "fixtures", "top50.json"), encoding="utf-8"))
CAL = json.load(open(os.path.join(HERE, "..", "data", "calendar.json"), encoding="utf-8"))


def ms(iso):
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def by_name(entries, name):
    return next(e for e in entries if e["name"] == name)


def next_round(entries):
    """A made-up next round from the real top 50."""
    cur = copy.deepcopy(entries)
    by_name(cur, "Red Corsairs")["trophies"] = 1012        # win + promotion Gold IV -> Diamond I
    by_name(cur, "Red Corsairs")["league"] = 16
    by_name(cur, "Solar")["trophies"] -= 30                 # loss
    by_name(cur, "Unessentials")["trophies"] += 29          # win
    by_name(cur, "Unessentials")["name"] = "Unessentials Renamed"  # rename: same guildId
    dropped = cur.pop()                                     # #50 leaves the top 50
    cur.append({"rank": 0, "guildId": "new-guild-id", "name": "Newcomers", "tag": "NEWCO",
                "trophies": dropped["trophies"] + 20, "league": 14, "guildLevel": 39,
                "members": 30, "country": "FR"})
    cur.sort(key=lambda e: -e["trophies"])
    for i, e in enumerate(cur):
        e["rank"] = i + 1
    return cur, dropped


class RoundsTest(unittest.TestCase):
    def test_round_numbers_follow_the_war_calendar(self):
        # Round 2's war phase (the Vermilion war) ran 2026-09-21 21:32 -> 2026-09-23 09:32 UTC.
        self.assertEqual(ingest.after_round(ms("2026-09-19T12:00:00Z"), CAL), (27, 0))  # war 1 being fought
        self.assertEqual(ingest.after_round(ms("2026-09-20T21:40:00Z"), CAL), (27, 1))
        self.assertEqual(ingest.after_round(ms("2026-09-23T09:20:00Z"), CAL), (27, 1))  # round 2 still being fought
        self.assertEqual(ingest.after_round(ms("2026-09-23T19:45:00Z"), CAL), (27, 2))  # our 23 Sep capture
        self.assertEqual(ingest.after_round(ms("2026-09-25T09:11:00Z"), CAL), (27, 2))  # during round 3
        self.assertEqual(ingest.after_round(ms("2026-09-25T21:40:00Z"), CAL), (27, 3))

    def test_break_after_war_6_and_next_season(self):
        # War 6 ends 2026-10-03 09:32 UTC; season 28 war 1 starts 28 days after season 27's
        # (2026-10-17 09:32 UTC). Until then it's the break: still "after round 6".
        self.assertEqual(ingest.after_round(ms("2026-10-03T09:00:00Z"), CAL), (27, 5))
        self.assertEqual(ingest.after_round(ms("2026-10-05T12:00:00Z"), CAL), (27, 6))
        self.assertEqual(ingest.after_round(ms("2026-10-17T09:00:00Z"), CAL), (27, 6))
        self.assertEqual(ingest.after_round(ms("2026-10-17T12:00:00Z"), CAL), (28, 0))
        self.assertEqual(ingest.after_round(ms("2026-10-18T22:00:00Z"), CAL), (28, 1))


class DiffTest(unittest.TestCase):
    def setUp(self):
        self.cur, self.dropped = next_round(TOP50)
        self.r = ingest.diff(TOP50, self.cur)

    def test_wins_losses_and_idle(self):
        self.assertEqual([x["name"] for x in self.r["lost"]], ["Solar"])
        self.assertEqual(self.r["lost"][0]["dT"], -30)
        won = {x["name"]: x["dT"] for x in self.r["won"]}
        self.assertEqual(won["Red Corsairs"], 24)
        self.assertEqual(won["Unessentials Renamed"], 29)
        self.assertEqual(self.r["idleCount"], 49 - 3)  # 49 guilds carried over, 3 of them changed

    def test_promotion(self):
        self.assertEqual([(x["name"], x["prevLeague"], x["league"]) for x in self.r["promoted"]],
                         [("Red Corsairs", 15, 16)])
        self.assertEqual(self.r["demoted"], [])

    def test_entered_and_left(self):
        self.assertEqual([x["name"] for x in self.r["entered"]], ["Newcomers"])
        self.assertEqual([x["name"] for x in self.r["left"]], [self.dropped["name"]])

    def test_rename_is_the_same_guild(self):
        row = next(x for x in self.r["table"] if x["name"] == "Unessentials Renamed")
        self.assertFalse(row["isNew"])
        self.assertEqual(row["prevName"], "Unessentials")

    def test_rank_moves(self):
        rc = next(x for x in self.r["table"] if x["name"] == "Red Corsairs")
        self.assertEqual(rc["rank"], 2)
        self.assertEqual(rc["dR"], 0)
        self.assertTrue(all(x["dR"] > 0 for x in self.r["climbers"]))
        self.assertTrue(all(x["dR"] < 0 for x in self.r["fallers"]))

    def test_summary_says_top_50_and_names_the_loser(self):
        text = "".join(p["t"] for p in self.r["summary"])
        self.assertIn("top 50", text)
        self.assertIn("only 1 guild lost", text)
        self.assertIn("Solar", text)
        self.assertIn("Red Corsairs", text)
        self.assertIn("Newcomers", text)
        self.assertNotIn(self.dropped["name"] + " lost", text)


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "data", "snapshots"))
        shutil.copy(os.path.join(HERE, "..", "data", "calendar.json"), os.path.join(self.root, "data"))

    def tearDown(self):
        shutil.rmtree(self.root)

    def feed(self, entries, captured):
        return {"status": "ok", "snapshot": {"capturedAt": ms(captured), "entries": entries}}

    def test_new_snapshot_then_duplicate(self):
        self.assertTrue(ingest.ingest(self.feed(TOP50, "2026-09-23T19:45:00Z"), self.root))
        self.assertFalse(ingest.ingest(self.feed(TOP50, "2026-09-23T19:45:00Z"), self.root))  # same capture
        self.assertFalse(ingest.ingest(self.feed(TOP50, "2026-09-25T09:11:00Z"), self.root))  # same entries later
        self.assertEqual(len(os.listdir(os.path.join(self.root, "data", "snapshots"))), 1)

    def test_bad_feed_changes_nothing(self):
        for bad in ({"status": "no_snapshot"}, {"status": "ok", "snapshot": {"capturedAt": 1, "entries": []}},
                    {"status": "ok", "snapshot": {"capturedAt": 1, "entries": [{"name": "x"}]}}):
            self.assertFalse(ingest.ingest(bad, self.root))
        self.assertEqual(os.listdir(os.path.join(self.root, "data", "snapshots")), [])

    def test_build_reports_per_round(self):
        cur, _ = next_round(TOP50)
        ingest.ingest(self.feed(TOP50, "2026-09-23T19:45:00Z"), self.root)   # after round 2
        ingest.ingest(self.feed(cur, "2026-09-25T22:00:00Z"), self.root)     # after round 3
        out = json.load(open(os.path.join(self.root, "data", "league.json"), encoding="utf-8"))
        self.assertEqual(out["latest"], "27-3")
        self.assertIsNone(out["reports"]["27-2"]["comparedWith"])          # first capture: table only
        r3 = out["reports"]["27-3"]
        self.assertEqual(r3["comparedWith"], {"season": 27, "round": 2})
        self.assertEqual([x["name"] for x in r3["lost"]], ["Solar"])
        self.assertEqual(out["seasons"], [{"season": 27, "rounds": [2, 3]}])
        rc = by_name(TOP50, "Red Corsairs")["guildId"]
        self.assertEqual([h["trophies"] for h in out["history"][rc]], [988, 1012])

    def test_gap_is_labelled(self):
        cur, _ = next_round(TOP50)
        ingest.ingest(self.feed(TOP50, "2026-09-23T19:45:00Z"), self.root)   # after round 2
        ingest.ingest(self.feed(cur, "2026-09-28T12:00:00Z"), self.root)     # after round 4 (round 3 missed)
        r = json.load(open(os.path.join(self.root, "data", "league.json"), encoding="utf-8"))["reports"]["27-4"]
        self.assertEqual(r["covers"], [3, 4])


if __name__ == "__main__":
    unittest.main()
