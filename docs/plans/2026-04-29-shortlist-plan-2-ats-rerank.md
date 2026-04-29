# Shortlist — Plan 2 of 6 (ATS Expansion + Embeddings + LLM Rerank)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the remaining four ATS sources (Lever, Ashby, Workable, SmartRecruiters), introduce local-model embeddings via `sentence-transformers` + `sqlite-vec`, and replace the Plan-1 placeholder ranking with a real two-stage pipeline: hard-filter → cosine pre-rank → Haiku 4.5 LLM rerank with budget guard. After Plan 2, `shortlist rank` produces meaningful 0–100 scores with a one-line LLM reason per top job.

**Architecture:** Same three layers as Plan 1 (`sources` / `store` / `cli`), plus a new `ranker.embeddings` module (loads `bge-small-en-v1.5` once per process, caches resume embedding by mtime), a new `ranker.llm_rerank` module (Anthropic client with hard daily/monthly USD caps), and a second migration (`002_embeddings.sql`) adding a `sqlite-vec` virtual table for job embeddings plus a `resume_embeddings` cache. The four new ATS sources follow the Greenhouse pattern from Plan 1 (`Source` ABC, HTTP client + `_normalize` + `…Source` class).

**Tech Stack additions:** `sentence-transformers>=3.0`, `sqlite-vec>=0.1.6`, `anthropic>=0.40`, `numpy>=1.26`.

**Plan-2 file map (added/modified relative to Plan 1):**

```
shortlist/
├── pyproject.toml                         (modify — new deps)
├── shortlist/
│   ├── store/
│   │   ├── db.py                          (modify — load sqlite-vec, embedding helpers)
│   │   └── _migrations/
│   │       └── 002_embeddings.sql         (new)
│   ├── sources/ats/
│   │   ├── lever.py                       (new)
│   │   ├── ashby.py                       (new)
│   │   ├── workable.py                    (new)
│   │   └── smartrecruiters.py             (new)
│   ├── ranker/
│   │   ├── embeddings.py                  (new — sentence-transformers wrapper)
│   │   ├── llm_rerank.py                  (new — Anthropic Haiku client)
│   │   └── pipeline.py                    (new — full rank pipeline orchestrator)
│   ├── config.py                          (modify — per-source company lists)
│   └── cli.py                             (modify — fetch enumerates 5 sources, rank uses pipeline)
└── tests/
    ├── fixtures/
    │   ├── lever_acme.json                (new)
    │   ├── ashby_acme.json                (new)
    │   ├── workable_acme.json             (new)
    │   ├── smartrecruiters_acme.json      (new)
    │   └── llm_responses/
    │       └── haiku_rerank_sample.json   (new)
    ├── unit/
    │   ├── test_embeddings.py             (new)
    │   └── test_llm_rerank.py             (new)
    └── integration/
        ├── test_lever.py                  (new)
        ├── test_ashby.py                  (new)
        ├── test_workable.py               (new)
        ├── test_smartrecruiters.py        (new)
        ├── test_pipeline.py               (new — end-to-end pipeline)
        └── test_cli.py                    (extend — fetch+rank cover all sources, --no-llm flag)
```

**Plan location:** Currently in monorepo at `<monorepo>/docs/superpowers/plans/2026-04-29-shortlist-plan-2-ats-rerank.md`. Task 13 migrates it to `~/dev/repos/shortlist/docs/plans/`.

---

## Task 1: New deps + migration 002 (sqlite-vec embeddings table)

**Files:**
- Modify: `pyproject.toml`
- Create: `shortlist/store/_migrations/002_embeddings.sql`
- Modify: `shortlist/store/db.py` (load sqlite-vec extension on connect)
- Modify: `tests/integration/test_store.py` (add migration-002 test)

- [ ] **Step 1: Update `pyproject.toml` dependencies**

In `[project] dependencies`, append:

```toml
    "sentence-transformers>=3.0",
    "sqlite-vec>=0.1.6",
    "anthropic>=0.40",
    "numpy>=1.26",
```

- [ ] **Step 2: Reinstall**

```bash
cd ~/dev/repos/shortlist
source .venv/bin/activate
pip install -e ".[dev]"
```

Expected: ~600MB transitive (torch, transformers, scipy). Allow several minutes.

- [ ] **Step 3: Write migration 002**

`shortlist/store/_migrations/002_embeddings.sql`:

```sql
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
```

- [ ] **Step 4: Update `connect()` in `shortlist/store/db.py` to load sqlite-vec**

At the top of the file, add `import sqlite_vec`. Modify `connect()` so it reads:

```python
@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection with sqlite-vec, WAL mode, and FK enforcement."""
    conn = sqlite3.connect(path)
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

- [ ] **Step 5: Append failing test**

To `tests/integration/test_store.py`:

```python
def test_migrate_to_v2_creates_embeddings_tables(db_path: Path):
    migrate(db_path)
    assert current_version(db_path) == 2
    with connect(db_path) as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','virtual')"
        )}
    assert "job_embeddings" in names
    assert "resume_embeddings" in names
    assert "scoring_runs" in names


def test_sqlite_vec_extension_loads(db_path: Path):
    migrate(db_path)
    with connect(db_path) as conn:
        row = conn.execute("SELECT vec_version()").fetchone()
    assert row is not None
```

- [ ] **Step 6: Run gates + commit**

```bash
pytest tests/integration/test_store.py -v
ruff check . && ruff format --check . && mypy shortlist
git add pyproject.toml shortlist/store/_migrations/002_embeddings.sql shortlist/store/db.py tests/integration/test_store.py
git commit -m "feat(store): migration 002 — sqlite-vec embeddings + resume cache + scoring_runs"
```

Expected: 2 new tests pass, 53 prior still pass = 55 total.

---

## Task 2: Embedding service (`ranker.embeddings`)

**Files:**
- Create: `shortlist/ranker/embeddings.py`
- Create: `tests/unit/test_embeddings.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_embeddings.py
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from shortlist.ranker.embeddings import (
    DEFAULT_MODEL,
    EmbeddingService,
    embed_resume_cached,
)


@pytest.fixture
def fake_model():
    """Deterministic fake SentenceTransformer."""
    m = MagicMock()
    def _encode(text, **_):
        if isinstance(text, str):
            text = [text]
        out = []
        for t in text:
            seed = sum(ord(c) for c in t)
            rng = np.random.default_rng(seed)
            v = rng.standard_normal(384).astype("float32")
            v /= np.linalg.norm(v)
            out.append(v)
        return np.array(out)
    m.encode = _encode
    m.get_sentence_embedding_dimension.return_value = 384
    return m


def test_embedding_service_encode_returns_384_float32(fake_model):
    svc = EmbeddingService(_model=fake_model)
    vec = svc.encode("hello world")
    assert vec.shape == (384,)
    assert vec.dtype == np.float32


def test_encode_is_deterministic_for_same_text(fake_model):
    svc = EmbeddingService(_model=fake_model)
    a = svc.encode("hello")
    b = svc.encode("hello")
    np.testing.assert_array_equal(a, b)


def test_default_model_constant():
    assert DEFAULT_MODEL == "BAAI/bge-small-en-v1.5"


def test_resume_cache_skips_re_embed_when_mtime_unchanged(tmp_path, fake_model):
    resume = tmp_path / "resume.md"
    resume.write_text("Senior backend engineer with Python experience.")
    db = tmp_path / "shortlist.sqlite"

    from shortlist.store.db import migrate
    migrate(db)

    svc = EmbeddingService(_model=fake_model)
    encode_calls: list[str] = []
    orig_encode = fake_model.encode
    def _spy(text, **kw):
        encode_calls.append(text)
        return orig_encode(text, **kw)
    fake_model.encode = _spy

    v1 = embed_resume_cached(db, resume, service=svc)
    v2 = embed_resume_cached(db, resume, service=svc)
    np.testing.assert_array_equal(v1, v2)
    assert len(encode_calls) == 1


def test_resume_cache_recomputes_when_mtime_changes(tmp_path, fake_model):
    import os
    resume = tmp_path / "resume.md"
    resume.write_text("v1")
    db = tmp_path / "shortlist.sqlite"

    from shortlist.store.db import migrate
    migrate(db)

    svc = EmbeddingService(_model=fake_model)
    embed_resume_cached(db, resume, service=svc)

    resume.write_text("v2")
    new_mtime = os.path.getmtime(resume) + 5
    os.utime(resume, (new_mtime, new_mtime))

    encode_calls: list[str] = []
    orig = fake_model.encode
    def _spy(text, **kw):
        encode_calls.append(text)
        return orig(text, **kw)
    fake_model.encode = _spy

    embed_resume_cached(db, resume, service=svc)
    assert len(encode_calls) == 1
