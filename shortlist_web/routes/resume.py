"""Resume upload, preview and editing.

Upload never writes `resume.md`. It extracts the text and hands it back for
review, because PDF extraction interleaves multi-column layouts and the only
other symptom would be quietly worse job scores - that text becomes the
embedding.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse

from shortlist.profiles import Profile
from shortlist.resume_import import MAX_RESUME_BYTES, UnsupportedResumeError, extract_text
from shortlist_web.routes._shared import get_env, page_context, profile_dep, toast

router = APIRouter()


def _render(request: Request, profile: Profile, text: str, note: str = "") -> HTMLResponse:
    html = (
        get_env(request)
        .get_template("resume.html")
        .render(**page_context(request, profile, text=text, note=note))
    )
    return HTMLResponse(html)


@router.get("/resume", response_class=HTMLResponse)
def resume_editor(request: Request, profile: Profile = Depends(profile_dep)) -> HTMLResponse:
    text = profile.resume_path.read_text() if profile.resume_path.exists() else ""
    return _render(request, profile, text)


@router.post("/resume/upload", response_class=HTMLResponse)
def upload_resume(
    request: Request,
    profile: Profile = Depends(profile_dep),
    file: UploadFile = File(...),
) -> HTMLResponse:
    """Extract and show the text. Writes nothing the pipeline reads until saved."""
    # Read at most one byte past the cap: extract_text's own size check is
    # its first line, before any parsing, so a too-large read already
    # triggers the same rejection without ever buffering the whole upload.
    data = file.file.read(MAX_RESUME_BYTES + 1)
    try:
        text = extract_text(data, file.filename or "")
    except UnsupportedResumeError as exc:
        return toast(request, str(exc), "error", code=400)
    # The uploaded filename is never used to build a path.
    profile.original_resume_path.parent.mkdir(parents=True, exist_ok=True)
    profile.original_resume_path.write_bytes(data)
    return _render(request, profile, text, note="Review the extracted text, then save.")


@router.post("/resume", response_class=HTMLResponse)
def save_resume(
    request: Request,
    profile: Profile = Depends(profile_dep),
    text: str = Form(...),
) -> HTMLResponse:
    profile.resume_path.parent.mkdir(parents=True, exist_ok=True)
    profile.resume_path.write_text(text)
    return _render(request, profile, text, note="Saved. The next rank will re-embed.")
