"""
config.py - saari "settings" ek jagah.

IMPORTANT: Yahan likhe deadlines (SLA days), statuses aur bureaus DEMO placeholders hain.
AICTE ke official timelines / workflow confirm hone ke baad inhe badalna hai.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "complaints.db")

DATA_LABEL = "Synthetic demo data - not real AICTE records"

# (code, full name). "OTH" sirf placeholder hai "other Bureaus/Cells" ke liye.
BUREAUS = [
    ("RB", "Regulation Bureau"),
    ("PGRC", "Public Grievance Redressal Cell"),
    ("OTH", "Other Bureau/Cell (demo placeholder)"),
]

# Status ki definitions neeche DEFINITIONS mein hain (dashboard par bhi dikhti hain).
STATUSES = ["Pending", "Under Process", "Transferred", "Escalated", "Disposed"]

# category -> subcategories (demo list; official list AICTE se confirm karni hai)
CATEGORIES = {
    "Faculty": ["Faculty shortage", "Faculty qualification", "Salary non-payment"],
    "Fee and finance": ["Fee refund", "Excess fee collection"],
    "Infrastructure": ["Laboratory facilities", "Building and classrooms"],
    "Approval norms": ["Intake beyond approval", "Operating without approval"],
    "Student grievance": ["Examination and results", "Harassment or discipline"],
    "Admission": ["Irregular admission"],
    "Other": ["General grievance"],
}

# Kaun si categories "related" maani jaayengi (overlap scoring mein aadha point milta hai).
RELATED_CATEGORIES = [
    {"Faculty", "Approval norms"},
    {"Infrastructure", "Approval norms"},
    {"Fee and finance", "Admission"},
]

REGIONS = ["North", "South", "East", "West", "Central"]

# DEMO placeholder deadlines (days). Official timeline milne par sla_rules table update karein.
DEFAULT_SLA_DAYS = {
    "Faculty": 45,
    "Fee and finance": 30,
    "Infrastructure": 60,
    "Approval norms": 60,
    "Student grievance": 30,
    "Admission": 30,
    "Other": 30,
}
SLA_NOTE = "Demo placeholder - replace with the official prescribed timeline"

DEFAULT_SETTINGS = {
    "approaching_days": "7",      # deadline se itne din pehle "approaching" alert
    "stale_days": "14",           # itne din se koi action nahi => "no recent action"
    "overlap_threshold": "65",    # is score ya usse upar => potential overlap flag
    "include_same_bureau": "0",   # 1 = same bureau ke pairs bhi flag karo
    "session_hours": "8",
}

DEFINITIONS = {
    "Pending": "Received and registered, no substantive action started yet.",
    "Under Process": "An officer is working on the case.",
    "Transferred": "Moved to another Bureau/Cell and not yet taken up there.",
    "Escalated": "Referred to a higher authority for decision.",
    "Disposed": "Formally closed by an authorised official (with remarks).",
    "Overdue": "Not disposed AND today is after the expected disposal date.",
    "Potential overlap": "System-flagged pair needing human review. NOT a declared duplicate.",
    "Confirmed link": "An authorised official reviewed the pair and linked the cases. Records stay separate.",
    "Dismissed": "An authorised official reviewed the pair and judged it unrelated (reason recorded).",
}

ROLES = ["admin", "supervisor", "officer", "viewer"]
