CREATE TABLE IF NOT EXISTS applications (
    job_id            INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    applied_at        TEXT,
    applied_via       TEXT,
    follow_up_due     TEXT,
    salary_offered    INTEGER,
    decision          TEXT,
    decision_reason   TEXT,
    lessons           TEXT
);

CREATE TABLE IF NOT EXISTS contacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id  INTEGER NOT NULL REFERENCES applications(job_id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    email           TEXT,
    role            TEXT,
    source          TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_contacts_application_id ON contacts (application_id);

CREATE TABLE IF NOT EXISTS tailor_outputs (
    job_id     INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    output_dir TEXT NOT NULL,
    rendered_at TEXT NOT NULL,
    cost_usd   REAL NOT NULL DEFAULT 0.0,
    tokens_in  INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0
);
