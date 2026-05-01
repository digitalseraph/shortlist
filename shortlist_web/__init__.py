"""Shortlist web layer — FastAPI + HTMX frontend."""

from __future__ import annotations

from shortlist_web.app import create_app

__all__ = ["create_app", "run_web"]


def run_web(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Launch uvicorn with the Shortlist FastAPI app."""
    import uvicorn

    uvicorn.run(create_app(), host=host, port=port)
