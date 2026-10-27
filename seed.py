"""
seed.py - SYNTHETIC demo data banata hai. Koi bhi record asli AICTE data nahi hai.
Run: python seed.py   (database reset karke dobara banata hai)
"""
import json
import os
import random
from datetime import date, datetime, timedelta

from werkzeug.security import generate_password_hash

import config
import db
import overlap

DEMO_PASSWORD = "demo123"  # sirf demo ke liye

USERS = [
    ("admin", "Admin User", "admin", None),
    ("head.office", "Head Office Supervisor", "supervisor", None),
    ("a.sharma", "A. Sharma", "officer", "PGRC"),
    ("s.khan", "S. Khan", "officer", "PGRC"),
    ("r.verma", "R. Verma", "officer", "RB"),
    ("p.nair", "P. Nair", "officer", "RB"),
    ("m.iyer", "M. Iyer", "officer", "OTH"),
    ("regional.viewer", "Regional Office Viewer", "viewer", None),
]

REGION_PLACES = {
    "North": [("Delhi", "New Delhi"), ("Punjab", "Ludhiana"), ("Uttar Pradesh", "Lucknow")],
    "South": [("Tamil Nadu", "Chennai"), ("Karnataka", "Mysuru"), ("Telangana", "Hyderabad")],
    "East": [("West Bengal", "Kolkata"), ("Odisha", "Bhubaneswar"), ("Bihar", "Patna")],
    "West": [("Maharashtra", "Pune"), ("Gujarat", "Surat"), ("Rajasthan", "Jaipur")],
    "Central": [("Madhya Pradesh", "Indore"), ("Chhattisgarh", "Raipur"), ("Madhya Pradesh", "Bhopal")],
}

# Har (category, subcategory) ke liye alag-alag shabdon mein likhe descriptions.
TEMPLATES = {
    ("Faculty", "Faculty shortage"): [
        "Students report the institution has fewer faculty members than required, many posts are vacant.",
        "Teachers not available as per AICTE norms; staff shortage affecting classes.",
        "Insufficient number of professors for the approved intake.",
    ],
    ("Faculty", "Faculty qualification"): [
        "Faculty appointed do not hold the prescribed qualifications.",
        "Lecturers without required degrees are teaching core subjects.",
    ],
    ("Faculty", "Salary non-payment"): [
        "Faculty salaries have not been paid for several months.",
        "Teaching staff alleging non-payment of salary and delayed payments.",
    ],
    ("Fee and finance", "Fee refund"): [
        "Fee not refunded after the student withdrew admission.",
        "Refund of tuition deposit pending despite withdrawal before cut-off date.",
    ],
    ("Fee and finance", "Excess fee collection"): [
        "Institution charged fees higher than the approved fee structure.",
        "Students were asked to pay additional development charges beyond approved fees.",
    ],
    ("Infrastructure", "Laboratory facilities"): [
        "Labs have insufficient equipment compared with norms.",
        "Laboratory facilities inadequate; required equipment is missing.",
    ],
    ("Infrastructure", "Building and classrooms"): [
        "Classrooms are overcrowded and the building lacks required facilities.",
        "Campus building does not meet the prescribed built-up area.",
    ],
    ("Approval norms", "Intake beyond approval"): [
        "Institution is admitting more students than the approved intake.",
        "Admissions made above sanctioned seats in a programme.",
    ],
    ("Approval norms", "Operating without approval"): [
        "Programme being run without valid approval for this academic year.",
        "Course advertised and conducted without AICTE approval.",
    ],
    ("Student grievance", "Examination and results"): [
        "Examination results delayed and revaluation requests ignored.",
        "Student complains about wrong marks and no response to re-evaluation request.",
    ],
    ("Student grievance", "Harassment or discipline"): [
        "Student reports harassment and unfair disciplinary action.",
        "Allegation of ragging and no action by the institution.",
    ],
    ("Admission", "Irregular admission"): [
        "Admissions done without following the prescribed counselling process.",
        "Irregularities in admission procedure and merit list.",
    ],
    ("Other", "General grievance"): [
        "General grievance regarding lack of response from the institution.",
        "Complaint about poor communication and services from the institution.",
    ],
}