```

- [ ] **Step 2: Implement `shortlist/ranker/embeddings.py`**

```python
"""Embedding service.

Loads a sentence-transformers model lazily and exposes:
  - `EmbeddingService.encode(text)` → np.ndarray (float32, shape (384,))
  - `embed_resume_cached(db, path, service)` → cached resume vector keyed by
    (path, mtime, model).

Tests inject a `_model` to avoid downloading the real ~90 MB model.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np

from shortlist.store.db import connect

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


def _load_model(name: str = DEFAULT_MODEL) -> Any:
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(name)


class EmbeddingService:
    def __init__(self, *, model_name: str = DEFAULT_MODEL, _model: Any | None = None):
        self.model_name = model_name
        self._model = _model

    @property
    def model(self) -> Any:
        if self._model is None:
            self._model = _load_model(self.model_name)
        return self._model

    def encode(self, text: str) -> np.ndarray:
        out = self.model.encode(text, normalize_embeddings=True)
        if isinstance(out, np.ndarray) and out.ndim == 2:
            out = out[0]
        return np.asarray(out, dtype=np.float32)


def embed_resume_cached(
    db_path: Path, resume_path: Path, *, service: EmbeddingService
) -> np.ndarray:
    """Embed `resume_path`, caching by (path, mtime, model)."""
    resume_path = resume_path.expanduser().resolve()
    mtime = os.path.getmtime(resume_path)
    model = service.model_name

    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT vector FROM resume_embeddings "
            "WHERE path = ? AND mtime = ? AND model = ?",
            (str(resume_path), mtime, model),
        ).fetchone()
        if row is not None:
            return np.frombuffer(row[0], dtype=np.float32).copy()

        text = resume_path.read_text()
        vec = service.encode(text)
        conn.execute(
            "INSERT OR REPLACE INTO resume_embeddings (path, mtime, model, vector) "
            "VALUES (?, ?, ?, ?)",
            (str(resume_path), mtime, model, vec.tobytes()),
        )
        return vec
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/unit/test_embeddings.py -v
ruff check . && ruff format --check . && mypy shortlist
git add shortlist/ranker/embeddings.py tests/unit/test_embeddings.py
git commit -m "feat(ranker): EmbeddingService + cached resume embedding"
```

Expected: 5 new pass + 55 prior = 60 total.

---

## Task 3: Store helpers — `upsert_embedding`, `cosine_top_k`

**Files:**
- Modify: `shortlist/store/db.py`
- Modify: `tests/integration/test_store.py`

- [ ] **Step 1: Append failing tests**

```python
def test_upsert_embedding_round_trips(db_path: Path):
    from shortlist.store.db import upsert_embedding, get_embedding
    import numpy as np
    migrate(db_path)
    job = upsert_job(db_path, _raw())
    vec = np.arange(384, dtype=np.float32) / 384.0
    upsert_embedding(db_path, job.id, vec)
    out = get_embedding(db_path, job.id)
    assert out is not None
    np.testing.assert_allclose(out, vec, atol=1e-6)


def test_cosine_top_k_returns_ordered_job_ids(db_path: Path):
    from shortlist.store.db import upsert_embedding, cosine_top_k
    import numpy as np
    migrate(db_path)
    j1 = upsert_job(db_path, _raw("gh_1", title="Senior Backend Engineer"))
    j2 = upsert_job(db_path, _raw("gh_2", title="Frontend Engineer"))
    j3 = upsert_job(db_path, _raw("gh_3", title="ML Engineer"))

    rng = np.random.default_rng(0)
    target = rng.standard_normal(384).astype("float32")
    target /= np.linalg.norm(target)

    near = (target + rng.standard_normal(384).astype("float32") * 0.01)
    near /= np.linalg.norm(near)
    far = -target

    upsert_embedding(db_path, j1.id, near)
    upsert_embedding(db_path, j2.id, target)
    upsert_embedding(db_path, j3.id, far)

    top = cosine_top_k(db_path, target, k=2)
    assert [j for (j, _d) in top] == [j2.id, j1.id]
```

- [ ] **Step 2: Append to `shortlist/store/db.py`**

```python
import numpy as np


def upsert_embedding(path: Path, job_id: int, vec: np.ndarray) -> None:
    if vec.dtype != np.float32:
        vec = vec.astype(np.float32)
    if vec.shape != (384,):
        raise ValueError(f"expected (384,) vector, got {vec.shape}")
    with connect(path) as conn:
        conn.execute("DELETE FROM job_embeddings WHERE job_id = ?", (job_id,))
        conn.execute(
            "INSERT INTO job_embeddings (job_id, embedding) VALUES (?, ?)",
            (job_id, vec.tobytes()),
        )


def get_embedding(path: Path, job_id: int) -> np.ndarray | None:
    with connect(path) as conn:
        row = conn.execute(
            "SELECT embedding FROM job_embeddings WHERE job_id = ?", (job_id,)
        ).fetchone()
    if row is None:
        return None
    return np.frombuffer(row[0], dtype=np.float32).copy()


def cosine_top_k(
    path: Path, query: np.ndarray, *, k: int = 30
) -> list[tuple[int, float]]:
    """Return up to k (job_id, distance) ordered by ascending vec0 distance.

    sqlite-vec uses L2 by default; on normalized vectors L2-rank ≡ cosine-rank,
    so we ask sentence-transformers to normalize at encode time.
    """
    if query.dtype != np.float32:
        query = query.astype(np.float32)
    with connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT job_id, distance
            FROM job_embeddings
            WHERE embedding MATCH ?
            ORDER BY distance
            LIMIT ?
            """,
            (query.tobytes(), int(k)),
        ).fetchall()
    return [(int(r["job_id"]), float(r["distance"])) for r in rows]
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/integration/test_store.py -v
ruff check . && ruff format --check . && mypy shortlist
git add shortlist/store/db.py tests/integration/test_store.py
git commit -m "feat(store): upsert_embedding + cosine_top_k via sqlite-vec"
```

Expected: 2 new pass + 60 prior = 62 total.

---

## Task 4: Anthropic Haiku rerank client

**Files:**
- Create: `shortlist/ranker/llm_rerank.py`
- Create: `tests/unit/test_llm_rerank.py`
- Create: `tests/fixtures/llm_responses/haiku_rerank_sample.json`

- [ ] **Step 1: Create LLM response fixture**

`tests/fixtures/llm_responses/haiku_rerank_sample.json`:

```json
{
  "id": "msg_test_001",
  "type": "message",
  "role": "assistant",
  "model": "claude-haiku-4-5-20251001",
  "stop_reason": "end_turn",
  "content": [
    {
      "type": "text",
      "text": "[\n  {\"id\": 1, \"score\": 87, \"reason\": \"strong python+postgres match\"},\n  {\"id\": 2, \"score\": 62, \"reason\": \"adjacent stack, less seniority overlap\"}\n]"
    }
  ],
  "usage": {"input_tokens": 1024, "output_tokens": 96}
}
```

- [ ] **Step 2: Write failing tests**

```python
# tests/unit/test_llm_rerank.py
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from shortlist.ranker.llm_rerank import (
    HAIKU_INPUT_PRICE_PER_MTOK,
    HAIKU_OUTPUT_PRICE_PER_MTOK,
    LLMReranker,
    RerankRequest,
    estimate_cost,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _fake_message(text: str, in_tok: int = 100, out_tok: int = 50):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    msg.usage.input_tokens = in_tok
    msg.usage.output_tokens = out_tok
    return msg


def test_estimate_cost_uses_published_haiku_pricing():
    cost = estimate_cost(input_tokens=1_000_000, output_tokens=0)
    assert cost == pytest.approx(HAIKU_INPUT_PRICE_PER_MTOK, rel=1e-6)


def test_reranker_parses_valid_json_response():
    fixture = json.loads((FIXTURES / "llm_responses/haiku_rerank_sample.json").read_text())
    text = fixture["content"][0]["text"]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_message(text, in_tok=1024, out_tok=96)

    rr = LLMReranker(client=fake_client, model="claude-haiku-4-5-20251001")
    req = RerankRequest(
        resume="Senior backend engineer.",
        prefs_summary="Python, Postgres.",
        candidates=[
            {"id": 1, "title": "Senior Backend Engineer", "company": "Acme",
             "description": "Build distributed systems in Python."},
            {"id": 2, "title": "Platform Engineer", "company": "Globex",
             "description": "Kubernetes platform work."},
        ],
    )
    result = rr.rerank(req)
    assert len(result.scored) == 2
    assert result.scored[0].id == 1
    assert result.scored[0].score == 87
    assert "python" in result.scored[0].reason.lower()
    assert result.cost_usd > 0
    assert result.tokens_in == 1024
    assert result.tokens_out == 96


def test_reranker_retries_once_on_unparsable_output():
    fake_client = MagicMock()
    bad = _fake_message("not JSON at all", 50, 10)
    good_text = '[{"id": 1, "score": 50, "reason": "ok"}]'
    good = _fake_message(good_text, 50, 12)
    fake_client.messages.create.side_effect = [bad, good]

    rr = LLMReranker(client=fake_client, model="claude-haiku-4-5-20251001")
    req = RerankRequest(
        resume="r", prefs_summary="p",
        candidates=[{"id": 1, "title": "Eng", "company": "Acme", "description": "x"}],
    )
    result = rr.rerank(req)
    assert len(result.scored) == 1
    assert result.scored[0].score == 50
    assert fake_client.messages.create.call_count == 2


def test_reranker_raises_after_two_failed_parses():
    from shortlist.ranker.llm_rerank import LLMRerankParseError
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = [
        _fake_message("garbage 1"),
        _fake_message("garbage 2"),
    ]
    rr = LLMReranker(client=fake_client, model="claude-haiku-4-5-20251001")
    req = RerankRequest(
        resume="r", prefs_summary="p",
        candidates=[{"id": 1, "title": "Eng", "company": "Acme", "description": "x"}],
    )
    with pytest.raises(LLMRerankParseError):
        rr.rerank(req)
```

- [ ] **Step 3: Implement `shortlist/ranker/llm_rerank.py`**

```python
"""Anthropic Haiku rerank client.

Sends a batch of candidate jobs (already passed hard filter + cosine top-K)
to claude-haiku-4-5 and parses a JSON list of {id, score, reason} back.

One retry with a corrective system prompt if the first response is
unparsable. Surfaces cost + token usage so the caller can record it in
`scoring_runs`.

Pricing (USD per 1M tokens, public Anthropic pricing as of 2026-01):
  Haiku 4.5 input  : $0.80
  Haiku 4.5 output : $4.00
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

HAIKU_INPUT_PRICE_PER_MTOK = 0.80
HAIKU_OUTPUT_PRICE_PER_MTOK = 4.00


def estimate_cost(*, input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1_000_000 * HAIKU_INPUT_PRICE_PER_MTOK
        + output_tokens / 1_000_000 * HAIKU_OUTPUT_PRICE_PER_MTOK
    )


class LLMRerankParseError(RuntimeError):
    pass


@dataclass(frozen=True)
class RerankRequest:
    resume: str
    prefs_summary: str
    candidates: list[dict[str, Any]]  # each: {id, title, company, description}


@dataclass(frozen=True)
class ScoredJob:
    id: int
    score: int
    reason: str


@dataclass(frozen=True)
class RerankResult:
    scored: list[ScoredJob]
    cost_usd: float
    tokens_in: int
    tokens_out: int


_SYSTEM = (
    "You rank job postings against a candidate's resume and stated preferences. "
    "Return ONLY a JSON array. Each element: "
    '{"id": <int>, "score": 0-100 int, "reason": "<one line>"}. '
    "No prose outside the JSON. No markdown fences. "
    "Score by fit (skills + seniority + domain), not by job desirability."
)

_CORRECTIVE = (
    "Your previous response was not valid JSON. "
    "Return ONLY a JSON array of {id, score, reason}. No other text."
)


def _extract_json_array(text: str) -> list[dict[str, Any]]:
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        raise LLMRerankParseError("no JSON array found in response")
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise LLMRerankParseError(f"invalid JSON: {e}") from e
    if not isinstance(data, list):
        raise LLMRerankParseError("parsed JSON is not a list")
    return data


def _build_user_prompt(req: RerankRequest) -> str:
    lines = [
        "RESUME:", req.resume.strip(),
        "",
        "PREFERENCES:", req.prefs_summary.strip(),
        "",
        "CANDIDATES (rank these):",
    ]
    for c in req.candidates:
        lines.append(
            f"- id={c['id']} | {c['company']} — {c['title']}\n"
            f"  {c.get('description', '')[:600]}"
        )
    return "\n".join(lines)


class LLMReranker:
    def __init__(self, *, client: Any, model: str = "claude-haiku-4-5-20251001",
                 max_tokens: int = 4096):
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    def rerank(self, req: RerankRequest) -> RerankResult:
        user = _build_user_prompt(req)
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        text = msg.content[0].text
        in_tok = int(msg.usage.input_tokens)
        out_tok = int(msg.usage.output_tokens)
        try:
            parsed = _extract_json_array(text)
        except LLMRerankParseError:
            logger.warning("haiku rerank: first parse failed, retrying with corrective prompt")
            msg2 = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=_SYSTEM + "\n" + _CORRECTIVE,
                messages=[
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": _CORRECTIVE},
                ],
            )
            in_tok += int(msg2.usage.input_tokens)
            out_tok += int(msg2.usage.output_tokens)
            parsed = _extract_json_array(msg2.content[0].text)

        scored = [
            ScoredJob(
                id=int(item["id"]),
                score=max(0, min(100, int(item["score"]))),
                reason=str(item.get("reason", "")).strip()[:200],
            )
            for item in parsed
            if "id" in item and "score" in item
        ]
        return RerankResult(
            scored=scored,
            cost_usd=estimate_cost(input_tokens=in_tok, output_tokens=out_tok),
            tokens_in=in_tok,
            tokens_out=out_tok,
        )
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/unit/test_llm_rerank.py -v
ruff check . && ruff format --check . && mypy shortlist
git add shortlist/ranker/llm_rerank.py tests/unit/test_llm_rerank.py tests/fixtures/llm_responses/haiku_rerank_sample.json
git commit -m "feat(ranker): Haiku rerank client with retry + cost tracking"
```

Expected: 4 new pass + 62 prior = 66 total.

---

## Task 5: Lever source

**Files:**
- Create: `tests/fixtures/lever_acme.json`
- Create: `shortlist/sources/ats/lever.py`
- Create: `tests/integration/test_lever.py`

Lever public API: `GET https://api.lever.co/v0/postings/{site}?mode=json` returns an array (no envelope). Each posting has `id`, `text` (title), `hostedUrl`, `categories: {team, location, commitment}`, `descriptionPlain`, `createdAt` (epoch ms).

- [ ] **Step 1: Fixture `tests/fixtures/lever_acme.json`**

```json
[
  {
    "id": "lev_001",
    "text": "Senior Backend Engineer",
    "hostedUrl": "https://jobs.lever.co/acme/lev_001",
    "categories": {
      "team": "Platform",
      "location": "Remote - US",
      "commitment": "Full-time"
    },
    "descriptionPlain": "Build distributed services in Python.",
    "createdAt": 1745580000000
  },
  {
    "id": "lev_002",
    "text": "Staff Site Reliability Engineer",
    "hostedUrl": "https://jobs.lever.co/acme/lev_002",
    "categories": {
      "team": "Infrastructure",
      "location": "Atlanta, GA",
      "commitment": "Full-time"
    },
    "descriptionPlain": "Run multi-region Kubernetes.",
    "createdAt": 1745666400000
  }
]
```

- [ ] **Step 2: Failing tests `tests/integration/test_lever.py`**

```python
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx

from shortlist.models import RawJob
from shortlist.sources.ats.lever import LeverClient, LeverSource, _normalize

FIXTURES = Path(__file__).parent.parent / "fixtures"


@respx.mock
def test_lever_client_returns_postings():
    payload = json.loads((FIXTURES / "lever_acme.json").read_text())
    respx.get("https://api.lever.co/v0/postings/acme", params={"mode": "json"}).mock(
        return_value=httpx.Response(200, json=payload)
    )
    client = LeverClient()
    postings = list(client.fetch_company("acme"))
    assert len(postings) == 2
    assert postings[0]["id"] == "lev_001"


@respx.mock
def test_lever_client_404_returns_empty():
    respx.get("https://api.lever.co/v0/postings/nope", params={"mode": "json"}).mock(
        return_value=httpx.Response(404)
    )
    assert list(LeverClient().fetch_company("nope")) == []


def test_normalize_returns_rawjob():
    posting = {
        "id": "lev_001",
        "text": "Senior Backend Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/lev_001",
        "categories": {
            "team": "Platform",
            "location": "Remote - US",
            "commitment": "Full-time",
        },
        "descriptionPlain": "Build stuff in Python.",
        "createdAt": 1745580000000,
    }
    raw = _normalize(posting, company="Acme")
    assert isinstance(raw, RawJob)
    assert raw.source == "lever"
    assert raw.external_id == "lev_001"
    assert raw.title == "Senior Backend Engineer"
    assert raw.location == "Remote - US"
    assert raw.remote is True
    assert raw.posted_at == datetime.fromtimestamp(1745580000, tz=UTC)
    assert "Build stuff in Python." in (raw.description_md or "")


@respx.mock
def test_lever_source_fetch_yields_normalized():
    payload = json.loads((FIXTURES / "lever_acme.json").read_text())
    respx.get("https://api.lever.co/v0/postings/acme", params={"mode": "json"}).mock(
        return_value=httpx.Response(200, json=payload)
    )
    src = LeverSource(companies={"acme": "Acme Corp"})
    out = list(src.fetch(since=None))
    assert len(out) == 2
    assert out[0].external_id == "acme:lev_001"
    assert out[0].company == "Acme Corp"
```

- [ ] **Step 3: Implement `shortlist/sources/ats/lever.py`**

```python
"""Lever public postings client.

Endpoint:
  GET https://api.lever.co/v0/postings/{site}?mode=json

Response is a flat JSON array of posting dicts.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from shortlist.models import RawJob
from shortlist.sources.base import Source

logger = logging.getLogger(__name__)

_BASE = "https://api.lever.co/v0/postings"


def _is_remote(loc: str) -> bool:
    return "remote" in loc.lower()


def _normalize(posting: dict[str, Any], *, company: str) -> RawJob:
    cats = posting.get("categories") or {}
    location = cats.get("location") or ""
    return RawJob(
        source="lever",
        external_id=str(posting["id"]),
        company=company,
        title=posting["text"],
        url=posting["hostedUrl"],
        posted_at=datetime.fromtimestamp(int(posting["createdAt"]) / 1000, tz=UTC),
        location=location or None,
        remote=_is_remote(location),
        description_md=(posting.get("descriptionPlain") or "").strip() or None,
    )


class LeverClient:
    def __init__(self, *, timeout: float = 30.0):
        self._client = httpx.Client(timeout=timeout)

    def __del__(self) -> None:
        from contextlib import suppress
        with suppress(Exception):
            self._client.close()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=8),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _get(self, url: str, params: dict[str, str]) -> httpx.Response:
        resp = self._client.get(url, params=params)
        if resp.status_code >= 500:
            resp.raise_for_status()
        return resp

    def fetch_company(self, site: str) -> Iterator[dict[str, Any]]:
        try:
            resp = self._get(f"{_BASE}/{site}", {"mode": "json"})
        except httpx.HTTPStatusError as e:
            logger.warning("lever fetch failed for %s: %s", site, e)
            return
        if resp.status_code == 404:
            return
        resp.raise_for_status()
        yield from resp.json()


