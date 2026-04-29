"""Hard filter: deterministic disqualifier before any LLM scoring.

A job `passes` only if all of the following hold:
  - At least one preferred title matches as a case-insensitive substring of job.title.
  - At least one preferred seniority appears in job.title (case-insensitive).
  - No `exclude_keywords` appears (case-insensitive) in title or description.
  - Location is acceptable: `job.remote` and `prefs.remote_ok`, OR
    `job.location` substring-matches one of `prefs.locations`.
  - Compensation: if `job.comp_max` is known, it must be >= `prefs.comp_floor_usd`.
    Unknown compensation passes (ATS often omits it).
"""

from __future__ import annotations

from shortlist.config import Prefs
from shortlist.models import Job


def _ci_any(needles: list[str], haystack: str) -> bool:
    h = haystack.lower()
    return any(n.lower() in h for n in needles if n)


def passes(job: Job, prefs: Prefs) -> bool:
    title = job.title or ""
    desc = job.description_md or ""
    text = f"{title}\n{desc}"

    if _ci_any(prefs.exclude_keywords, text):
        return False

    if not _ci_any(prefs.titles, title):
        return False

    if not _ci_any(prefs.seniority, title):
        return False

    location_ok = (job.remote and prefs.remote_ok) or (
        job.location is not None and _ci_any(prefs.locations, job.location)
    )
    if not location_ok:
        return False

    return job.comp_max is None or job.comp_max >= prefs.comp_floor_usd
