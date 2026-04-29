CREATE TABLE IF NOT EXISTS jobs (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    source                  TEXT    NOT NULL,
    external_id             TEXT    NOT NULL,
    company                 TEXT    NOT NULL,
    title                   TEXT    NOT NULL,
    url                     TEXT    NOT NULL,
    posted_at               TEXT    NOT NULL,
    discovered_at           TEXT    NOT NULL,
    location                TEXT,
    remote                  INTEGER NOT NULL DEFAULT 0,
    comp_min                INTEGER,
    comp_max                INTEGER,
    description_md          TEXT,
    score                   INTEGER,
    score_reason            TEXT,
    status                  TEXT    NOT NULL DEFAULT 'new',
    status_changed_at       TEXT,
    scored_with_prefs_at    TEXT,
    scored_with_model       TEXT,
    UNIQUE (source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status);
CREATE INDEX IF NOT EXISTS idx_jobs_score  ON jobs (score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs (source);

CREATE TABLE IF NOT EXISTS sources (
    name              TEXT PRIMARY KEY,
    last_fetched_at   TEXT,
    last_error        TEXT,
    cooldown_until    TEXT,
    enabled           INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id       INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    type         TEXT    NOT NULL,
    payload_json TEXT    NOT NULL DEFAULT '{}',
    cost_usd     REAL,
    tokens       INTEGER,
    created_at   TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_job_id ON events (job_id);
CREATE INDEX IF NOT EXISTS idx_events_type   ON events (type);