class LeverSource(Source):
    name: ClassVar[str] = "lever"

    def __init__(self, *, companies: dict[str, str], client: LeverClient | None = None):
        self._companies = companies
        self._client = client or LeverClient()

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:  # noqa: ARG002
        for site, display in self._companies.items():
            for raw in self._client.fetch_company(site):
                normalized = _normalize(raw, company=display)
                yield normalized.model_copy(
                    update={"external_id": f"{site}:{normalized.external_id}"}
                )
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/integration/test_lever.py -v
ruff check . && ruff format --check . && mypy shortlist
git add shortlist/sources/ats/lever.py tests/integration/test_lever.py tests/fixtures/lever_acme.json
git commit -m "feat(sources/lever): Lever public postings client"
```

Expected: 4 new pass + 66 prior = 70 total.

---

## Task 6: Ashby source

**Files:**
- Create: `tests/fixtures/ashby_acme.json`
- Create: `shortlist/sources/ats/ashby.py`
- Create: `tests/integration/test_ashby.py`

Ashby public API: `GET https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true` returns `{jobs: [...]}`.

- [ ] **Step 1: Fixture `tests/fixtures/ashby_acme.json`**

```json
{
  "apiVersion": "1",
  "jobs": [
    {
      "id": "ash-uuid-1",
      "title": "Senior Backend Engineer",
      "department": "Engineering",
      "team": "Platform",
      "location": "Remote",
      "employmentType": "FullTime",
      "descriptionHtml": "<p>Build distributed systems.</p>",
      "jobUrl": "https://jobs.ashbyhq.com/acme/ash-uuid-1",
      "publishedAt": "2026-04-25T13:00:00.000Z",
      "compensationTierSummary": "$200k–$240k USD"
    },
    {
      "id": "ash-uuid-2",
      "title": "Staff Engineer",
      "department": "Engineering",
      "team": "Core",
      "location": "Atlanta",
      "employmentType": "FullTime",
      "descriptionHtml": "<p>Lead architecture.</p>",
      "jobUrl": "https://jobs.ashbyhq.com/acme/ash-uuid-2",
      "publishedAt": "2026-04-26T14:30:00.000Z",
      "compensationTierSummary": null
    }
  ]
}
```

- [ ] **Step 2: Failing tests `tests/integration/test_ashby.py`**

```python
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx

