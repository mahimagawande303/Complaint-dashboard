"""API tests: roles, audit trail, no-auto-decision rules. Uses a throw-away database."""
import os
import tempfile
import unittest

import app as appmod


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.app = appmod.create_app(os.path.join(cls.tmp, "test.db"))

    def setUp(self):
        self.client = self.app.test_client()
        self.tokens = {}

    def h(self, username):
        if username not in self.tokens:
            r = self.client.post("/api/login", json={"username": username, "password": "demo123"})
            self.assertEqual(r.status_code, 200)
            self.tokens[username] = {"Authorization": "Bearer " + r.get_json()["token"]}
        return self.tokens[username]

    def get(self, url, user="head.office"):
        return self.client.get(url, headers=self.h(user))

    def post(self, url, body, user="head.office"):
        return self.client.post(url, json=body, headers=self.h(user))

    def alert_id(self, a, b):
        items = self.get("/api/overlaps").get_json()["items"]
        for o in items:
            if {o["complaint_a"], o["complaint_b"]} == {a, b}:
                return o["id"]
        return None

    # ---- auth ----
    def test_login_and_auth_required(self):
        self.assertEqual(self.client.get("/api/dashboard").status_code, 401)
        bad = self.client.post("/api/login", json={"username": "admin", "password": "wrong"})
        self.assertEqual(bad.status_code, 401)

    # ---- overlap behaviour from the problem statement ----
    def test_c101_c205_flagged_and_c310_not(self):
        self.assertIsNotNone(self.alert_id("C101", "C205"))
        items = self.get("/api/overlaps").get_json()["items"]
        self.assertFalse(any("C310" in (o["complaint_a"], o["complaint_b"]) for o in items))
        detail = self.get("/api/complaints/C310").get_json()
        self.assertEqual(detail["overlaps"], [])

    def test_detection_never_changes_complaints(self):
        before = {c["complaint_id"]: (c["status"], c["bureau"]) for c in self.get("/api/complaints?limit=500").get_json()["items"]}
        self.assertEqual(self.post("/api/overlaps/detect", {}).status_code, 200)
        after = {c["complaint_id"]: (c["status"], c["bureau"]) for c in self.get("/api/complaints?limit=500").get_json()["items"]}
        self.assertEqual(before, after)

    # ---- permissions ----
    def test_viewer_cannot_act(self):
        r = self.post("/api/complaints/C101/action", {"action": "remark", "remarks": "x"}, "regional.viewer")
        self.assertEqual(r.status_code, 403)

    def test_officer_of_other_bureau_cannot_act(self):
        r = self.post("/api/complaints/C101/action", {"action": "remark", "remarks": "x"}, "r.verma")  # RB officer, PGRC case
        self.assertEqual(r.status_code, 403)

    def test_owner_officer_can_add_remark(self):
        r = self.post("/api/complaints/C310/action", {"action": "remark", "remarks": "Reminder sent"}, "s.khan")
        self.assertEqual(r.status_code, 200)
        hist = self.get("/api/complaints/C310").get_json()["history"]
        self.assertEqual(hist[-1]["remarks"], "Reminder sent")
        self.assertEqual(hist[-1]["actor"], "S. Khan")

    def test_contact_details_masked_for_viewer(self):
        viewer = self.get("/api/complaints/C101", "regional.viewer").get_json()["complaint"]
        self.assertEqual(viewer["complainant_contact"], "Restricted")
        sup = self.get("/api/complaints/C101").get_json()["complaint"]
        self.assertIn("example.invalid", sup["complainant_contact"])
        listing = self.get("/api/complaints?limit=5").get_json()["items"][0]
        self.assertNotIn("complainant_contact", listing)

    # ---- records and audit ----
    def test_dispose_requires_remarks_and_is_recorded(self):
        r = self.post("/api/complaints/C600/action", {"action": "update_status", "to_status": "Disposed"}, "a.sharma")
        self.assertEqual(r.status_code, 400)
        r = self.post("/api/complaints/C600/action",
                      {"action": "update_status", "to_status": "Disposed", "remarks": "Resolved after reply"}, "a.sharma")
        self.assertEqual(r.status_code, 200)
        d = self.get("/api/complaints/C600").get_json()
        self.assertEqual(d["complaint"]["status"], "Disposed")
        self.assertEqual(d["history"][-1]["from_status"], "Under Process")
        # officer cannot reopen a disposed case, supervisor can
        r = self.post("/api/complaints/C600/action", {"action": "update_status", "to_status": "Under Process"}, "a.sharma")
        self.assertEqual(r.status_code, 403)

    def test_transfer_keeps_history(self):
        before = len(self.get("/api/complaints/C701").get_json()["history"])
        r = self.post("/api/complaints/C701/action", {"action": "transfer", "to_bureau": "PGRC"}, "p.nair")
        self.assertEqual(r.status_code, 400)  # reason missing
        r = self.post("/api/complaints/C701/action",
                      {"action": "transfer", "to_bureau": "PGRC", "remarks": "Student matter"}, "p.nair")
        self.assertEqual(r.status_code, 200)
        d = self.get("/api/complaints/C701").get_json()
        self.assertEqual(d["complaint"]["bureau"], "PGRC")
        self.assertEqual(d["complaint"]["status"], "Transferred")
        self.assertEqual(len(d["history"]), before + 1)
        last = d["history"][-1]
        self.assertEqual((last["from_bureau"], last["to_bureau"]), ("RB", "PGRC"))
        self.assertEqual(d["history"][0]["action"], "Complaint received")

    # ---- review workflow ----
    def test_dismiss_requires_remarks_and_survives_rerun(self):
        aid = self.alert_id("C520", "C521")
        self.assertIsNotNone(aid)
        self.assertEqual(self.post("/api/overlaps/%d/review" % aid, {"decision": "dismiss"}).status_code, 400)
        r = self.post("/api/overlaps/%d/review" % aid, {"decision": "dismiss", "remarks": "Different labs"})
        self.assertEqual(r.status_code, 200)
        self.post("/api/overlaps/detect", {})
        detail = self.get("/api/overlaps/%d" % aid).get_json()
        self.assertEqual(detail["alert"]["status"], "Dismissed")
        self.assertEqual(self.get("/api/complaints/C520").get_json()["complaint"]["status"], "Under Process")
        self.assertEqual(self.post("/api/overlaps/%d/coordination" % aid, {"remark": "hi"}).status_code, 400)

    def test_confirm_links_without_merging(self):
        aid = self.alert_id("C101", "C205")
        r = self.post("/api/overlaps/%d/review" % aid, {"decision": "confirm", "remarks": "Same allegation"})
        self.assertEqual(r.status_code, 200)
        d = self.get("/api/overlaps/%d" % aid).get_json()
        self.assertEqual(d["alert"]["status"], "Confirmed")
        self.assertEqual(len(d["links"]), 1)
        self.assertEqual(d["a"]["complaint_id"], "C101")
        self.assertEqual(d["b"]["complaint_id"], "C205")
        self.assertNotEqual(d["a"]["bureau"], d["b"]["bureau"])

    def test_uninvolved_officer_cannot_review(self):
        aid = self.alert_id("C101", "C205")  # PGRC + RB
        r = self.post("/api/overlaps/%d/review" % aid, {"decision": "dismiss", "remarks": "x"}, "m.iyer")
        self.assertEqual(r.status_code, 403)

    def test_coordination_decision_tracked(self):
        aid = self.alert_id("C600", "C601")
        r = self.post("/api/overlaps/%d/coordination" % aid, {"remark": "Discussed with RB"}, "a.sharma")
        self.assertEqual(r.get_json()["coordination_status"], "In discussion")
        r = self.post("/api/overlaps/%d/coordination" % aid,
                      {"remark": "RB will lead", "decision": "Lead Bureau/Cell assigned"}, "r.verma")
        self.assertEqual(r.get_json()["coordination_status"], "Decision recorded")
        hist = self.get("/api/complaints/C601").get_json()["history"]
        self.assertTrue(any("Coordination remark" in h["action"] for h in hist))

    # ---- dashboard and exports ----
    def test_dashboard_numbers_are_consistent(self):
        cards = self.get("/api/dashboard").get_json()["cards"]
        status_sum = sum(cards[k] for k in ("pending", "under_process", "disposed", "transferred", "escalated"))
        self.assertEqual(status_sum, cards["total"])
        listing = self.get("/api/complaints?overdue=1&limit=500").get_json()
        self.assertEqual(listing["count"], cards["overdue"])

    def test_csv_export_restricted_and_audited(self):
        self.assertEqual(self.get("/api/reports/bureau?format=csv", "a.sharma").status_code, 403)
        r = self.get("/api/reports/bureau?format=csv")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.mimetype.startswith("text/csv"))
        audit = self.get("/api/audit", "admin").get_json()["items"]
        self.assertTrue(any(a["action"] == "export_report" for a in audit))

    def test_settings_admin_only(self):
        self.assertEqual(self.client.put("/api/settings", json={"settings": {"stale_days": "20"}},
                                         headers=self.h("head.office")).status_code, 403)
        r = self.client.put("/api/settings", json={"settings": {"stale_days": "20"}}, headers=self.h("admin"))
        self.assertEqual(r.status_code, 200)
        bad = self.client.put("/api/settings", json={"settings": {"stale_days": "abc"}}, headers=self.h("admin"))
        self.assertEqual(bad.status_code, 400)


if __name__ == "__main__":
    unittest.main()
