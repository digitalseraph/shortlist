"""Place-name suggestions for the settings page's location inputs."""

from __future__ import annotations

from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from shortlist import places

router = APIRouter()


@router.get("/places", response_class=HTMLResponse)
def place_options(q: str = "") -> HTMLResponse:
    """`<option>` elements for the shared `#place-options` datalist."""
    return HTMLResponse("".join(f'<option value="{escape(p)}">' for p in places.suggest(q)))