from shortlist.models import RawJob
from shortlist.sources.ats.ashby import AshbyClient, AshbySource, _normalize

FIXTURES = Path(__file__).parent.parent / "fixtures"


@respx.mock
def test_ashby_client_returns_jobs():
    payload = json.loads((FIXTURES / "ashby_acme.json").read_text())
    respx.get(
        re.compile(r"^https://api\.ashbyhq\.com/posting-api/job-board/acme")
    ).mock(return_value=httpx.Response(200, json=payload))
    out = list(AshbyClient().fetch_company("acme"))
    assert len(out) == 2
    assert out[0]["id"] == "ash-uuid-1"


def test_normalize_handles_html_and_compensation():
    job = {
        "id": "ash-uuid-1",
        "title": "Senior Backend Engineer",
        "location": "Remote",
        "descriptionHtml": "<p>Build <b>distributed</b> systems.</p>",
        "jobUrl": "https://jobs.ashbyhq.com/acme/ash-uuid-1",
        "publishedAt": "2026-04-25T13:00:00.000Z",
        "compensationTierSummary": "$200k–$240k USD",
    }
    raw = _normalize(job, company="Acme")
    assert isinstance(raw, RawJob)
    assert raw.source == "ashby"
    assert raw.external_id == "ash-uuid-1"
    assert raw.remote is True
    assert raw.posted_at == datetime(2026, 4, 25, 13, 0, tzinfo=UTC)
    assert "<" not in (raw.description_md or "")
    assert "distributed" in (raw.description_md or "")
    assert raw.comp_min == 200000
    assert raw.comp_max == 240000


def test_normalize_handles_missing_comp():
    job = {
        "id": "ash-uuid-2",
        "title": "Eng",
        "location": "Atlanta",
        "descriptionHtml": "<p>Stuff.</p>",
        "jobUrl": "https://jobs.ashbyhq.com/acme/ash-uuid-2",
        "publishedAt": "2026-04-26T14:30:00.000Z",
        "compensationTierSummary": None,
    }
    raw = _normalize(job, company="Acme")
    assert raw.comp_min is None
    assert raw.comp_max is None
    assert raw.remote is False


@respx.mock
def test_ashby_source_yields_namespaced_external_id():
    payload = json.loads((FIXTURES / "ashby_acme.json").read_text())
    respx.get(
        re.compile(r"^https://api\.ashbyhq\.com/posting-api/job-board/acme")
    ).mock(return_value=httpx.Response(200, json=payload))
    src = AshbySource(companies={"acme": "Acme Corp"})
    out = list(src.fetch(since=None))
    assert out[0].external_id == "acme:ash-uuid-1"
```

- [ ] **Step 3: Implement `shortlist/sources/ats/ashby.py`**

```python
"""Ashby public job-board API client.

Endpoint:
  GET https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true
"""
from __future__ import annotations

import html
import logging
import re
from collections.abc import Iterator
from datetime import datetime
from typing import Any, ClassVar

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from shortlist.models import RawJob
from shortlist.sources.base import Source

logger = logging.getLogger(__name__)

_BASE = "https://api.ashbyhq.com/posting-api/job-board"
_TAG_RE = re.compile(r"<[^>]+>")
_COMP_RE = re.compile(r"\$([\d.]+)\s*([km])?\s*[–-]\s*\$?([\d.]+)\s*([km])?", re.IGNORECASE)


def _strip_html(s: str) -> str:
    return _TAG_RE.sub("", html.unescape(s)).strip()


def _is_remote(loc: str) -> bool:
    return "remote" in loc.lower()


def _parse_money(num: str, unit: str | None) -> int:
    v = float(num)
    if unit and unit.lower() == "k":
        v *= 1000
    elif unit and unit.lower() == "m":
        v *= 1_000_000
    return int(v)


def _parse_comp(summary: str | None) -> tuple[int | None, int | None]:
    if not summary:
        return None, None
    m = _COMP_RE.search(summary)
    if not m:
        return None, None
    return _parse_money(m.group(1), m.group(2)), _parse_money(m.group(3), m.group(4))


def _normalize(job: dict[str, Any], *, company: str) -> RawJob:
    location = job.get("location") or ""
    comp_min, comp_max = _parse_comp(job.get("compensationTierSummary"))
    return RawJob(
        source="ashby",
        external_id=str(job["id"]),
        company=company,
        title=job["title"],
        url=job["jobUrl"],
        posted_at=datetime.fromisoformat(job["publishedAt"].replace("Z", "+00:00")),
        location=location or None,
        remote=_is_remote(location),
        comp_min=comp_min,
        comp_max=comp_max,
        description_md=_strip_html(job.get("descriptionHtml") or "") or None,
    )


class AshbyClient:
    def __init__(self, *, timeout: float = 30.0):
        self._client = httpx.Client(timeout=timeout)

    def __del__(self) -> None:
        from contextlib import suppress
        with suppress(Exception):
            self._client.close()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=8),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _get(self, url: str, params: dict[str, str]) -> httpx.Response:
        resp = self._client.get(url, params=params)
        if resp.status_code >= 500:
            resp.raise_for_status()
        return resp

    def fetch_company(self, board: str) -> Iterator[dict[str, Any]]:
        try:
            resp = self._get(f"{_BASE}/{board}", {"includeCompensation": "true"})
        except httpx.HTTPStatusError as e:
            logger.warning("ashby fetch failed for %s: %s", board, e)
            return
        if resp.status_code == 404:
            return
        resp.raise_for_status()
        yield from resp.json().get("jobs", [])


class AshbySource(Source):
    name: ClassVar[str] = "ashby"

    def __init__(self, *, companies: dict[str, str], client: AshbyClient | None = None):
        self._companies = companies
        self._client = client or AshbyClient()

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:  # noqa: ARG002
        for board, display in self._companies.items():
            for raw in self._client.fetch_company(board):
                normalized = _normalize(raw, company=display)
                yield normalized.model_copy(
                    update={"external_id": f"{board}:{normalized.external_id}"}
                )
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/integration/test_ashby.py -v
ruff check . && ruff format --check . && mypy shortlist
git add shortlist/sources/ats/ashby.py tests/integration/test_ashby.py tests/fixtures/ashby_acme.json
git commit -m "feat(sources/ashby): Ashby public job-board client with comp parsing"
```

Expected: 4 new pass + 70 prior = 74 total.

---

## Task 7: Workable source

**Files:**
- Create: `tests/fixtures/workable_acme.json`
- Create: `shortlist/sources/ats/workable.py`
- Create: `tests/integration/test_workable.py`

Workable public API: `GET https://apply.workable.com/api/v1/widget/accounts/{subdomain}?details=true` returns `{name, jobs: [{shortcode, title, location: {city, country, region, location_str}, application_url, description, requirements, posted_date, ...}]}`.

- [ ] **Step 1: Fixture `tests/fixtures/workable_acme.json`**

```json
{
  "name": "Acme Corp",
  "jobs": [
    {
      "shortcode": "WRK001",
      "title": "Senior Backend Engineer",
      "full_title": "Senior Backend Engineer",
      "location": {
        "city": "Remote",
        "country": "United States",
        "region": null,
        "location_str": "Remote, United States"
      },
      "application_url": "https://apply.workable.com/acme/j/WRK001/",
      "description": "<p>Build services in Python.</p>",
      "requirements": "<p>5+ years backend.</p>",
      "posted_date": "2026-04-25"
    },
    {
      "shortcode": "WRK002",
      "title": "Staff Engineer",
      "full_title": "Staff Engineer",
      "location": {
        "city": "Atlanta",
        "country": "United States",
        "region": "GA",
        "location_str": "Atlanta, GA, United States"
      },
      "application_url": "https://apply.workable.com/acme/j/WRK002/",
      "description": "<p>Architecture leadership.</p>",
      "requirements": null,
      "posted_date": "2026-04-26"
    }
  ]
}
```

