"""db.py - SQLite database ka schema aur connection helpers."""
import sqlite3
import os

SCHEMA = """
CREATE TABLE IF NOT EXISTS institutions (
    permanent_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT,
    city TEXT,
    state TEXT,
    region TEXT,
    institution_type TEXT,
    is_synthetic INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    bureau TEXT,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS complaints (
    complaint_id TEXT PRIMARY KEY,
    source_ref TEXT,
    source_system TEXT,
    source_channel TEXT,
    institution_id TEXT NOT NULL REFERENCES institutions(permanent_id),
    category TEXT NOT NULL,
    subcategory TEXT,
    description TEXT,
    date_received TEXT NOT NULL,
    bureau TEXT NOT NULL,
    assigned_officer TEXT,
    status TEXT NOT NULL,
    last_action TEXT,
    last_action_date TEXT,
    next_action TEXT,
    expected_disposal_date TEXT,
    sla_days INTEGER,
    applicable_procedure TEXT,
    external_ref TEXT,
    complainant_name TEXT,
    complainant_contact TEXT,
    is_synthetic INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_c_inst ON complaints(institution_id);
CREATE INDEX IF NOT EXISTS idx_c_status ON complaints(status);

CREATE TABLE IF NOT EXISTS complaint_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id TEXT NOT NULL REFERENCES complaints(complaint_id),
    ts TEXT NOT NULL,
    action TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    from_bureau TEXT,
    to_bureau TEXT,
    actor TEXT,
    actor_bureau TEXT,
    remarks TEXT
);
CREATE INDEX IF NOT EXISTS idx_h_c ON complaint_history(complaint_id);

CREATE TABLE IF NOT EXISTS overlap_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_a TEXT NOT NULL REFERENCES complaints(complaint_id),
    complaint_b TEXT NOT NULL REFERENCES complaints(complaint_id),
    institution_id TEXT NOT NULL,
    score INTEGER NOT NULL,
    reasons TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Potential',
    detected_at TEXT NOT NULL,
    reviewed_by TEXT,
    reviewed_at TEXT,
    review_remarks TEXT,
    coordination_status TEXT NOT NULL DEFAULT 'Not started',
    UNIQUE(complaint_a, complaint_b)
);

CREATE TABLE IF NOT EXISTS complaint_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_a TEXT NOT NULL,
    complaint_b TEXT NOT NULL,
    alert_id INTEGER,
    linked_by TEXT,
    linked_at TEXT,
    note TEXT
);

CREATE TABLE IF NOT EXISTS coordination_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id INTEGER NOT NULL REFERENCES overlap_alerts(id),
    ts TEXT NOT NULL,
    username TEXT,
    bureau TEXT,
    remark TEXT NOT NULL,
    decision TEXT
);

CREATE TABLE IF NOT EXISTS sla_rules (
    category TEXT PRIMARY KEY,
    days INTEGER NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    username TEXT,
    action TEXT NOT NULL,
    entity TEXT,
    entity_id TEXT,
    details TEXT
);
"""


def connect(path):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path):
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
