"""
overlap.py - Cross-Bureau overlap detection (RULE-BASED, explainable).

Yeh AI/ML model NAHI hai. Yeh transparent scoring rules hain:
  - Same AICTE Permanent ID ............ +30  (gate: iske bina koi flag nahi)
  - Same category ...................... +20   (related category: +10)
  - Same subcategory ................... +15
  - Description similarity (0..1) ...... +0..25  (cosine similarity)
  - Dates close (<=30d / <=90d) ........ +10 / +5
  - Same external reference ............ +15
Score >= threshold (default 65) => "Potential overlap" flag.

Safety rules:
  * Sirf flag karta hai. Kabhi merge / close / dismiss nahi karta.
  * Har flag ke saath reasons saath dikhte hain.
  * Reviewed (Confirmed / Dismissed) alerts dobara detection se overwrite nahi hote.
"""
import json
import math
import re
from collections import Counter
from datetime import date, datetime

import config

STOPWORDS = set("""
a an the of in at on to for and or is are was were be been has have had with by from as it its this that
these those not no than their there which who into over under about after before during since while also
may might can could should would will shall please kindly sir madam complaint regarding respect request
institute institution college reported received against many much some any very more most
""".split())

# Alag-alag shabd, same matlab. (Chhota rule-based "synonym map".)
SYNONYMS = {
    "teacher": "faculty", "professor": "faculty", "lecturer": "faculty", "faculties": "faculty",
    "vacant": "shortage", "vacancy": "shortage", "insufficient": "shortage", "inadequate": "shortage",
    "lack": "shortage", "lacking": "shortage", "fewer": "shortage", "deficiency": "shortage",
    "short": "shortage", "unavailable": "shortage", "missing": "shortage",
    "reimburse": "refund", "reimbursement": "refund", "return": "refund",
    "charge": "fee", "charged": "fee", "tuition": "fee",
    "laboratory": "lab", "laboratorie": "lab",
    "facility": "infrastructure", "classroom": "infrastructure", "building": "infrastructure",
    "equipment": "infrastructure",
    "admitted": "admission", "admit": "admission", "enrol": "admission", "enrolment": "admission",
}


def _stem(word):
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokenize(text):
    words = re.findall(r"[a-z]+", (text or "").lower())
    out = []
    for w in words:
        w = _stem(w)
        if w in STOPWORDS or len(w) < 3:
            continue
        out.append(SYNONYMS.get(w, w))
    return out


def cosine_similarity(text_a, text_b):
    ca, cb = Counter(tokenize(text_a)), Counter(tokenize(text_b))
    if not ca or not cb:
        return 0.0
    dot = sum(ca[t] * cb[t] for t in ca if t in cb)
    na = math.sqrt(sum(v * v for v in ca.values()))
    nb = math.sqrt(sum(v * v for v in cb.values()))
    return dot / (na * nb) if na and nb else 0.0


def _related(cat_a, cat_b):
    return any({cat_a, cat_b} == pair for pair in config.RELATED_CATEGORIES)


def _days_apart(d1, d2):
    try:
        return abs((date.fromisoformat(d1) - date.fromisoformat(d2)).days)
    except (TypeError, ValueError):
        return None


def compare(a, b, threshold=65, include_same_bureau=False):
    """Do complaints (dict-like) ko compare karo. Returns dict: score, reasons, flagged."""
    reasons = []
    score = 0

    if not a["institution_id"] or a["institution_id"] != b["institution_id"]:
        return {"score": 0, "reasons": ["Different institutions"], "flagged": False, "text_similarity": 0.0}
    score += 30
    reasons.append("Same AICTE Permanent ID (+30)")

    same_cat = a["category"] == b["category"]
    related = (not same_cat) and _related(a["category"], b["category"])
    if same_cat:
        score += 20
        reasons.append("Same category: %s (+20)" % a["category"])
    elif related:
        score += 10
        reasons.append("Related categories: %s / %s (+10)" % (a["category"], b["category"]))

    same_sub = bool(a["subcategory"]) and a["subcategory"] == b["subcategory"]
    if same_sub:
        score += 15
        reasons.append("Same subcategory: %s (+15)" % a["subcategory"])

    sim = cosine_similarity(a["description"], b["description"])
    text_points = round(sim * 25)
    if text_points > 0:
        score += text_points
        reasons.append("Description similarity %d%% (+%d)" % (round(sim * 100), text_points))

    gap = _days_apart(a["date_received"], b["date_received"])
    if gap is not None:
        if gap <= 30:
            score += 10
            reasons.append("Received %d days apart (+10)" % gap)
        elif gap <= 90:
            score += 5
            reasons.append("Received %d days apart (+5)" % gap)

    same_ref = bool(a["external_ref"]) and a["external_ref"] == b["external_ref"]
    if same_ref:
        score += 15
        reasons.append("Same external reference %s (+15)" % a["external_ref"])

    score = min(score, 100)

    different_bureaus = a["bureau"] != b["bureau"]
    both_closed = a["status"] == "Disposed" and b["status"] == "Disposed"
    has_issue_evidence = same_cat or related or sim >= 0.30 or same_ref
    flagged = (
        score >= threshold
        and has_issue_evidence
        and not both_closed
        and (different_bureaus or include_same_bureau)
    )
    return {"score": score, "reasons": reasons, "flagged": flagged, "text_similarity": round(sim, 3)}


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def detect_overlaps(conn, threshold=65, include_same_bureau=False):
    """
    Saare complaints ko institution ke hisaab se group karke pairs compare karta hai.
    alerts table mein sirf INSERT / Potential-alert ka score UPDATE karta hai.
    Complaints table ko kabhi nahi chhuta.
    """
    rows = conn.execute(
        "SELECT complaint_id, institution_id, category, subcategory, description, date_received, "
        "bureau, status, external_ref FROM complaints ORDER BY institution_id, complaint_id"
    ).fetchall()
    by_inst = {}
    for r in rows:
        by_inst.setdefault(r["institution_id"], []).append(r)

    created = updated = 0
    for inst_id, items in by_inst.items():
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                result = compare(a, b, threshold, include_same_bureau)
                if not result["flagged"]:
                    continue
                first, second = sorted([a["complaint_id"], b["complaint_id"]])
                existing = conn.execute(
                    "SELECT id, status FROM overlap_alerts WHERE complaint_a=? AND complaint_b=?",
                    (first, second),
                ).fetchone()
                reasons_json = json.dumps(result["reasons"])
                if existing is None:
                    conn.execute(
                        "INSERT INTO overlap_alerts (complaint_a, complaint_b, institution_id, score, reasons, "
                        "status, detected_at) VALUES (?,?,?,?,?, 'Potential', ?)",
                        (first, second, inst_id, result["score"], reasons_json, _now()),
                    )
                    created += 1
                elif existing["status"] == "Potential":
                    conn.execute(
                        "UPDATE overlap_alerts SET score=?, reasons=? WHERE id=?",
                        (result["score"], reasons_json, existing["id"]),
                    )
                    updated += 1
                # Confirmed / Dismissed alerts ko haath nahi lagate.
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM overlap_alerts WHERE status='Potential'").fetchone()[0]
    return {"created": created, "updated": updated, "potential_total": total}