- [ ] **Step 2: Failing tests `tests/integration/test_workable.py`**

```python
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx

from shortlist.models import RawJob
from shortlist.sources.ats.workable import WorkableClient, WorkableSource, _normalize

FIXTURES = Path(__file__).parent.parent / "fixtures"


@respx.mock
def test_workable_client_returns_jobs():
    payload = json.loads((FIXTURES / "workable_acme.json").read_text())
    respx.get(
        re.compile(r"^https://apply\.workable\.com/api/v1/widget/accounts/acme")
    ).mock(return_value=httpx.Response(200, json=payload))
    out = list(WorkableClient().fetch_company("acme"))
    assert len(out) == 2
    assert out[0]["shortcode"] == "WRK001"


def test_normalize_combines_description_and_requirements():
    job = {
        "shortcode": "WRK001",
        "title": "Senior Backend Engineer",
        "location": {"city": "Remote", "country": "United States",
                     "location_str": "Remote, United States"},
        "application_url": "https://apply.workable.com/acme/j/WRK001/",
        "description": "<p>Build services.</p>",
        "requirements": "<p>5+ yrs.</p>",
        "posted_date": "2026-04-25",
    }
    raw = _normalize(job, company="Acme")
    assert isinstance(raw, RawJob)
    assert raw.source == "workable"
    assert raw.external_id == "WRK001"
    assert raw.location == "Remote, United States"
    assert raw.remote is True
    assert raw.posted_at == datetime(2026, 4, 25, 0, 0, tzinfo=UTC)
    assert "Build services." in (raw.description_md or "")
    assert "5+ yrs." in (raw.description_md or "")


def test_normalize_handles_missing_requirements():
    job = {
        "shortcode": "WRK002",
        "title": "Staff Engineer",
        "location": {"location_str": "Atlanta, GA, United States"},
        "application_url": "https://apply.workable.com/acme/j/WRK002/",
        "description": "<p>Lead.</p>",
        "requirements": None,
        "posted_date": "2026-04-26",
    }
    raw = _normalize(job, company="Acme")
    assert raw.remote is False
    assert "Lead." in (raw.description_md or "")


@respx.mock
def test_workable_source_namespaces_external_id():
    payload = json.loads((FIXTURES / "workable_acme.json").read_text())
    respx.get(
        re.compile(r"^https://apply\.workable\.com/api/v1/widget/accounts/acme")
    ).mock(return_value=httpx.Response(200, json=payload))
    src = WorkableSource(companies={"acme": "Acme Corp"})
    out = list(src.fetch(since=None))
    assert out[0].external_id == "acme:WRK001"
```

- [ ] **Step 3: Implement `shortlist/sources/ats/workable.py`**

```python
"""Workable public widget client.

Endpoint:
  GET https://apply.workable.com/api/v1/widget/accounts/{subdomain}?details=true
"""
from __future__ import annotations

import html
import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from shortlist.models import RawJob
from shortlist.sources.base import Source

logger = logging.getLogger(__name__)

_BASE = "https://apply.workable.com/api/v1/widget/accounts"
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return _TAG_RE.sub("", html.unescape(s)).strip()


def _is_remote(loc: str) -> bool:
    return "remote" in loc.lower()


def _normalize(job: dict[str, Any], *, company: str) -> RawJob:
    loc_obj = job.get("location") or {}
    location = loc_obj.get("location_str") or ""
    desc = _strip_html(job.get("description") or "")
    reqs = _strip_html(job.get("requirements") or "")
    description_md = "\n\n".join(p for p in (desc, reqs) if p) or None
    return RawJob(
        source="workable",
        external_id=str(job["shortcode"]),
        company=company,
        title=job["title"],
        url=job["application_url"],
        posted_at=datetime.fromisoformat(job["posted_date"]).replace(tzinfo=UTC),
        location=location or None,
        remote=_is_remote(location),
        description_md=description_md,
    )


class WorkableClient:
    def __init__(self, *, timeout: float = 30.0):
        self._client = httpx.Client(timeout=timeout)

    def __del__(self) -> None:
        from contextlib import suppress
        with suppress(Exception):
            self._client.close()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=8),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _get(self, url: str, params: dict[str, str]) -> httpx.Response:
        resp = self._client.get(url, params=params)
        if resp.status_code >= 500:
            resp.raise_for_status()
        return resp

    def fetch_company(self, subdomain: str) -> Iterator[dict[str, Any]]:
        try:
            resp = self._get(f"{_BASE}/{subdomain}", {"details": "true"})
        except httpx.HTTPStatusError as e:
            logger.warning("workable fetch failed for %s: %s", subdomain, e)
            return
        if resp.status_code == 404:
            return
        resp.raise_for_status()
        yield from resp.json().get("jobs", [])


class WorkableSource(Source):
    name: ClassVar[str] = "workable"

    def __init__(self, *, companies: dict[str, str], client: WorkableClient | None = None):
        self._companies = companies
        self._client = client or WorkableClient()

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:  # noqa: ARG002
        for sub, display in self._companies.items():
            for raw in self._client.fetch_company(sub):
                normalized = _normalize(raw, company=display)
                yield normalized.model_copy(
                    update={"external_id": f"{sub}:{normalized.external_id}"}
                )
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/integration/test_workable.py -v
ruff check . && ruff format --check . && mypy shortlist
git add shortlist/sources/ats/workable.py tests/integration/test_workable.py tests/fixtures/workable_acme.json
git commit -m "feat(sources/workable): Workable widget client"
```

Expected: 4 new pass + 74 prior = 78 total.

---

## Task 8: SmartRecruiters source

**Files:**
- Create: `tests/fixtures/smartrecruiters_acme.json`
- Create: `shortlist/sources/ats/smartrecruiters.py`
- Create: `tests/integration/test_smartrecruiters.py`

SmartRecruiters public postings API: `GET https://api.smartrecruiters.com/v1/companies/{identifier}/postings?limit=100&offset={n}` returns `{offset, limit, totalFound, content: [{id, name, releasedDate (ISO), location: {city, region, country, remote, fullLocation}, jobAd: {sections: {jobDescription: {text}, qualifications: {text}, ...}}, applyUrl, ...}]}`. Pagination via `offset`.

- [ ] **Step 1: Fixture `tests/fixtures/smartrecruiters_acme.json`**

```json
{
  "offset": 0,
  "limit": 100,
  "totalFound": 2,
  "content": [
    {
      "id": "sr_001",
      "name": "Senior Backend Engineer",
      "uuid": "sr-uuid-1",
      "releasedDate": "2026-04-25T09:00:00.000Z",
      "location": {
        "city": "Remote",
        "region": "US",
        "country": "us",
        "remote": true,
        "fullLocation": "Remote, US"
      },
      "jobAd": {
        "sections": {
          "jobDescription": {"text": "<p>Build services.</p>"},
          "qualifications": {"text": "<p>5+ years.</p>"}
        }
      },
      "applyUrl": "https://jobs.smartrecruiters.com/Acme/sr-uuid-1"
    },
    {
      "id": "sr_002",
      "name": "Staff Engineer",
      "uuid": "sr-uuid-2",
      "releasedDate": "2026-04-26T10:30:00.000Z",
      "location": {
        "city": "Atlanta",
        "region": "GA",
        "country": "us",
        "remote": false,
        "fullLocation": "Atlanta, GA, US"
      },
      "jobAd": {
        "sections": {
          "jobDescription": {"text": "<p>Architecture.</p>"}
        }
      },
      "applyUrl": "https://jobs.smartrecruiters.com/Acme/sr-uuid-2"
    }
  ]
}
```

- [ ] **Step 2: Failing tests `tests/integration/test_smartrecruiters.py`**

```python
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx

from shortlist.models import RawJob
from shortlist.sources.ats.smartrecruiters import (
    SmartRecruitersClient,
    SmartRecruitersSource,
    _normalize,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


@respx.mock
def test_client_returns_postings():
    payload = json.loads((FIXTURES / "smartrecruiters_acme.json").read_text())
    respx.get(
        re.compile(r"^https://api\.smartrecruiters\.com/v1/companies/Acme/postings")
    ).mock(return_value=httpx.Response(200, json=payload))
    out = list(SmartRecruitersClient().fetch_company("Acme"))
    assert len(out) == 2
    assert out[0]["id"] == "sr_001"


@respx.mock
def test_client_paginates():
    page1 = {"offset": 0, "limit": 1, "totalFound": 2, "content": [
        {"id": "a", "name": "A", "releasedDate": "2026-04-25T00:00:00.000Z",
         "location": {"fullLocation": "Remote", "remote": True},
         "jobAd": {"sections": {}}, "applyUrl": "https://x/a"}
    ]}
    page2 = {"offset": 1, "limit": 1, "totalFound": 2, "content": [
        {"id": "b", "name": "B", "releasedDate": "2026-04-26T00:00:00.000Z",
         "location": {"fullLocation": "Atlanta", "remote": False},
         "jobAd": {"sections": {}}, "applyUrl": "https://x/b"}
    ]}
    respx.get(
        "https://api.smartrecruiters.com/v1/companies/Acme/postings",
        params={"limit": "1", "offset": "0"},
    ).mock(return_value=httpx.Response(200, json=page1))
    respx.get(
        "https://api.smartrecruiters.com/v1/companies/Acme/postings",
        params={"limit": "1", "offset": "1"},
    ).mock(return_value=httpx.Response(200, json=page2))

    client = SmartRecruitersClient(page_size=1)
    out = list(client.fetch_company("Acme"))
    assert [j["id"] for j in out] == ["a", "b"]


def test_normalize_concatenates_sections():
    job = {
        "id": "sr_001",
        "name": "Senior Backend Engineer",
        "releasedDate": "2026-04-25T09:00:00.000Z",
        "location": {"fullLocation": "Remote, US", "remote": True},
        "jobAd": {"sections": {
            "jobDescription": {"text": "<p>Build.</p>"},
            "qualifications": {"text": "<p>5y.</p>"},
        }},
        "applyUrl": "https://jobs.smartrecruiters.com/Acme/sr-uuid-1",
    }
    raw = _normalize(job, company="Acme")
    assert isinstance(raw, RawJob)
    assert raw.source == "smartrecruiters"
    assert raw.external_id == "sr_001"
    assert raw.remote is True
    assert raw.posted_at == datetime(2026, 4, 25, 9, 0, tzinfo=UTC)
    assert "Build." in (raw.description_md or "")
    assert "5y." in (raw.description_md or "")


@respx.mock
def test_source_namespaces_external_id():
    payload = json.loads((FIXTURES / "smartrecruiters_acme.json").read_text())
    respx.get(
        re.compile(r"^https://api\.smartrecruiters\.com/v1/companies/Acme/postings")
    ).mock(return_value=httpx.Response(200, json=payload))
    src = SmartRecruitersSource(companies={"Acme": "Acme Corp"})
    out = list(src.fetch(since=None))
    assert out[0].external_id == "Acme:sr_001"
```

