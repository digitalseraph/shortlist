"""Sonnet tailor prompts. Strict no-fabrication guardrail in the system prompt."""

from __future__ import annotations

SYSTEM = (
    "You tailor a candidate's resume + write a cover letter + write interview "
    "notes for a single job posting. Three rules:\n"
    "1. NEVER fabricate. Do not invent jobs, dates, employers, degrees, "
    "certifications, projects, technologies, or numbers. Only use facts "
    "present in the supplied resume. If a JD asks for something the resume "
    "doesn't show, say so honestly in the cover letter or notes.\n"
    "2. You may reorder, rephrase, condense, and expand on what's in the "
    "resume. You may emphasize relevant experience and de-emphasize the rest.\n"
    "3. Output exactly three top-level sections in this order, each marked "
    "by an H1: `# RESUME`, `# COVER`, `# NOTES`. No content outside these "
    "three sections. No markdown fences around the whole output.\n"
)


def build_user_prompt(
    *,
    resume: str,
    prefs_summary: str,
    job_title: str,
    company: str,
    job_description: str,
    cover_paragraphs: int,
) -> str:
    return (
        f"# CANDIDATE RESUME\n\n{resume.strip()}\n\n"
        f"# PREFERENCES\n\n{prefs_summary.strip()}\n\n"
        f"# JOB POSTING\n\n"
        f"**Company:** {company}\n"
        f"**Title:** {job_title}\n\n"
        f"{job_description.strip()}\n\n"
        f"# YOUR TASK\n\n"
        f"Produce three sections — `# RESUME`, `# COVER`, `# NOTES` — per the "
        f"system instructions. The cover letter should be {cover_paragraphs} "
        f"paragraphs."
    )