CHANNELS = ["Direct letter", "Email", "Online form", "Government portal referral (synthetic)"]
OFFICER_BY_BUREAU = {"PGRC": ["A. Sharma", "S. Khan"], "RB": ["R. Verma", "P. Nair"], "OTH": ["M. Iyer"]}
SOURCE_SYSTEM = {"PGRC": "PGRC register (synthetic)", "RB": "RB register (synthetic)", "OTH": "Other cell register (synthetic)"}


def _ts(d, hour=10):
    return "%s %02d:00:00" % (d.isoformat(), hour)


def _history(conn, cid, d, action, from_status=None, to_status=None, from_bureau=None, to_bureau=None,
             actor="System", actor_bureau=None, remarks=None):
    conn.execute(
        "INSERT INTO complaint_history (complaint_id, ts, action, from_status, to_status, from_bureau, "
        "to_bureau, actor, actor_bureau, remarks) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (cid, _ts(d), action, from_status, to_status, from_bureau, to_bureau, actor, actor_bureau, remarks),
    )


def _insert_complaint(conn, c, history):
    cols = ["complaint_id", "source_ref", "source_system", "source_channel", "institution_id", "category",
            "subcategory", "description", "date_received", "bureau", "assigned_officer", "status",
            "last_action", "last_action_date", "next_action", "expected_disposal_date", "sla_days",
            "applicable_procedure", "external_ref", "complainant_name", "complainant_contact"]
    conn.execute(
        "INSERT INTO complaints (%s) VALUES (%s)" % (",".join(cols), ",".join("?" * len(cols))),
        [c.get(k) for k in cols],
    )
    for h in history:
        _history(conn, c["complaint_id"], **h)


def _make(cid, inst, cat, sub, desc, received, bureau, status, officer, last_action, last_action_date,
          next_action, today, ext_ref=None, channel="Online form", seq=0):
    sla = config.DEFAULT_SLA_DAYS[cat]
    year = received.year
    return {
        "complaint_id": cid,
        "source_ref": "%s/%d/%04d" % (bureau, year, seq or int(cid[1:])),
        "source_system": SOURCE_SYSTEM[bureau],
        "source_channel": channel,
        "institution_id": inst,
        "category": cat,
        "subcategory": sub,
        "description": desc,
        "date_received": received.isoformat(),
        "bureau": bureau,
        "assigned_officer": officer,
        "status": status,
        "last_action": last_action,
        "last_action_date": last_action_date.isoformat(),
        "next_action": next_action,
        "expected_disposal_date": (received + timedelta(days=sla)).isoformat(),
        "sla_days": sla,
        "applicable_procedure": "Demo placeholder - procedure to be confirmed by AICTE",
        "external_ref": ext_ref,
        "complainant_name": "Synthetic Complainant %s" % cid,
        "complainant_contact": "complainant-%s@example.invalid" % cid.lower(),
    }