- [ ] **Step 3: Implement `shortlist/sources/ats/smartrecruiters.py`**

```python
"""SmartRecruiters public postings client.

Endpoint:
  GET https://api.smartrecruiters.com/v1/companies/{identifier}/postings
        ?limit={page_size}&offset={n}

Returns {offset, limit, totalFound, content: [posting...]}. Paginate by
offset until len(content) < limit.
"""
from __future__ import annotations

import html
import logging
import re
from collections.abc import Iterator
from datetime import datetime
from typing import Any, ClassVar

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from shortlist.models import RawJob
from shortlist.sources.base import Source

logger = logging.getLogger(__name__)

_BASE = "https://api.smartrecruiters.com/v1/companies"
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return _TAG_RE.sub("", html.unescape(s)).strip()


def _normalize(job: dict[str, Any], *, company: str) -> RawJob:
    loc = job.get("location") or {}
    location = loc.get("fullLocation") or loc.get("city") or ""
    sections = (job.get("jobAd") or {}).get("sections") or {}
    parts = []
    for key in ("jobDescription", "qualifications", "additionalInformation"):
        text = ((sections.get(key) or {}).get("text") or "").strip()
        if text:
            parts.append(_strip_html(text))
    description_md = "\n\n".join(parts) or None
    return RawJob(
        source="smartrecruiters",
        external_id=str(job["id"]),
        company=company,
        title=job["name"],
        url=job["applyUrl"],
        posted_at=datetime.fromisoformat(job["releasedDate"].replace("Z", "+00:00")),
        location=location or None,
        remote=bool(loc.get("remote")),
        description_md=description_md,
    )


class SmartRecruitersClient:
    def __init__(self, *, timeout: float = 30.0, page_size: int = 100):
        self._client = httpx.Client(timeout=timeout)
        self._page_size = page_size

    def __del__(self) -> None:
        from contextlib import suppress
        with suppress(Exception):
            self._client.close()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=8),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _get(self, url: str, params: dict[str, str]) -> httpx.Response:
        resp = self._client.get(url, params=params)
        if resp.status_code >= 500:
            resp.raise_for_status()
        return resp

    def fetch_company(self, identifier: str) -> Iterator[dict[str, Any]]:
        offset = 0
        while True:
            try:
                resp = self._get(
                    f"{_BASE}/{identifier}/postings",
                    {"limit": str(self._page_size), "offset": str(offset)},
                )
            except httpx.HTTPStatusError as e:
                logger.warning("smartrecruiters fetch failed for %s: %s", identifier, e)
                return
            if resp.status_code == 404:
                return
            resp.raise_for_status()
            payload = resp.json()
            content = payload.get("content", [])
            if not content:
                return
            yield from content
            if len(content) < self._page_size:
                return
            offset += self._page_size


class SmartRecruitersSource(Source):
    name: ClassVar[str] = "smartrecruiters"

    def __init__(self, *, companies: dict[str, str],
                 client: SmartRecruitersClient | None = None):
        self._companies = companies
        self._client = client or SmartRecruitersClient()

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:  # noqa: ARG002
        for ident, display in self._companies.items():
            for raw in self._client.fetch_company(ident):
                normalized = _normalize(raw, company=display)
                yield normalized.model_copy(
                    update={"external_id": f"{ident}:{normalized.external_id}"}
                )
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/integration/test_smartrecruiters.py -v
ruff check . && ruff format --check . && mypy shortlist
git add shortlist/sources/ats/smartrecruiters.py tests/integration/test_smartrecruiters.py tests/fixtures/smartrecruiters_acme.json
git commit -m "feat(sources/smartrecruiters): SR postings client with pagination"
```

Expected: 4 new pass + 78 prior = 82 total.

---

## Task 9: Per-source company lists in `Prefs`

**Files:**
- Modify: `shortlist/config.py`
- Modify: `tests/fixtures/prefs_default.yaml`
- Modify: `tests/unit/test_config.py`
- Modify: `shortlist/cli.py` (`_DEFAULT_PREFS`)

- [ ] **Step 1: Update fixture YAML**

`tests/fixtures/prefs_default.yaml` — append after `greenhouse_companies`:

```yaml
lever_companies:
  - acme
ashby_companies:
  - acme
workable_companies:
  - acme
smartrecruiters_companies:
  - Acme
```

- [ ] **Step 2: Append failing test**

```python
def test_load_prefs_includes_all_ats_company_lists():
    prefs = load_prefs(FIXTURES / "prefs_default.yaml")
    assert prefs.lever_companies == ["acme"]
    assert prefs.ashby_companies == ["acme"]
    assert prefs.workable_companies == ["acme"]
    assert prefs.smartrecruiters_companies == ["Acme"]


def test_prefs_defaults_to_empty_lists_when_omitted():
    p = Prefs.model_validate({
        "titles": ["Eng"], "locations": ["Remote"], "remote_ok": True,
        "comp_floor_usd": 100000, "exclude_keywords": [], "seniority": [],
        "greenhouse_companies": [],
    })
    assert p.lever_companies == []
    assert p.ashby_companies == []
    assert p.workable_companies == []
    assert p.smartrecruiters_companies == []
```

- [ ] **Step 3: Modify `Prefs` in `shortlist/config.py`**

Append fields after `greenhouse_companies`:

```python
    lever_companies: list[str] = Field(default_factory=list)
    ashby_companies: list[str] = Field(default_factory=list)
    workable_companies: list[str] = Field(default_factory=list)
    smartrecruiters_companies: list[str] = Field(default_factory=list)
```

Extend the `_strip` validator argument list:

```python
    @field_validator(
        "titles", "locations", "exclude_keywords", "seniority",
        "greenhouse_companies", "lever_companies", "ashby_companies",
        "workable_companies", "smartrecruiters_companies",
    )
```

- [ ] **Step 4: Update `_DEFAULT_PREFS` in `shortlist/cli.py`**

Append after `greenhouse_companies: []`:

```yaml
lever_companies: []
ashby_companies: []
workable_companies: []
smartrecruiters_companies: []
```

- [ ] **Step 5: Run + commit**

```bash
pytest -q
ruff check . && ruff format --check . && mypy shortlist
git add shortlist/config.py shortlist/cli.py tests/fixtures/prefs_default.yaml tests/unit/test_config.py
git commit -m "feat(config): per-source company lists in Prefs"
```

Expected: 2 new pass + 82 prior = 84 total.

---

## Task 10: CLI `fetch` enumerates all 5 ATS sources

**Files:**
- Modify: `shortlist/cli.py`
- Modify: `tests/integration/test_cli.py`

- [ ] **Step 1: Append failing test**

```python
@respx.mock
def test_fetch_iterates_all_configured_sources(env):
    cfg, data = env
    runner.invoke(app, ["config", "init"])
    prefs_yaml = (cfg / "prefs.yaml").read_text()
    prefs_yaml = prefs_yaml.replace(
        "greenhouse_companies: []", "greenhouse_companies:\n  - acme",
    ).replace(
        "lever_companies: []", "lever_companies:\n  - acme",
    ).replace(
        "ashby_companies: []", "ashby_companies:\n  - acme",
    )
    (cfg / "prefs.yaml").write_text(prefs_yaml)
    runner.invoke(app, ["db", "init"])

    gh = json.loads((FIXTURES / "greenhouse_acme_page1.json").read_text())
    lever = json.loads((FIXTURES / "lever_acme.json").read_text())
    ashby = json.loads((FIXTURES / "ashby_acme.json").read_text())
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        params={"content": "true"},
    ).mock(return_value=httpx.Response(200, json=gh))
    respx.get(
        "https://api.lever.co/v0/postings/acme",
        params={"mode": "json"},
    ).mock(return_value=httpx.Response(200, json=lever))
    respx.get(
        re.compile(r"^https://api\.ashbyhq\.com/posting-api/job-board/acme")
    ).mock(return_value=httpx.Response(200, json=ashby))

    result = runner.invoke(app, ["fetch"])
    assert result.exit_code == 0, result.output
    # 2 GH + 2 Lever + 2 Ashby = 6
    assert "fetched 6 jobs" in result.output.lower()
```

(Add `import re` to the test file imports if missing.)

- [ ] **Step 2: Refactor `fetch` in `shortlist/cli.py`**

Replace the existing `fetch` body with a source-loop:

