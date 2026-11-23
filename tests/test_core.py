import unittest, copy
from orgtwin.seed import build
from orgtwin.memory import Memory

INC, OK = "INC-2026-001", "TRX-2026-114"


class T(unittest.TestCase):
    def setUp(self):
        self.t = build()

    def test_impact_ranks_direct_dependents_first(self):
        r = self.t.g.impact("sys:ocr", "degrade")
        self.assertEqual(r[0]["id"], "agent:paybot")
        ids = [x["id"] for x in r]
        self.assertIn("proc:close", ids)
        self.assertTrue(all(r[i]["exposure"] >= r[i + 1]["exposure"] for i in range(len(r) - 1)))

    def test_removing_control_is_treated_as_relaxing_it(self):
        s = self.t.simulate("pol:approval", "remove")
        self.assertEqual(s["change"], "relax")
        self.assertIn("DEC-009", [d["id"] for d in s["relied_on_by"]])
        self.assertIn(INC, s["seen_in_incidents"])

    def test_memory_search_and_arabic_normalisation(self):
        self.assertEqual(self.t.mem.search("why skip PO matching for trusted vendors")[0]["id"], "DEC-009")
        m = Memory([{"id": "A", "title": "إلغاء الموافقة", "text": "أي دفعة", "nodes": []}])
        self.assertTrue(m.search("الغاء الموافقه") or m.search("الغاء الموافقة"))

    def test_hash_chain_detects_tampering(self):
        self.assertTrue(self.t.bb.verify()["ok"])
        self.t.bb.events[1]["outputs"]["amount"] = 12500.0
        v = self.t.bb.verify()
        self.assertFalse(v["ok"])
        self.assertEqual(v["broken_at"], f"{INC}-E2")

    def test_root_cause_is_the_first_divergence_not_the_last_symptom(self):
        r = self.t.report(INC)
        self.assertEqual(r["root_cause"]["event"], f"{INC}-E2")
        self.assertEqual(r["root_cause"]["kind"], "data_divergence")
        self.assertEqual(r["loss"], 112500)
        self.assertEqual(r["originator"]["actor"], "human:ap_clerk")
        self.assertEqual(r["detection_lag_hours"], 49.0)
        self.assertEqual([v["control"] for v in r["violations"]], ["CTL-1"])
        self.assertEqual(r["violations"][0]["bypass"], f"{INC}-E5")
        self.assertEqual(r["permissions_used"][0]["permission"], "treasury.transfer<=200000")
        self.assertTrue({"DEC-009", "DEC-014", "CHG-022"} <= {d["id"] for d in r["decisions"]})

    def test_healthy_run_has_no_findings(self):
        r = self.t.report(OK)
        self.assertIsNone(r["root_cause"])
        self.assertEqual((r["violations"], r["skipped_barriers"], r["loss"]), ([], [], 0))

    def test_replay_each_candidate_and_independent_barriers(self):
        rows = {x["control"]: x for x in self.t.report(INC)["recommendations"]}
        self.assertTrue(rows["K1"]["prevented"] and rows["K1"]["blocks_at"].endswith("E2"))
        self.assertTrue(rows["K3"]["prevented"] and rows["K4"]["prevented"])
        self.assertTrue(rows["K2"]["prevented"] and rows["K2"]["blocks_at"].endswith("E6"))
        self.assertEqual(rows["K1"]["independent_barriers"], 4)
        self.assertEqual(rows["K1"]["loss_avoided"], 112500)

    def test_replay_cascades_and_does_not_touch_healthy_run(self):
        r = self.t.replay(INC, ["K1"])
        self.assertEqual(r["status"][f"{INC}-E1"], "executed")
        self.assertEqual(r["status"][f"{INC}-E2"], "blocked")
        self.assertEqual(r["status"][f"{INC}-E6"], "not_executed")
        ok = self.t.replay(OK, ["K1", "K2", "K3", "K4"])
        self.assertFalse(ok["prevented"])
        self.assertTrue(all(s == "executed" for s in ok["status"].values()))

    def test_ask_routes(self):
        a = self.t.ask("what if we disable the payment approval policy?")
        self.assertEqual((a["type"], a["node"], a["change"]), ("simulation", "pol:approval", "relax"))
        self.assertEqual(self.t.ask("لو وقفنا الـ Bank API")["node"], "sys:bank")
        self.assertEqual(self.t.ask("what happened in the failed payment")["type"], "incident")
        self.assertEqual(self.t.ask("who approves transfers above 100,000")["sources"][0]["id"], "DEC-017")

    def test_narrate_falls_back_without_key(self):
        n = self.t.narrate(self.t.report(INC))
        self.assertEqual(n["source"], "deterministic")
        self.assertIn("112,500", n["text"])


if __name__ == "__main__":
    unittest.main()