def _scenario_data(conn, today):
    """Haath se banaye gaye demo scenarios (problem statement ke examples jaise)."""
    d = lambda n: today - timedelta(days=n)  # noqa: E731

    def basic_history(c, extra=None):
        h = [
            dict(d=date.fromisoformat(c["date_received"]), action="Complaint received", to_status="Pending",
                 to_bureau=c["bureau"], actor="Registry", actor_bureau=c["bureau"],
                 remarks="Registered in " + c["source_system"]),
            dict(d=date.fromisoformat(c["date_received"]) + timedelta(days=1),
                 action="Assigned to %s" % c["bureau"], from_status="Pending", to_status="Pending",
                 to_bureau=c["bureau"], actor="Registry", actor_bureau=c["bureau"],
                 remarks="Assigned to %s" % c["assigned_officer"]),
        ]
        h += extra or []
        return h

    items = []

    # --- College A: problem statement ka example (C101, C205 overlap; C310 alag issue) ---
    c = _make("C101", "SYN-00001", "Faculty", "Faculty shortage",
              "Students report the institution has fewer faculty members than required, many posts are vacant.",
              d(40), "PGRC", "Under Process", "A. Sharma", "Additional information requested from institution",
              d(9), "Review institution's reply", today, seq=101)
    items.append((c, basic_history(c, [
        dict(d=d(30), action="Officer reviewed the complaint", from_status="Pending", to_status="Under Process",
             actor="A. Sharma", actor_bureau="PGRC", remarks="Prima facie needs institution's reply"),
        dict(d=d(9), action="Additional information requested", from_status="Under Process",
             to_status="Under Process", actor="A. Sharma", actor_bureau="PGRC",
             remarks="Letter sent to institution"),
    ])))
    c = _make("C205", "SYN-00001", "Faculty", "Faculty shortage",
              "Teachers not available as per AICTE norms; staff shortage reported by faculty association.",
              d(31), "RB", "Under Process", "R. Verma", "Verification of faculty list initiated",
              d(6), "Compare faculty list with approved norms", today, seq=205)
    items.append((c, basic_history(c, [
        dict(d=d(6), action="Verification initiated", from_status="Pending", to_status="Under Process",
             actor="R. Verma", actor_bureau="RB", remarks="Faculty list requested"),
    ])))
    c = _make("C310", "SYN-00001", "Fee and finance", "Fee refund",
              "Fee not refunded after student withdrew admission.",
              d(12), "PGRC", "Pending", "S. Khan", "Complaint registered", d(11),
              "Seek institution's response", today, seq=310)
    items.append((c, basic_history(c)))
    c = _make("C050", "SYN-00001", "Student grievance", "Examination and results",
              "Examination results delayed and revaluation requests ignored.",
              d(150), "PGRC", "Disposed", "A. Sharma", "Disposed after institution released results",
              d(110), "None", today, seq=50)
    items.append((c, basic_history(c, [
        dict(d=d(110), action="Disposed", from_status="Pending", to_status="Disposed", actor="A. Sharma",
             actor_bureau="PGRC", remarks="Institution released revised results; student satisfied"),
    ])))

    # --- College B: overdue case ---
    c = _make("C412", "SYN-00002", "Approval norms", "Intake beyond approval",
              "Institution is admitting more students than the approved intake.",
              d(120), "RB", "Under Process", "P. Nair", "Show-cause stage under review", d(20),
              "Decide on next step", today, seq=412)
    items.append((c, basic_history(c, [
        dict(d=d(20), action="Officer reviewed the complaint", from_status="Pending", to_status="Under Process",
             actor="P. Nair", actor_bureau="RB", remarks="File put up to senior officer"),
    ])))

    # --- College C: alag shabd, same issue (different wording demo) ---
    c = _make("C520", "SYN-00003", "Infrastructure", "Laboratory facilities",
              "Labs have insufficient equipment compared with norms.",
              d(25), "PGRC", "Under Process", "S. Khan", "Inspection request noted", d(5),
              "Check inspection schedule", today, seq=520)
    items.append((c, basic_history(c, [
        dict(d=d(5), action="Officer reviewed the complaint", from_status="Pending", to_status="Under Process",
             actor="S. Khan", actor_bureau="PGRC", remarks="Inspection request noted"),
    ])))
    c = _make("C521", "SYN-00003", "Infrastructure", "Laboratory facilities",
              "Laboratory facilities inadequate; required equipment is missing.",
              d(18), "OTH", "Pending", "M. Iyer", "Complaint registered", d(17),
              "Assign for examination", today, seq=521)
    items.append((c, basic_history(c)))

    # --- College D: same external reference, different wording ---
    c = _make("C600", "SYN-00004", "Admission", "Irregular admission",
              "Admissions done without following the prescribed counselling process.",
              d(22), "PGRC", "Under Process", "A. Sharma", "Reply sought from institution", d(8),
              "Await reply", today, ext_ref="DEMO-REF-0001", channel="Government portal referral (synthetic)",
              seq=600)
    items.append((c, basic_history(c, [
        dict(d=d(8), action="Reply sought", from_status="Pending", to_status="Under Process",
             actor="A. Sharma", actor_bureau="PGRC", remarks="Reply sought from institution"),
    ])))
    c = _make("C601", "SYN-00004", "Admission", "Irregular admission",
              "Irregularities in admission procedure and merit list.",
              d(20), "RB", "Pending", "R. Verma", "Complaint registered", d(19),
              "Assign for examination", today, ext_ref="DEMO-REF-0001", seq=601)
    items.append((c, basic_history(c)))

    # --- College E: same institution, alag issue (flag nahi hona chahiye) ---
    c = _make("C700", "SYN-00005", "Faculty", "Salary non-payment",
              "Faculty salaries have not been paid for several months.",
              d(60), "PGRC", "Under Process", "S. Khan", "Reply sought from institution", d(30),
              "Follow up", today, seq=700)
    items.append((c, basic_history(c, [
        dict(d=d(30), action="Reply sought", from_status="Pending", to_status="Under Process", actor="S. Khan",
             actor_bureau="PGRC", remarks="Reply sought"),
    ])))
    c = _make("C701", "SYN-00005", "Student grievance", "Harassment or discipline",
              "Allegation of ragging and no action by the institution.",
              d(15), "RB", "Pending", "P. Nair", "Complaint registered", d(14),
              "Seek anti-ragging committee report", today, seq=701)
    items.append((c, basic_history(c)))

    for c, h in items:
        _insert_complaint(conn, c, h)