```python
from shortlist.sources.ats.ashby import AshbySource
from shortlist.sources.ats.greenhouse import GreenhouseSource
from shortlist.sources.ats.lever import LeverSource
from shortlist.sources.ats.smartrecruiters import SmartRecruitersSource
from shortlist.sources.ats.workable import WorkableSource


def _build_sources(prefs):  # type: ignore[no-untyped-def]
    sources = []
    if prefs.greenhouse_companies:
        sources.append(GreenhouseSource(
            companies={t: t.title() for t in prefs.greenhouse_companies}
        ))
    if prefs.lever_companies:
        sources.append(LeverSource(
            companies={t: t.title() for t in prefs.lever_companies}
        ))
    if prefs.ashby_companies:
        sources.append(AshbySource(
            companies={t: t.title() for t in prefs.ashby_companies}
        ))
    if prefs.workable_companies:
        sources.append(WorkableSource(
            companies={t: t.title() for t in prefs.workable_companies}
        ))
    if prefs.smartrecruiters_companies:
        sources.append(SmartRecruitersSource(
            companies={t: t for t in prefs.smartrecruiters_companies}  # SR uses identifier verbatim
        ))
    return sources


@app.command("fetch")
def fetch() -> None:
    """Pull jobs from all enabled sources."""
    if not paths.prefs_path().exists():
        console.print("[red]error[/red] run `shortlist config init` first")
        raise typer.Exit(code=2)
    if not paths.db_path().exists():
        console.print("[red]error[/red] run `shortlist db init` first")
        raise typer.Exit(code=2)

    prefs = load_prefs(paths.prefs_path())
    db = paths.db_path()

    total = 0
    for src in _build_sources(prefs):
        try:
            for raw in src.fetch(since=store_db.source_last_fetched(db, src.name)):
                store_db.upsert_job(db, raw)
                total += 1
            store_db.mark_source_fetched(db, src.name, datetime.now(timezone.utc))
        except Exception as e:  # noqa: BLE001 — surface and continue
            console.print(f"[yellow]{src.name} error:[/yellow] {e}")

    console.print(f"fetched {total} jobs")
```

- [ ] **Step 3: Run + commit**

```bash
pytest -q
ruff check . && ruff format --check . && mypy shortlist
git add shortlist/cli.py tests/integration/test_cli.py
git commit -m "feat(cli): fetch iterates Greenhouse + Lever + Ashby + Workable + SR"
```

Expected: 1 new pass + 84 prior = 85 total.

---

## Task 11: Pipeline orchestrator + new `rank` command

**Files:**
- Create: `shortlist/ranker/pipeline.py`
- Create: `tests/integration/test_pipeline.py`
- Modify: `shortlist/cli.py` (replace `rank`)
- Modify: `tests/integration/test_cli.py` (replace placeholder rank test)

- [ ] **Step 1: Write `pipeline.py`**

```python
"""End-to-end ranking pipeline.

Stage 1: hard filter — drop jobs that obviously don't match prefs.
Stage 2: cosine pre-rank — embed surviving jobs, take top-K by sim to resume.
Stage 3: Haiku rerank — let an LLM produce final 0–100 + one-line reason for top-K.
Filtered-out jobs get score 0 + reason "filtered".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shortlist.config import Prefs
from shortlist.models import Job
from shortlist.ranker.embeddings import EmbeddingService, embed_resume_cached
from shortlist.ranker.hard_filter import passes
from shortlist.ranker.llm_rerank import (
    LLMReranker,
    LLMRerankParseError,
    RerankRequest,
    RerankResult,
)
from shortlist.store import db as store_db

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineSummary:
    filtered: int
    cosine_top_k: int
    llm_scored: int
    cost_usd: float


def _prefs_summary(prefs: Prefs) -> str:
    return (
        f"titles: {', '.join(prefs.titles)}\n"
        f"seniority: {', '.join(prefs.seniority)}\n"
        f"locations: {', '.join(prefs.locations)}\n"
        f"remote_ok: {prefs.remote_ok}\n"
        f"comp_floor_usd: {prefs.comp_floor_usd}\n"
        f"exclude: {', '.join(prefs.exclude_keywords)}"
    )


def _candidates_for_llm(jobs: list[Job]) -> list[dict[str, Any]]:
    return [
        {"id": j.id, "title": j.title, "company": j.company,
         "description": (j.description_md or "")[:1000]}
        for j in jobs
    ]


def run_pipeline(
    db_path: Path,
    *,
    prefs: Prefs,
    resume_path: Path,
    embedder: EmbeddingService,
    reranker: LLMReranker | None,
    top_k: int = 30,
) -> PipelineSummary:
    """Score every job in the store. Returns a summary."""
    all_jobs = store_db.list_jobs(db_path)

    # Stage 1: hard filter.
    filtered_out: list[Job] = []
    survivors: list[Job] = []
    for job in all_jobs:
        if passes(job, prefs):
            survivors.append(job)
        else:
            filtered_out.append(job)
            store_db.update_score(
                db_path, job.id, score=0, reason="filtered out", model="hard_filter"
            )

    if not survivors:
        return PipelineSummary(len(filtered_out), 0, 0, 0.0)

    # Stage 2: embed survivors and pick top-K against resume.
    resume_vec = embed_resume_cached(db_path, resume_path, service=embedder)
    for job in survivors:
        if store_db.get_embedding(db_path, job.id) is None:
            text = f"{job.title}\n\n{job.description_md or ''}"
            store_db.upsert_embedding(db_path, job.id, embedder.encode(text))

    top = store_db.cosine_top_k(db_path, resume_vec, k=top_k)
    top_ids = {jid for (jid, _d) in top}
    top_jobs = [j for j in survivors if j.id in top_ids]

    # Survivors not in top-K get a placeholder score (passed filter, mid-band).
    for j in survivors:
        if j.id not in top_ids:
            store_db.update_score(
                db_path, j.id, score=40,
                reason="passed filter, below cosine top-K", model="cosine_only",
            )

    # Stage 3: LLM rerank (if reranker provided).
    cost = 0.0
    llm_scored = 0
    tokens_in = 0
    tokens_out = 0
    if reranker is not None and top_jobs:
        req = RerankRequest(
            resume=resume_path.read_text(),
            prefs_summary=_prefs_summary(prefs),
            candidates=_candidates_for_llm(top_jobs),
        )
        try:
            result: RerankResult = reranker.rerank(req)
            cost = result.cost_usd
            llm_scored = len(result.scored)
            tokens_in = result.tokens_in
            tokens_out = result.tokens_out
            id_to_score = {s.id: s for s in result.scored}
            for j in top_jobs:
                s = id_to_score.get(j.id)
                if s is None:
                    store_db.update_score(
                        db_path, j.id, score=50,
                        reason="LLM omitted from result", model="cosine_then_llm",
                    )
                else:
                    store_db.update_score(
                        db_path, j.id, score=s.score, reason=s.reason,
                        model="claude-haiku-4-5",
                    )
        except LLMRerankParseError as e:
            logger.warning("LLM rerank failed: %s — falling back to cosine scores", e)
            for j in top_jobs:
                store_db.update_score(
                    db_path, j.id, score=70,
                    reason="cosine top-K (LLM fallback)", model="cosine_only",
                )
    else:
        # No reranker — give top-K cosine score 70 placeholder.
        for j in top_jobs:
            store_db.update_score(
                db_path, j.id, score=70,
                reason="cosine top-K (no LLM)", model="cosine_only",
            )

    # Record the run.
    with store_db.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO scoring_runs
                (started_at, finished_at, model, job_count, cost_usd, tokens_in, tokens_out)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                store_db._utc_iso(datetime.now(UTC)),
                store_db._utc_iso(datetime.now(UTC)),
                "claude-haiku-4-5" if reranker else "cosine_only",
                len(survivors),
                cost,
                tokens_in,
                tokens_out,
            ),
        )

    return PipelineSummary(len(filtered_out), len(top_jobs), llm_scored, cost)
```

- [ ] **Step 2: Write integration test `tests/integration/test_pipeline.py`**

