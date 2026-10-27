"""
app.py - Flask backend (REST API + static frontend serve).
Run: python app.py   ->  http://127.0.0.1:5000

Rule: permissions SERVER par check hote hain (sirf buttons chhupane se kaam nahi chalta).
"""
import csv
import io
import json
import secrets
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Flask, Response, g, jsonify, request, send_from_directory
from werkzeug.security import check_password_hash

import config
import db as dbmod
import overlap
import seed as seedmod

COORD_DECISIONS = ["Joint review", "Lead Bureau/Cell assigned", "Proceed independently", "Awaiting information"]
BUREAU_CODES = [b[0] for b in config.BUREAUS]


def now_ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str():
    return date.today().isoformat()


def err(message, code=400):
    return jsonify({"error": message}), code


def create_app(db_path=None, seed_if_empty=True):
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config["DB_PATH"] = db_path or config.DB_PATH

    boot = dbmod.init_db(app.config["DB_PATH"])
    if seed_if_empty and boot.execute("SELECT COUNT(*) FROM institutions").fetchone()[0] == 0:
        seedmod.seed(boot)
    boot.close()

    # ---------------- helpers ----------------
    def conn():
        if "db" not in g:
            g.db = dbmod.connect(app.config["DB_PATH"])
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        c = g.pop("db", None)
        if c is not None:
            c.close()

    def settings():
        rows = conn().execute("SELECT key, value FROM settings").fetchall()
        s = dict(config.DEFAULT_SETTINGS)
        s.update({r["key"]: r["value"] for r in rows})
        return s

    def audit(action, entity="", entity_id="", details=None):
        user = g.get("user")
        conn().execute(
            "INSERT INTO audit_log (ts, username, action, entity, entity_id, details) VALUES (?,?,?,?,?,?)",
            (now_ts(), user["username"] if user else "anonymous", action, entity, str(entity_id),
             json.dumps(details) if details else None),
        )

    def auth_required(*roles):
        def deco(fn):
            @wraps(fn)
            def wrapper(*a, **kw):
                header = request.headers.get("Authorization", "")
                token = header[7:] if header.startswith("Bearer ") else ""
                row = conn().execute(
                    "SELECT u.*, s.expires_at FROM sessions s JOIN users u ON u.id = s.user_id "
                    "WHERE s.token=? AND u.active=1", (token,)).fetchone()
                if not row or row["expires_at"] < now_ts():
                    return err("Please log in.", 401)
                g.user = dict(row)
                if roles and g.user["role"] not in roles:
                    return err("Your role is not allowed to do this.", 403)
                return fn(*a, **kw)
            return wrapper
        return deco

    def can_act(user, c):
        if user["role"] in ("admin", "supervisor"):
            return True
        return user["role"] == "officer" and user["bureau"] == c["bureau"]

    def can_see_contact(user, c):
        return can_act(user, c)

    def can_review_alert(user, ca, cb):
        if user["role"] in ("admin", "supervisor"):
            return True
        return user["role"] == "officer" and user["bureau"] in (ca["bureau"], cb["bureau"])

    def decorate(row, user=None):
        """Complaint row -> dict with computed fields (overdue, days_left) and masked contact."""
        c = dict(row)
        today = date.today()
        c["days_left"] = None
        c["overdue"] = False
        if c["expected_disposal_date"] and c["status"] != "Disposed":
            left = (date.fromisoformat(c["expected_disposal_date"]) - today).days
            c["days_left"] = left
            c["overdue"] = left < 0
        if user is not None and not can_see_contact(user, c):
            c["complainant_name"] = "Restricted"
            c["complainant_contact"] = "Restricted"
        return c

    def add_history(cid, action, from_status=None, to_status=None, from_bureau=None, to_bureau=None,
                    remarks=None):
        u = g.user
        conn().execute(
            "INSERT INTO complaint_history (complaint_id, ts, action, from_status, to_status, from_bureau, "
            "to_bureau, actor, actor_bureau, remarks) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (cid, now_ts(), action, from_status, to_status, from_bureau, to_bureau,
             u["full_name"], u["bureau"] or u["role"], remarks))

    def get_complaint(cid):
        return conn().execute("SELECT * FROM complaints WHERE complaint_id=?", (cid,)).fetchone()

    # ---------------- pages ----------------
    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    # ---------------- auth ----------------
    @app.post("/api/login")
    def login():
        data = request.get_json(silent=True) or {}
        row = conn().execute("SELECT * FROM users WHERE username=? AND active=1",
                             (str(data.get("username", "")).strip(),)).fetchone()
        if not row or not check_password_hash(row["password_hash"], str(data.get("password", ""))):
            return err("Wrong username or password.", 401)
        token = secrets.token_urlsafe(32)
        hours = int(settings()["session_hours"])
        conn().execute("INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
                       (token, row["id"], now_ts(), (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")))
        g.user = dict(row)
        audit("login", "user", row["username"])
        conn().commit()
        return jsonify({"token": token, "user": {"username": row["username"], "full_name": row["full_name"],
                                                 "role": row["role"], "bureau": row["bureau"]}})

    @app.post("/api/logout")
    @auth_required()
    def logout():
        header = request.headers.get("Authorization", "")[7:]
        conn().execute("DELETE FROM sessions WHERE token=?", (header,))
        conn().commit()
        return jsonify({"ok": True})

    @app.get("/api/meta")
    @auth_required()
    def meta():
        last = conn().execute("SELECT MAX(ts) FROM complaint_history").fetchone()[0]
        return jsonify({
            "bureaus": [{"code": c, "name": n} for c, n in config.BUREAUS],
            "statuses": config.STATUSES, "categories": config.CATEGORIES, "regions": config.REGIONS,
            "definitions": config.DEFINITIONS, "data_label": config.DATA_LABEL,
            "coordination_decisions": COORD_DECISIONS, "last_updated": last,
            "settings": settings(),
        })

    # ---------------- dashboard ----------------
    @app.get("/api/dashboard")
    @auth_required()
    def dashboard():
        c, s, today = conn(), settings(), today_str()
        count = lambda where="1=1", args=(): c.execute(  # noqa: E731
            "SELECT COUNT(*) FROM complaints WHERE " + where, args).fetchone()[0]
        cards = {
            "total": count(),
            "pending": count("status='Pending'"),
            "under_process": count("status='Under Process'"),
            "disposed": count("status='Disposed'"),
            "transferred": count("status='Transferred'"),
            "escalated": count("status='Escalated'"),
            "overdue": count("status!='Disposed' AND expected_disposal_date < ?", (today,)),
            "potential_overlaps": c.execute("SELECT COUNT(*) FROM overlap_alerts WHERE status='Potential'").fetchone()[0],
        }
        by_bureau = [dict(r) for r in c.execute(
            "SELECT bureau AS label, COUNT(*) AS total, "
            "SUM(CASE WHEN status!='Disposed' THEN 1 ELSE 0 END) AS open_cases "
            "FROM complaints GROUP BY bureau ORDER BY total DESC")]
        by_region = [dict(r) for r in c.execute(
            "SELECT i.region AS label, COUNT(*) AS total FROM complaints c "
            "JOIN institutions i ON i.permanent_id=c.institution_id GROUP BY i.region ORDER BY total DESC")]
        by_status = [{"label": st, "total": count("status=?", (st,))} for st in config.STATUSES]
        top_inst = [dict(r) for r in c.execute(
            "SELECT i.permanent_id, i.name, COUNT(*) AS open_cases FROM complaints c "
            "JOIN institutions i ON i.permanent_id=c.institution_id WHERE c.status!='Disposed' "
            "GROUP BY i.permanent_id ORDER BY open_cases DESC, i.name LIMIT 5")]
        last = c.execute("SELECT MAX(ts) FROM complaint_history").fetchone()[0]
        return jsonify({"cards": cards, "by_bureau": by_bureau, "by_region": by_region, "by_status": by_status,
                        "top_institutions": top_inst, "last_updated": last, "data_label": config.DATA_LABEL,
                        "approaching_days": int(s["approaching_days"])})

    # ---------------- complaints ----------------
    @app.get("/api/complaints")
    @auth_required()
    def list_complaints():
        a = request.args
        where, args = ["1=1"], []
        if a.get("q"):
            like = "%" + a["q"].strip() + "%"
            where.append("(c.complaint_id LIKE ? OR c.source_ref LIKE ? OR i.name LIKE ? OR "
                         "i.permanent_id LIKE ? OR c.description LIKE ?)")
            args += [like] * 5
        for field, col in (("bureau", "c.bureau"), ("category", "c.category"), ("status", "c.status"),
                           ("region", "i.region"), ("institution_id", "c.institution_id")):
            if a.get(field):
                where.append(col + "=?")
                args.append(a[field])
        if a.get("date_from"):
            where.append("c.date_received >= ?")
            args.append(a["date_from"])
        if a.get("date_to"):
            where.append("c.date_received <= ?")
            args.append(a["date_to"])
        if a.get("overdue") == "1":
            where.append("c.status!='Disposed' AND c.expected_disposal_date < ?")
            args.append(today_str())
        limit = min(int(a.get("limit", 200)), 500)
        rows = conn().execute(
            "SELECT c.*, i.name AS institution_name, i.region AS region, "
            "(SELECT COUNT(*) FROM overlap_alerts o WHERE o.status IN ('Potential','Confirmed') "
            " AND (o.complaint_a=c.complaint_id OR o.complaint_b=c.complaint_id)) AS overlap_count "
            "FROM complaints c JOIN institutions i ON i.permanent_id=c.institution_id WHERE "
            + " AND ".join(where) + " ORDER BY c.date_received DESC, c.complaint_id LIMIT ?", args + [limit]).fetchall()
        items = []
        for r in rows:
            d = decorate(r, g.user)
            d.pop("complainant_name", None)
            d.pop("complainant_contact", None)
            items.append(d)
        return jsonify({"items": items, "count": len(items)})

    @app.get("/api/complaints/<cid>")
    @auth_required()
    def complaint_detail(cid):
        row = get_complaint(cid)
        if not row:
            return err("Complaint not found.", 404)
        c = decorate(row, g.user)
        inst = conn().execute("SELECT * FROM institutions WHERE permanent_id=?", (c["institution_id"],)).fetchone()
        history = [dict(r) for r in conn().execute(
            "SELECT * FROM complaint_history WHERE complaint_id=? ORDER BY ts, id", (cid,))]
        alerts = [dict(r) for r in conn().execute(
            "SELECT id, complaint_a, complaint_b, score, status, coordination_status FROM overlap_alerts "
            "WHERE complaint_a=? OR complaint_b=? ORDER BY id", (cid, cid))]
        links = [dict(r) for r in conn().execute(
            "SELECT * FROM complaint_links WHERE complaint_a=? OR complaint_b=?", (cid, cid))]
        if can_see_contact(g.user, c):
            audit("view_case_with_contact", "complaint", cid)
            conn().commit()
        return jsonify({"complaint": c, "institution": dict(inst), "history": history, "overlaps": alerts,
                        "links": links, "can_act": can_act(g.user, c)})

    @app.post("/api/complaints/<cid>/action")
    @auth_required("admin", "supervisor", "officer")
    def complaint_action(cid):
        row = get_complaint(cid)
        if not row:
            return err("Complaint not found.", 404)
        if not can_act(g.user, row):
            return err("Only the responsible Bureau/Cell's officers or a supervisor can act on this case.", 403)
        data = request.get_json(silent=True) or {}
        action = data.get("action")
        remarks = (data.get("remarks") or "").strip()
        prev_status, prev_bureau = row["status"], row["bureau"]
        is_senior = g.user["role"] in ("admin", "supervisor")

        if prev_status == "Disposed" and action != "remark" and not is_senior:
            return err("This case is disposed. Only a supervisor can reopen it.", 403)

        c = conn()
        if action == "update_status":
            to = data.get("to_status")
            if to not in config.STATUSES or to == "Transferred":
                return err("Choose a valid status. Use Transfer to move a case to another Bureau/Cell.")
            if to == "Disposed" and not remarks:
                return err("Remarks are required to dispose a case.")
            if to == prev_status:
                return err("The case is already in that status.")
            last = "Status changed to %s" % to
            c.execute("UPDATE complaints SET status=?, last_action=?, last_action_date=?, next_action=? "
                      "WHERE complaint_id=?", (to, last, today_str(), data.get("next_action") or row["next_action"], cid))
            add_history(cid, last, prev_status, to, remarks=remarks or None)
        elif action == "transfer":
            to_bureau = data.get("to_bureau")
            if to_bureau not in BUREAU_CODES or to_bureau == prev_bureau:
                return err("Choose a different, valid Bureau/Cell to transfer to.")
            if not remarks:
                return err("A reason is required for a transfer.")
            last = "Transferred from %s to %s" % (prev_bureau, to_bureau)
            c.execute("UPDATE complaints SET bureau=?, status='Transferred', assigned_officer=NULL, last_action=?, "
                      "last_action_date=?, next_action=? WHERE complaint_id=?",
                      (to_bureau, last, today_str(), "Receiving Bureau/Cell to assign an officer", cid))
            add_history(cid, "Transferred", prev_status, "Transferred", prev_bureau, to_bureau, remarks)
        elif action == "escalate":
            if not remarks:
                return err("A reason is required to escalate.")
            c.execute("UPDATE complaints SET status='Escalated', last_action=?, last_action_date=?, next_action=? "
                      "WHERE complaint_id=?", ("Escalated to competent authority", today_str(),
                                               "Decision by competent authority", cid))
            add_history(cid, "Escalated", prev_status, "Escalated", remarks=remarks)
        elif action == "assign":
            name = (data.get("officer") or "").strip()
            ok = c.execute("SELECT 1 FROM users WHERE full_name=? AND bureau=? AND role='officer' AND active=1",
                           (name, prev_bureau)).fetchone()
            if not ok:
                return err("That officer does not belong to %s." % prev_bureau)
            c.execute("UPDATE complaints SET assigned_officer=?, last_action=?, last_action_date=? "
                      "WHERE complaint_id=?", (name, "Assigned to %s" % name, today_str(), cid))
            add_history(cid, "Assigned to %s" % name, remarks=remarks or None)
        elif action == "remark":
            if not remarks:
                return err("Write a remark first.")
            c.execute("UPDATE complaints SET last_action=?, last_action_date=? WHERE complaint_id=?",
                      ("Remark recorded", today_str(), cid))
            add_history(cid, "Remark recorded", remarks=remarks)
        elif action == "correct":
            if not is_senior:
                return err("Only a supervisor can correct category or Bureau/Cell.", 403)
            category, bureau = data.get("category") or row["category"], data.get("bureau") or row["bureau"]
            if category not in config.CATEGORIES or bureau not in BUREAU_CODES:
                return err("Invalid category or Bureau/Cell.")
            if not remarks:
                return err("A reason is required for a correction.")
            c.execute("UPDATE complaints SET category=?, bureau=?, last_action=?, last_action_date=? "
                      "WHERE complaint_id=?", (category, bureau, "Record corrected", today_str(), cid))
            add_history(cid, "Record corrected (category: %s -> %s)" % (row["category"], category),
                        from_bureau=prev_bureau, to_bureau=bureau, remarks=remarks)
        else:
            return err("Unknown action.")
        audit("complaint_" + action, "complaint", cid, {"remarks": remarks})
        c.commit()
        return jsonify({"ok": True})

    # ---------------- institutions ----------------
    @app.get("/api/institutions")
    @auth_required()
    def list_institutions():
        q = "%" + request.args.get("q", "").strip() + "%"
        rows = conn().execute(
            "SELECT i.*, COUNT(c.complaint_id) AS total, "
            "SUM(CASE WHEN c.status!='Disposed' THEN 1 ELSE 0 END) AS open_cases, "
            "SUM(CASE WHEN c.status!='Disposed' AND c.expected_disposal_date < ? THEN 1 ELSE 0 END) AS overdue, "
            "(SELECT COUNT(*) FROM overlap_alerts o WHERE o.institution_id=i.permanent_id AND o.status='Potential') "
            "AS potential_overlaps "
            "FROM institutions i LEFT JOIN complaints c ON c.institution_id=i.permanent_id "
            "WHERE i.name LIKE ? OR i.permanent_id LIKE ? GROUP BY i.permanent_id ORDER BY i.permanent_id",
            (today_str(), q, q)).fetchall()
        return jsonify({"items": [dict(r) for r in rows]})

    @app.get("/api/institutions/<pid>")
    @auth_required()
    def institution_detail(pid):
        inst = conn().execute("SELECT * FROM institutions WHERE permanent_id=?", (pid,)).fetchone()
        if not inst:
            return err("Institution not found.", 404)
        rows = conn().execute("SELECT * FROM complaints WHERE institution_id=? ORDER BY date_received DESC", (pid,)).fetchall()
        complaints = []
        for r in rows:
            d = decorate(r, g.user)
            d.pop("complainant_name", None)
            d.pop("complainant_contact", None)
            complaints.append(d)
        per_bureau = {}
        for c in complaints:
            if c["status"] != "Disposed":
                per_bureau[c["bureau"]] = per_bureau.get(c["bureau"], 0) + 1
        alerts = [dict(r) for r in conn().execute(
            "SELECT id, complaint_a, complaint_b, score, status, coordination_status FROM overlap_alerts "
            "WHERE institution_id=? ORDER BY id", (pid,))]
        events = [dict(r) for r in conn().execute(
            "SELECT h.* FROM complaint_history h JOIN complaints c ON c.complaint_id=h.complaint_id "
            "WHERE c.institution_id=? ORDER BY h.ts DESC, h.id DESC LIMIT 100", (pid,))]
        return jsonify({"institution": dict(inst), "complaints": complaints, "open_by_bureau": per_bureau,
                        "overdue": sum(1 for c in complaints if c["overdue"]),
                        "overlaps": alerts, "history": events})

    # ---------------- overlaps ----------------
    def alert_summary(r):
        d = dict(r)
        d["reasons"] = json.loads(d["reasons"])
        return d

    @app.get("/api/overlaps")
    @auth_required()
    def list_overlaps():
        status = request.args.get("status")
        where, args = "1=1", []
        if status:
            where, args = "o.status=?", [status]
        rows = conn().execute(
            "SELECT o.*, i.name AS institution_name, ca.bureau AS bureau_a, cb.bureau AS bureau_b, "
            "ca.category AS category_a, cb.category AS category_b, ca.status AS status_a, cb.status AS status_b, "
            "(SELECT remark FROM coordination_notes n WHERE n.alert_id=o.id ORDER BY n.id DESC LIMIT 1) AS last_remark "
            "FROM overlap_alerts o JOIN institutions i ON i.permanent_id=o.institution_id "
            "JOIN complaints ca ON ca.complaint_id=o.complaint_a JOIN complaints cb ON cb.complaint_id=o.complaint_b "
            "WHERE " + where + " ORDER BY o.score DESC, o.id", args).fetchall()
        return jsonify({"items": [alert_summary(r) for r in rows]})

    @app.get("/api/overlaps/<int:aid>")
    @auth_required()
    def overlap_detail(aid):
        o = conn().execute("SELECT * FROM overlap_alerts WHERE id=?", (aid,)).fetchone()
        if not o:
            return err("Alert not found.", 404)
        ca, cb = get_complaint(o["complaint_a"]), get_complaint(o["complaint_b"])
        inst = conn().execute("SELECT * FROM institutions WHERE permanent_id=?", (o["institution_id"],)).fetchone()
        notes = [dict(r) for r in conn().execute("SELECT * FROM coordination_notes WHERE alert_id=? ORDER BY id", (aid,))]
        links = [dict(r) for r in conn().execute("SELECT * FROM complaint_links WHERE alert_id=?", (aid,))]
        return jsonify({"alert": alert_summary(o), "institution": dict(inst),
                        "a": decorate(ca, g.user), "b": decorate(cb, g.user), "notes": notes, "links": links,
                        "can_review": can_review_alert(g.user, ca, cb),
                        "decisions": COORD_DECISIONS})

    @app.post("/api/overlaps/detect")
    @auth_required("admin", "supervisor", "officer")
    def run_detection():
        s = settings()
        result = overlap.detect_overlaps(conn(), int(s["overlap_threshold"]), s["include_same_bureau"] == "1")
        audit("run_overlap_detection", "overlap", "-", result)
        conn().commit()
        return jsonify(result)

    @app.post("/api/overlaps/<int:aid>/review")
    @auth_required("admin", "supervisor", "officer")
    def review_alert(aid):
        o = conn().execute("SELECT * FROM overlap_alerts WHERE id=?", (aid,)).fetchone()
        if not o:
            return err("Alert not found.", 404)
        ca, cb = get_complaint(o["complaint_a"]), get_complaint(o["complaint_b"])
        if not can_review_alert(g.user, ca, cb):
            return err("Only officers of the involved Bureaus/Cells or a supervisor can review this alert.", 403)
        if o["status"] != "Potential":
            return err("This alert has already been reviewed.")
        data = request.get_json(silent=True) or {}
        decision, remarks = data.get("decision"), (data.get("remarks") or "").strip()
        if decision not in ("confirm", "dismiss"):
            return err("Decision must be confirm or dismiss.")
        if not remarks:
            return err("Remarks are required to record the review.")
        new_status = "Confirmed" if decision == "confirm" else "Dismissed"
        conn().execute("UPDATE overlap_alerts SET status=?, reviewed_by=?, reviewed_at=?, review_remarks=? WHERE id=?",
                       (new_status, g.user["full_name"], now_ts(), remarks, aid))
        if decision == "confirm":
            conn().execute("INSERT INTO complaint_links (complaint_a, complaint_b, alert_id, linked_by, linked_at, note) "
                           "VALUES (?,?,?,?,?,?)", (o["complaint_a"], o["complaint_b"], aid, g.user["full_name"], now_ts(), remarks))
        for me, other in ((o["complaint_a"], o["complaint_b"]), (o["complaint_b"], o["complaint_a"])):
            add_history(me, "Overlap alert #%d %s (related case %s)" % (aid, new_status.lower(), other), remarks=remarks)
        audit("overlap_" + decision, "overlap", aid, {"remarks": remarks})
        conn().commit()
        return jsonify({"ok": True, "status": new_status})

    @app.post("/api/overlaps/<int:aid>/coordination")
    @auth_required("admin", "supervisor", "officer")
    def add_coordination(aid):
        o = conn().execute("SELECT * FROM overlap_alerts WHERE id=?", (aid,)).fetchone()
        if not o:
            return err("Alert not found.", 404)
        ca, cb = get_complaint(o["complaint_a"]), get_complaint(o["complaint_b"])
        if not can_review_alert(g.user, ca, cb):
            return err("Only officers of the involved Bureaus/Cells or a supervisor can add coordination remarks.", 403)
        if o["status"] == "Dismissed":
            return err("This alert was dismissed. No coordination is needed.")
        data = request.get_json(silent=True) or {}
        remark, decision = (data.get("remark") or "").strip(), data.get("decision") or None
        if not remark:
            return err("Write a coordination remark.")
        if decision and decision not in COORD_DECISIONS:
            return err("Invalid coordination decision.")
        conn().execute("INSERT INTO coordination_notes (alert_id, ts, username, bureau, remark, decision) VALUES (?,?,?,?,?,?)",
                       (aid, now_ts(), g.user["full_name"], g.user["bureau"] or g.user["role"], remark, decision))
        status = "Decision recorded" if decision else ("In discussion" if o["coordination_status"] == "Not started" else o["coordination_status"])
        conn().execute("UPDATE overlap_alerts SET coordination_status=? WHERE id=?", (status, aid))
        for cid in (o["complaint_a"], o["complaint_b"]):
            add_history(cid, "Coordination remark recorded (alert #%d)" % aid,
                        remarks=remark + ((" [Decision: %s]" % decision) if decision else ""))
        audit("coordination_note", "overlap", aid, {"decision": decision})
        conn().commit()
        return jsonify({"ok": True, "coordination_status": status})

    # ---------------- alerts ----------------
    @app.get("/api/alerts")
    @auth_required()
    def alerts():
        s, today = settings(), date.today()
        approaching = int(s["approaching_days"])
        stale = int(s["stale_days"])
        base = ("SELECT c.complaint_id, c.institution_id, i.name AS institution_name, c.bureau, c.category, c.status, "
                "c.expected_disposal_date, c.last_action_date, c.assigned_officer FROM complaints c "
                "JOIN institutions i ON i.permanent_id=c.institution_id WHERE c.status!='Disposed' ")
        rows = conn().execute(base + "ORDER BY c.expected_disposal_date").fetchall()
        out = {"approaching": [], "overdue": [], "no_recent_action": []}
        for r in rows:
            d = dict(r)
            left = (date.fromisoformat(d["expected_disposal_date"]) - today).days
            d["days_left"] = left
            idle = (today - date.fromisoformat(d["last_action_date"])).days
            d["days_since_action"] = idle
            if left < 0:
                out["overdue"].append(d)
            elif left <= approaching:
                out["approaching"].append(d)
            if idle > stale:
                out["no_recent_action"].append(d)
        out["no_recent_action"].sort(key=lambda x: -x["days_since_action"])
        out["potential_overlaps"] = [alert_summary(r) for r in conn().execute(
            "SELECT o.*, i.name AS institution_name FROM overlap_alerts o JOIN institutions i "
            "ON i.permanent_id=o.institution_id WHERE o.status='Potential' ORDER BY o.score DESC")]
        out["coordination_required"] = [alert_summary(r) for r in conn().execute(
            "SELECT o.*, i.name AS institution_name FROM overlap_alerts o JOIN institutions i "
            "ON i.permanent_id=o.institution_id WHERE o.status IN ('Potential','Confirmed') "
            "AND o.coordination_status!='Decision recorded' ORDER BY o.status DESC, o.score DESC")]
        out["settings"] = {"approaching_days": approaching, "stale_days": stale}
        return jsonify(out)

    # ---------------- reports ----------------
    def build_report(kind):
        c, today = conn(), today_str()
        q = lambda sql, args=(): [dict(r) for r in c.execute(sql, args)]  # noqa: E731
        if kind == "bureau":
            rows = q("SELECT bureau AS Bureau, COUNT(*) AS Total, "
                     "SUM(status='Pending') AS Pending, SUM(status='Under Process') AS Under_Process, "
                     "SUM(status='Transferred') AS Transferred, SUM(status='Escalated') AS Escalated, "
                     "SUM(status='Disposed') AS Disposed, "
                     "SUM(status!='Disposed' AND expected_disposal_date < ?) AS Overdue "
                     "FROM complaints GROUP BY bureau ORDER BY bureau", (today,))
            return "Bureau/Cell-wise complaints", rows
        if kind == "region":
            rows = q("SELECT i.region AS Region, COUNT(*) AS Total, SUM(c.status!='Disposed') AS Open_cases, "
                     "SUM(c.status='Disposed') AS Disposed, "
                     "SUM(c.status!='Disposed' AND c.expected_disposal_date < ?) AS Overdue "
                     "FROM complaints c JOIN institutions i ON i.permanent_id=c.institution_id "
                     "GROUP BY i.region ORDER BY i.region", (today,))
            return "Region-wise complaints", rows
        if kind == "status":
            rows = q("SELECT status AS Status, COUNT(*) AS Total FROM complaints GROUP BY status ORDER BY Total DESC")
            return "Status-wise complaints", rows
        if kind == "overdue":
            rows = q("SELECT c.complaint_id AS Complaint, i.name AS Institution, c.bureau AS Bureau, c.category AS Category, "
                     "c.status AS Status, c.expected_disposal_date AS Expected_date, "
                     "CAST(julianday(?) - julianday(c.expected_disposal_date) AS INTEGER) AS Days_overdue "
                     "FROM complaints c JOIN institutions i ON i.permanent_id=c.institution_id "
                     "WHERE c.status!='Disposed' AND c.expected_disposal_date < ? ORDER BY Days_overdue DESC", (today, today))
            return "Overdue complaints", rows
        if kind == "institution":
            rows = q("SELECT i.permanent_id AS Permanent_ID, i.name AS Institution, i.region AS Region, "
                     "COUNT(c.complaint_id) AS Total, SUM(c.status!='Disposed') AS Open_cases, "
                     "SUM(c.status='Disposed') AS Disposed, "
                     "SUM(c.status!='Disposed' AND c.expected_disposal_date < ?) AS Overdue "
                     "FROM institutions i LEFT JOIN complaints c ON c.institution_id=i.permanent_id "
                     "GROUP BY i.permanent_id ORDER BY Total DESC, i.permanent_id", (today,))
            return "Institution-wise complaint history", rows
        if kind == "overlaps":
            rows = q("SELECT o.id AS Alert, i.name AS Institution, o.complaint_a AS Case_A, ca.bureau AS Bureau_A, "
                     "o.complaint_b AS Case_B, cb.bureau AS Bureau_B, o.score AS Score, o.status AS Review_status, "
                     "o.coordination_status AS Coordination FROM overlap_alerts o "
                     "JOIN institutions i ON i.permanent_id=o.institution_id "
                     "JOIN complaints ca ON ca.complaint_id=o.complaint_a JOIN complaints cb ON cb.complaint_id=o.complaint_b "
                     "ORDER BY o.score DESC")
            return "Potential overlaps and their review outcome", rows
        if kind == "ageing":
            rows = q("SELECT CASE WHEN age<=30 THEN '0-30 days' WHEN age<=60 THEN '31-60 days' "
                     "WHEN age<=90 THEN '61-90 days' ELSE 'Over 90 days' END AS Age_of_open_cases, COUNT(*) AS Cases "
                     "FROM (SELECT CAST(julianday(?) - julianday(date_received) AS INTEGER) AS age FROM complaints "
                     "WHERE status!='Disposed') GROUP BY 1 ORDER BY MIN(age)", (today,))
            total = c.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
            disposed = c.execute("SELECT COUNT(*) FROM complaints WHERE status='Disposed'").fetchone()[0]
            avg = c.execute(
                "SELECT AVG(julianday(substr(h.ts,1,10)) - julianday(c.date_received)) FROM complaints c "
                "JOIN complaint_history h ON h.complaint_id=c.complaint_id AND h.to_status='Disposed' "
                "WHERE c.status='Disposed'").fetchone()[0]
            rows.append({"Age_of_open_cases": "Disposal rate (disposed / total)",
                         "Cases": "%d%% (%d of %d)" % (round(100 * disposed / total) if total else 0, disposed, total)})
            rows.append({"Age_of_open_cases": "Average days to dispose", "Cases": round(avg, 1) if avg else "n/a"})
            return "Pending-case ageing and disposal statistics", rows
        if kind == "monthly":
            rows = q("SELECT substr(date_received,1,7) AS Month, COUNT(*) AS Received FROM complaints "
                     "GROUP BY 1 ORDER BY 1 DESC")
            disposed = {r["m"]: r["n"] for r in q(
                "SELECT substr(h.ts,1,7) AS m, COUNT(*) AS n FROM complaint_history h WHERE h.to_status='Disposed' GROUP BY 1")}
            for r in rows:
                r["Disposed"] = disposed.get(r["Month"], 0)
            return "Monthly received vs disposed", rows
        return None, None

    REPORT_KINDS = ["bureau", "region", "status", "overdue", "institution", "overlaps", "ageing", "monthly"]

    @app.get("/api/reports/<kind>")
    @auth_required()
    def report(kind):
        title, rows = build_report(kind)
        if title is None:
            return err("Unknown report.", 404)
        cols = list(rows[0].keys()) if rows else []
        if request.args.get("format") == "csv":
            if g.user["role"] not in ("admin", "supervisor"):
                return err("Only a supervisor or admin can export reports.", 403)
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(cols)
            for r in rows:
                writer.writerow([r[k] for k in cols])
            audit("export_report", "report", kind, {"rows": len(rows)})
            conn().commit()
            return Response(buf.getvalue(), mimetype="text/csv",
                            headers={"Content-Disposition": "attachment; filename=report_%s_%s.csv" % (kind, today_str())})
        return jsonify({"title": title, "kind": kind, "columns": cols, "rows": rows,
                        "generated_at": now_ts(), "data_label": config.DATA_LABEL, "kinds": REPORT_KINDS})

    # ---------------- admin ----------------
    @app.get("/api/users")
    @auth_required("admin")
    def users():
        rows = conn().execute("SELECT id, username, full_name, role, bureau, active FROM users ORDER BY id").fetchall()
        return jsonify({"items": [dict(r) for r in rows]})

    @app.get("/api/audit")
    @auth_required("admin")
    def audit_view():
        rows = conn().execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 100").fetchall()
        return jsonify({"items": [dict(r) for r in rows]})

    @app.get("/api/settings")
    @auth_required()
    def get_settings():
        sla = [dict(r) for r in conn().execute("SELECT * FROM sla_rules ORDER BY category")]
        return jsonify({"settings": settings(), "sla_rules": sla})

    @app.put("/api/settings")
    @auth_required("admin")
    def put_settings():
        data = request.get_json(silent=True) or {}
        for key, value in (data.get("settings") or {}).items():
            if key not in config.DEFAULT_SETTINGS:
                return err("Unknown setting: %s" % key)
            if not str(value).isdigit():
                return err("%s must be a whole number." % key)
            conn().execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, str(value)))
        for cat, days in (data.get("sla_days") or {}).items():
            if cat not in config.CATEGORIES or not str(days).isdigit() or int(days) < 1:
                return err("Invalid SLA for %s." % cat)
            conn().execute("UPDATE sla_rules SET days=? WHERE category=?", (int(days), cat))
        audit("update_settings", "settings", "-", data)
        conn().commit()
        return jsonify({"ok": True})

    return app


if __name__ == "__main__":
    create_app().run(debug=True, port=5000)
