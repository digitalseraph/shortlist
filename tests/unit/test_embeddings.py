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