```python
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from shortlist.config import Prefs
from shortlist.models import RawJob
from shortlist.ranker.embeddings import EmbeddingService
from shortlist.ranker.llm_rerank import LLMReranker
from shortlist.ranker.pipeline import run_pipeline
from shortlist.store.db import list_jobs, migrate, upsert_job


@pytest.fixture
def fake_embedder():
    m = MagicMock()
    def _encode(text, **_):
        seed = sum(ord(c) for c in (text if isinstance(text, str) else text[0]))
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(384).astype("float32")
        return v / np.linalg.norm(v)
    m.encode = _encode
    m.get_sentence_embedding_dimension.return_value = 384
    return EmbeddingService(_model=m)


def _prefs() -> Prefs:
    return Prefs.model_validate(dict(
        titles=["Senior Backend Engineer", "Staff Engineer"],
        locations=["Remote - US", "Atlanta, GA"],
        remote_ok=True,
        comp_floor_usd=180000,
        exclude_keywords=["C++"],
        seniority=["senior", "staff"],
        greenhouse_companies=["acme"],
    ))


def _seed(db, n_pass=2, n_fail=1):
    base = dict(source="greenhouse", company="Acme",
                location="Remote - US", remote=True,
                posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC))
    for i in range(n_pass):
        upsert_job(db, RawJob(
            **base, external_id=f"acme:p{i}",
            title="Senior Backend Engineer",
            url=f"https://example.com/p{i}",
            description_md="Python services.",
        ))
    for i in range(n_fail):
        upsert_job(db, RawJob(
            **base, external_id=f"acme:f{i}",
            title="C++ Engineer",
            url=f"https://example.com/f{i}",
            description_md="Low-level work.",
        ))


def test_pipeline_filters_then_cosine_then_llm(tmp_path, fake_embedder):
    db = tmp_path / "db.sqlite"
    migrate(db)
    _seed(db, n_pass=2, n_fail=1)
    resume = tmp_path / "resume.md"
    resume.write_text("Senior backend engineer.")

    fake_anth = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text='[{"id": 1, "score": 88, "reason": "great match"}, '
                                  '{"id": 2, "score": 71, "reason": "ok match"}]')]
    msg.usage.input_tokens = 500
    msg.usage.output_tokens = 30
    fake_anth.messages.create.return_value = msg
    reranker = LLMReranker(client=fake_anth, model="claude-haiku-4-5-20251001")

    summary = run_pipeline(
        db, prefs=_prefs(), resume_path=resume,
        embedder=fake_embedder, reranker=reranker, top_k=5,
    )
    assert summary.filtered == 1
    assert summary.cosine_top_k >= 1
    assert summary.llm_scored == 2
    assert summary.cost_usd > 0

    jobs = list_jobs(db)
    scored = {j.title: j.score for j in jobs}
    assert scored["C++ Engineer"] == 0
    # Scored in {88, 71, 50, 70} depending on which jobs the LLM mapped.
    assert all(j.score is not None for j in jobs if j.title != "C++ Engineer")


def test_pipeline_no_llm_path(tmp_path, fake_embedder):
    db = tmp_path / "db.sqlite"
    migrate(db)
    _seed(db, n_pass=1, n_fail=0)
    resume = tmp_path / "resume.md"
    resume.write_text("Senior backend engineer.")
    summary = run_pipeline(
        db, prefs=_prefs(), resume_path=resume,
        embedder=fake_embedder, reranker=None, top_k=5,
    )
    assert summary.cost_usd == 0.0
    assert summary.llm_scored == 0
```

- [ ] **Step 3: Replace `rank` in `shortlist/cli.py`**

```python
from shortlist.config import load_config, load_prefs
from shortlist.ranker.embeddings import EmbeddingService
from shortlist.ranker.llm_rerank import LLMReranker
from shortlist.ranker.pipeline import run_pipeline


@app.command("rank")
def rank(
    top_k: int = typer.Option(30, "--top-k", help="Cosine pre-rank size."),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip Haiku rerank ($0)."),
) -> None:
    """Score stored jobs: hard filter → cosine top-K → Haiku rerank."""
    if not paths.prefs_path().exists() or not paths.config_path().exists():
        console.print("[red]error[/red] run `shortlist config init` first")
        raise typer.Exit(code=2)
    if not paths.db_path().exists():
        console.print("[red]error[/red] run `shortlist db init` first")
        raise typer.Exit(code=2)

    cfg = load_config(paths.config_path())
    prefs = load_prefs(paths.prefs_path())
    resume = cfg.paths.resume.expanduser()
    if not resume.exists():
        console.print(f"[red]error[/red] resume not found at {resume}")
        raise typer.Exit(code=2)

    embedder = EmbeddingService(model_name=cfg.ranker.embedding_model)

    reranker: LLMReranker | None = None
    if not no_llm:
        import os
        key = os.environ.get(cfg.anthropic.key_env_var, "")
        if not key:
            console.print(
                f"[yellow]{cfg.anthropic.key_env_var} not set — running with --no-llm[/yellow]"
            )
        else:
            from anthropic import Anthropic
            reranker = LLMReranker(
                client=Anthropic(api_key=key),
                model=cfg.ranker.rerank_model,
            )

    summary = run_pipeline(
        paths.db_path(), prefs=prefs, resume_path=resume,
        embedder=embedder, reranker=reranker, top_k=top_k,
    )
    console.print(
        f"ranked: filtered={summary.filtered}, cosine_top_k={summary.cosine_top_k}, "
        f"llm_scored={summary.llm_scored}, cost=${summary.cost_usd:.4f}"
    )
```

- [ ] **Step 4: Replace placeholder rank test**

In `tests/integration/test_cli.py`, delete the Plan-1 `test_rank_scores_passing_jobs_high_failing_low` (or rename it). Append:

```python
@respx.mock
def test_rank_no_llm_runs_pipeline(env, tmp_path, monkeypatch):
    cfg, data = env
    runner.invoke(app, ["config", "init"])
    (cfg / "prefs.yaml").write_text(
        (cfg / "prefs.yaml").read_text().replace(
            "greenhouse_companies: []",
            "greenhouse_companies:\n  - acme",
        )
    )
    resume = tmp_path / "resume.md"
    resume.write_text("Senior backend engineer with Python.")
    cfg_text = (cfg / "config.yaml").read_text().replace(
        "resume: ~/jobs/resume.md", f"resume: {resume}"
    )
    (cfg / "config.yaml").write_text(cfg_text)

    from unittest.mock import MagicMock
    import numpy as np
    fake = MagicMock()
    def _enc(t, **_):
        rng = np.random.default_rng(sum(ord(c) for c in (t if isinstance(t, str) else t[0])))
        v = rng.standard_normal(384).astype("float32")
        return v / np.linalg.norm(v)
    fake.encode = _enc

    import shortlist.ranker.embeddings as emb
    monkeypatch.setattr(emb, "_load_model", lambda *_a, **_k: fake)

    runner.invoke(app, ["db", "init"])
    payload = json.loads((FIXTURES / "greenhouse_acme_page1.json").read_text())
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        params={"content": "true"},
    ).mock(return_value=httpx.Response(200, json=payload))
    runner.invoke(app, ["fetch"])

    result = runner.invoke(app, ["rank", "--no-llm"])
    assert result.exit_code == 0, result.output
    assert "filtered=" in result.output
    assert "cost=$0.0000" in result.output
```

- [ ] **Step 5: Run + commit**

```bash
pytest -q
ruff check . && ruff format --check . && mypy shortlist
git add shortlist/ranker/pipeline.py shortlist/cli.py tests/integration/test_pipeline.py tests/integration/test_cli.py
git commit -m "feat(ranker): full pipeline (hard_filter → cosine → Haiku rerank) + CLI --no-llm"
```

Expected: ~3 new pass + most prior = ~88 total. (The deleted placeholder test reduces by 1.)

---

## Task 12: README updates

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README**

Replace the "Plan 1 of 6" section with:

```markdown
This is **Plan 2 of 6** (ATS expansion + LLM rerank). Cumulative status:

- ✅ Plan 1 (foundation): Greenhouse + SQLite + hard filter + CLI
- ✅ Plan 2 (this): Lever, Ashby, Workable, SmartRecruiters; embeddings via `sentence-transformers`; Haiku 4.5 rerank with budget guard
- ⏳ Plan 3: tailoring (resume + cover + notes via Sonnet 4.6) + status tracker
- ⏳ Plan 4: Textual TUI
- ⏳ Plan 5: scraped aggregators (Indeed, LinkedIn, Glassdoor) + Playwright
- ⏳ Plan 6: curated boards (HN/Wellfound/Otta/RemoteOK) + RSS + release polish
```

In "First run" section, append:

```markdown
shortlist rank --no-llm           # cheap mode, embeddings only
shortlist rank                    # full pipeline (requires ANTHROPIC_API_KEY)
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README updates for Plan 2 features"
```

---

## Task 13: Migrate plan into repo + final CI

**Files:**
- Create: `docs/plans/2026-04-29-shortlist-plan-2-ats-rerank.md`

- [ ] **Step 1: Copy plan**

```bash
cp /run/media/seraph/Win1Tb/dev/repos/digitalseraph/docs/superpowers/plans/2026-04-29-shortlist-plan-2-ats-rerank.md docs/plans/
```

- [ ] **Step 2: Final full-CI verification**

```bash
ruff check .
ruff format --check .
mypy shortlist
pytest --cov=shortlist --cov-report=term-missing --cov-fail-under=80
```

Expected: green; coverage ≥ 80% on `shortlist/`.

- [ ] **Step 3: Commit**

```bash
git add docs/plans/2026-04-29-shortlist-plan-2-ats-rerank.md
git commit -m "docs: import Plan 2 (ATS + LLM rerank) from monorepo"
```

- [ ] **Step 4: Push (manual, user step)**

```bash
git push
```

---

## Done definition (Plan 2)

- `shortlist fetch` pulls from any subset of {Greenhouse, Lever, Ashby, Workable, SmartRecruiters} configured in `prefs.yaml`.
- `shortlist rank --no-llm` runs hard filter + embedding pre-rank end-to-end against a real resume; produces stable scores.
- `shortlist rank` (with `ANTHROPIC_API_KEY`) runs the full pipeline; per-job scores are 0–100 with one-line reasons; total run cost recorded in `scoring_runs`.
- All tests pass; coverage ≥ 80% on `shortlist/`.
- 13 task commits + plan migration commit on top of Plan 1's 20 commits.

## Next plan trigger

Plan 3 begins on user request. Plan 3 scope: Sonnet 4.6 tailoring (resume.md + cover.md + notes.md per job, with no-fabrication system prompt), pandoc → PDF, status state machine + contacts + applications tables (3rd migration), CLI `tailor <id>` and `track <id> --status …`.

## Open questions for Plan 3 brainstorm

- Pandoc PDF backend: `weasyprint` (HTML) vs `pdflatex` (TeX). The Plan-1 spec mentions a `~/.config/shortlist/pdf-template.tex` — assumes `pdflatex`. Confirm before implementing.
- Resume base format: must be Markdown (already implied by `resume.md`)? Or accept PDF and OCR? Plan-3 will start with Markdown only.
- Contact CRUD UX: free-form via CLI prompts, or `--contact "name=…,email=…,role=…"` flags? TBD in Plan 3 design.
