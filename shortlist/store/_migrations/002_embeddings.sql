-- Embeddings for job descriptions (one vector per job).
-- Vector dimension is 384 (bge-small-en-v1.5 output dim).
CREATE VIRTUAL TABLE IF NOT EXISTS job_embeddings USING vec0(
    job_id   INTEGER PRIMARY KEY,
    embedding FLOAT[384]
);

-- Cache resume embeddings keyed by file path + mtime so we don't re-embed
-- the same resume on every run.
CREATE TABLE IF NOT EXISTS resume_embeddings (
    path     TEXT NOT NULL,
    mtime    REAL NOT NULL,
    model    TEXT NOT NULL,
    vector   BLOB NOT NULL,
    PRIMARY KEY (path, mtime, model)
);

-- Track per-job scoring runs for cost / debugging.
CREATE TABLE IF NOT EXISTS scoring_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    model        TEXT NOT NULL,
    job_count    INTEGER NOT NULL DEFAULT 0,
    cost_usd     REAL    NOT NULL DEFAULT 0.0,
    tokens_in    INTEGER NOT NULL DEFAULT 0,
    tokens_out   INTEGER NOT NULL DEFAULT 0,
    error        TEXT
);