def _random_data(conn, today, rng, n=170):
    inst_ids = [r[0] for r in conn.execute(
        "SELECT permanent_id FROM institutions WHERE permanent_id > 'SYN-00005' ORDER BY permanent_id")]
    cat_pairs = [(cat, sub) for cat, subs in config.CATEGORIES.items() for sub in subs]
    bureaus = ["PGRC"] * 50 + ["RB"] * 35 + ["OTH"] * 15
    statuses = ["Pending"] * 22 + ["Under Process"] * 30 + ["Transferred"] * 6 + ["Escalated"] * 6 + ["Disposed"] * 36

    for i in range(n):
        cid = "C%d" % (1000 + i)
        inst = rng.choice(inst_ids)
        cat, sub = rng.choice(cat_pairs)
        desc = rng.choice(TEMPLATES[(cat, sub)])
        bureau = rng.choice(bureaus)
        status = rng.choice(statuses)
        # open cases are mostly recent; disposed ones can be older (keeps the demo realistic)
        days_ago = rng.randint(20, 220) if status == "Disposed" else rng.randint(3, 85)
        received = today - timedelta(days=days_ago)
        sla = config.DEFAULT_SLA_DAYS[cat]
        officer = rng.choice(OFFICER_BY_BUREAU[bureau])
        channel = rng.choice(CHANNELS)

        history = [dict(d=received, action="Complaint received", to_status="Pending", to_bureau=bureau,
                        actor="Registry", actor_bureau=bureau, remarks="Registered in " + SOURCE_SYSTEM[bureau])]
        first_action = min(received + timedelta(days=1), today)
        history.append(dict(d=first_action, action="Assigned to %s" % bureau, from_status="Pending",
                            to_status="Pending", to_bureau=bureau, actor="Registry", actor_bureau=bureau,
                            remarks="Assigned to %s" % officer))
        last_action = "Complaint registered"
        last_date = first_action
        next_action = "Assign for examination"

        if status != "Pending":
            span = max((today - first_action).days, 0)
            offset = rng.randint(0, span)
            last_date = first_action + timedelta(days=offset)
            if status == "Under Process":
                last_action, next_action = "Officer reviewed the complaint", "Await institution's reply"
                history.append(dict(d=last_date, action=last_action, from_status="Pending",
                                    to_status="Under Process", actor=officer, actor_bureau=bureau,
                                    remarks="Examined; reply sought"))
            elif status == "Transferred":
                other = rng.choice([b for b in ("PGRC", "RB", "OTH") if b != bureau])
                last_action, next_action = "Transferred from %s to %s" % (other, bureau), "Receiving cell to take up"
                history.insert(1, dict(d=first_action, action="Assigned to %s" % other, from_status="Pending",
                                       to_status="Pending", to_bureau=other, actor="Registry",
                                       actor_bureau=other, remarks="Initially assigned to %s" % other))
                history.pop(2)
                history.append(dict(d=last_date, action="Transferred", from_status="Pending",
                                    to_status="Transferred", from_bureau=other, to_bureau=bureau,
                                    actor="Supervisor", actor_bureau=other,
                                    remarks="Falls under the work of %s (demo reason)" % bureau))
            elif status == "Escalated":
                last_action, next_action = "Escalated to competent authority", "Decision by competent authority"
                history.append(dict(d=last_date, action="Escalated", from_status="Under Process",
                                    to_status="Escalated", actor=officer, actor_bureau=bureau,
                                    remarks="Referred for decision"))
            elif status == "Disposed":
                last_action, next_action = "Disposed", "None"
                history.append(dict(d=last_date, action="Disposed", from_status="Under Process",
                                    to_status="Disposed", actor=officer, actor_bureau=bureau,
                                    remarks="Closed after action taken (demo)"))

        c = _make("C%d" % (1000 + i), inst, cat, sub, desc, received, bureau, status, officer, last_action,
                  last_date, next_action, today, channel=channel, seq=1000 + i)
        _insert_complaint(conn, c, history)


