"""Unit tests for the overlap rules (no database, no server)."""
import unittest

import overlap


def make(cid, inst="SYN-00001", cat="Faculty", sub="Faculty shortage", desc="", bureau="PGRC",
         status="Under Process", received="2026-09-01", ref=None):
    return {"complaint_id": cid, "institution_id": inst, "category": cat, "subcategory": sub,
            "description": desc, "bureau": bureau, "status": status, "date_received": received,
            "external_ref": ref}


class OverlapRules(unittest.TestCase):
    def test_problem_statement_example_is_flagged(self):
        c101 = make("C101", desc="Fewer faculty members than required, many posts are vacant", bureau="PGRC")
        c205 = make("C205", desc="Teachers not available as per norms; staff shortage", bureau="RB",
                    received="2026-09-10")
        r = overlap.compare(c101, c205)
        self.assertTrue(r["flagged"], r)
        self.assertTrue(any("Same AICTE Permanent ID" in x for x in r["reasons"]))

    def test_same_institution_different_issue_is_not_flagged(self):
        c101 = make("C101", desc="Fewer faculty members than required")
        c310 = make("C310", cat="Fee and finance", sub="Fee refund", desc="Fee not refunded after withdrawal",
                    bureau="PGRC", status="Pending")
        self.assertFalse(overlap.compare(c101, c310)["flagged"])
        c310_rb = dict(c310, bureau="RB")
        self.assertFalse(overlap.compare(c101, c310_rb)["flagged"])

    def test_different_wording_same_issue_is_flagged(self):
        a = make("C520", cat="Infrastructure", sub="Laboratory facilities",
                 desc="Labs have insufficient equipment compared with norms.", bureau="PGRC")
        b = make("C521", cat="Infrastructure", sub="Laboratory facilities",
                 desc="Laboratory facilities inadequate; required equipment is missing.", bureau="OTH")
        self.assertTrue(overlap.compare(a, b)["flagged"])

    def test_same_external_reference_is_flagged(self):
        a = make("C600", cat="Admission", sub="Irregular admission", desc="Counselling process not followed",
                 ref="DEMO-REF-0001")
        b = make("C601", cat="Admission", sub="Irregular admission", desc="Merit list irregular",
                 bureau="RB", ref="DEMO-REF-0001")
        r = overlap.compare(a, b)
        self.assertTrue(r["flagged"])
        self.assertTrue(any("external reference" in x for x in r["reasons"]))

    def test_different_institutions_never_flagged(self):
        a = make("C1", inst="SYN-00001", desc="faculty shortage")
        b = make("C2", inst="SYN-00002", desc="faculty shortage", bureau="RB")
        self.assertFalse(overlap.compare(a, b)["flagged"])

    def test_same_bureau_only_when_enabled(self):
        a = make("C1", desc="faculty shortage vacant posts")
        b = make("C2", desc="faculty shortage vacant posts")
        self.assertFalse(overlap.compare(a, b)["flagged"])
        self.assertTrue(overlap.compare(a, b, include_same_bureau=True)["flagged"])

    def test_both_disposed_not_flagged(self):
        a = make("C1", status="Disposed", desc="faculty shortage vacant posts")
        b = make("C2", status="Disposed", desc="faculty shortage vacant posts", bureau="RB")
        self.assertFalse(overlap.compare(a, b)["flagged"])

    def test_tokenizer_maps_synonyms(self):
        self.assertIn("faculty", overlap.tokenize("Teachers and professors"))
        self.assertIn("shortage", overlap.tokenize("posts are vacant"))


if __name__ == "__main__":
    unittest.main()