def seed(conn, today=None, random_complaints=170):
    today = today or date.today()
    rng = random.Random(42)

    # Settings, SLA, users
    for k, v in config.DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (k, v))
    for cat, days in config.DEFAULT_SLA_DAYS.items():
        conn.execute("INSERT OR REPLACE INTO sla_rules (category, days, note) VALUES (?,?,?)",
                     (cat, days, config.SLA_NOTE))
    pw_hash = generate_password_hash(DEMO_PASSWORD)
    for username, full_name, role, bureau in USERS:
        conn.execute("INSERT OR IGNORE INTO users (username, full_name, password_hash, role, bureau) "
                     "VALUES (?,?,?,?,?)", (username, full_name, pw_hash, role, bureau))

    # Institutions (40 synthetic)
    named = ["College A (synthetic)", "College B (synthetic)", "College C (synthetic)",
             "College D (synthetic)", "College E (synthetic)"]
    regions = ["Central", "East", "South", "West", "North"]
    types = ["Engineering College", "Management Institute", "Pharmacy College", "Polytechnic"]
    for i in range(1, 41):
        region = regions[i - 1] if i <= 5 else rng.choice(config.REGIONS)
        state, city = (REGION_PLACES[region][0] if i == 1 else rng.choice(REGION_PLACES[region]))
        itype = types[(i - 1) % 4]
        name = named[i - 1] if i <= 5 else "Demo %s %02d" % (itype, i)
        conn.execute(
            "INSERT OR REPLACE INTO institutions (permanent_id, name, address, city, state, region, "
            "institution_type) VALUES (?,?,?,?,?,?,?)",
            ("SYN-%05d" % i, name, "Synthetic address %d, %s" % (i, city), city, state, region, itype),
        )

    _scenario_data(conn, today)
    _random_data(conn, today, rng, random_complaints)
    conn.execute("INSERT INTO audit_log (ts, username, action, entity, entity_id, details) VALUES (?,?,?,?,?,?)",
                 (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "system", "seed", "database", "-",
                  json.dumps({"note": "Synthetic demo data loaded"})))
    conn.commit()
    return overlap.detect_overlaps(conn)


if __name__ == "__main__":
    if os.path.exists(config.DB_PATH):
        os.remove(config.DB_PATH)
    connection = db.init_db(config.DB_PATH)
    print("Seeded:", seed(connection))
    n = connection.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
    print("Complaints:", n)
