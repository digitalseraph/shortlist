# Troubleshooting

## Scraped sources (Indeed, LinkedIn, Glassdoor, Wellfound, Otta)

### Why scraped sources are disabled by default

Indeed, LinkedIn, and Glassdoor aggressively detect headless browsers and will block or serve
CAPTCHAs after a small number of requests. When detected, the source is placed in a **24-hour
cooldown** recorded in the `sources` table (`cooldown_until` column). Fetches skip cooled
sources silently.

Wellfound and Otta are enabled by default but carry the same scraping risk.

**ATS APIs (Greenhouse, Lever, Ashby, Workable, SmartRecruiters) are the recommended primary
path.** They use public JSON APIs, pose no ban risk, and are faster.

### Enabling Indeed, LinkedIn, or Glassdoor

1. Set `enabled: true` in the relevant `sources:` block in `~/.config/shortlist/config.yaml`:

   ```yaml
   sources:
     indeed:   { enabled: true, rate_limit_rpm: 6 }
     linkedin: { enabled: true, rate_limit_rpm: 4 }
   ```

2. Add at least one query string to `~/.config/shortlist/prefs.yaml`:

   ```yaml
   indeed_queries:
     - "senior backend engineer"
   linkedin_queries:
     - "platform engineer remote"
   ```

3. Ensure Playwright's Chromium is installed:

   ```bash
   playwright install chromium
   ```

4. Run `shortlist fetch`. If a ban is detected you will see:

   ```
   [indeed] ban detected — cooldown until 2026-04-29T14:00:00Z
   ```

### Ban symptoms

- CAPTCHA page rendered instead of job listings
- HTTP 403 or redirect to a "verify you're human" page
- Empty results with no error (site returns a shell page with no listings)

When detected, the source auto-cools for 24 hours. Options:

- **Wait it out** — re-run `shortlist fetch` after the cooldown expires; the source retries
  automatically.
- **Rotate IP** — use a VPN or residential proxy, then manually clear the cooldown.
- **Clear manually** — if you are confident the block has lifted:

  ```bash
  shortlist sources clear-cooldown indeed
  ```

- **Check status** — see current cooldown state for all sources:

  ```bash
  shortlist sources status
  ```

### Selectors breaking

Scraped sources rely on site-specific HTML selectors that break when a site updates its markup.
If a scraper returns zero results without a ban error, the selectors may be stale. File a GitHub
issue at `github.com/digitalseraph/shortlist` with the site name and the error or empty-result
log output. In the meantime, disable the broken source and rely on ATS APIs. See
[architecture.md](architecture.md) "Extension points" for how to update or add a scraper.

---

## PDF rendering issues

### "PDF skipped" warning

```
WARNING: PDF skipped (resume): pandoc not found on PATH
```

`pandoc` is not installed or not on `PATH`. Install it:

- Arch / CachyOS: `sudo pacman -S pandoc`
- macOS: `brew install pandoc`

After installing, re-run `shortlist tailor <id>` — it will overwrite the output directory and
render the PDF.

### pdflatex not found

```
WARNING: PDF skipped (resume): pdflatex not found on PATH
```

- Arch / CachyOS: `sudo pacman -S texlive-core texlive-latex texlive-fontsrecommended`
- macOS: `brew install basictex`, then open a new terminal (BasicTeX modifies `PATH` via
  `/etc/paths.d/`). If `pdflatex` is still missing: `sudo tlmgr install collection-latex`

### LaTeX format file missing on Arch / CachyOS

```
ERROR: LaTeX Error: File 'article.cls' not found.
```

`texlive-core` alone is sometimes insufficient. Install the full latex collection:

```bash
sudo pacman -S texlive-core texlive-latex texlive-fontsrecommended
fmtutil-sys --all    # regenerate format files if needed
```

### PDF renders but looks wrong

The default LaTeX template is `shortlist/templates/pdf-template.tex` in the repo. Override it:

```yaml
# ~/.config/shortlist/config.yaml
paths:
  pdf_template: ~/.config/shortlist/my-template.tex
```

Copy `shortlist/templates/pdf-template.tex` and modify as needed.

---

## Anthropic API errors

### 401 Unauthorized

```
anthropic.AuthenticationError: 401 Unauthorized
```

The API key is not set or is invalid. Verify:

```bash
echo $ANTHROPIC_API_KEY    # should print sk-ant-...
```

If using `key_source: keyring` in `config.yaml`, ensure the key is stored under the service
name `shortlist` in your OS keyring.

### 429 Rate limited

```
anthropic.RateLimitError: 429 Too Many Requests
```

Shortlist retries up to 3 times with exponential backoff (2 s, 4 s, 8 s + jitter) via
`tenacity`. If all retries fail, the rank or tailor call aborts. Wait a minute and retry, or
reduce `ranker.top_k_for_llm_rerank` in `config.yaml` to send fewer candidates per batch.

### Budget cap reached

```
budget cap reached: daily_usd=5.00 (spent=5.03)
```

The daily or monthly budget cap was hit. Options:

- Wait for the cap to reset (daily resets at UTC midnight; monthly resets on the 1st).
- Raise the cap in `~/.config/shortlist/config.yaml`:

  ```yaml
  budget:
    daily_usd: 10.00
    monthly_usd: 100.00
  ```

- Use `shortlist rank --no-llm` to rank without any API cost.

---

## Embedding model first-run download

On the first `shortlist rank` call, `sentence-transformers` downloads `bge-small-en-v1.5`
(~90 MB) to `~/.cache/huggingface/`. This is a one-time download; subsequent runs load the
model from disk in a few seconds.

On a restricted network, pre-download the model manually:

```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"
```

---

## Test coverage caveats

The default `pytest -m "not browser and not live"` run deselects two test tiers:

- `browser`-marked tests — require a real Playwright Chromium session; not suitable for CI
- `live`-marked tests — hit real network APIs; gated by `RUN_LIVE=1` environment variable

These 10 tests are excluded from the reported 82.96% coverage figure. The full suite has 165
tests. To run the excluded tiers (requires network and a browser):

```bash
RUN_LIVE=1 pytest -m live
RUN_LIVE=1 pytest -m "browser and live"
```

---

## "There's no --apply flag" — by design

Shortlist does not auto-submit applications. The `shortlist track <id> --status applied` command
records that you applied, but the actual form submission happens on the company's careers page.
This is intentional: automated submissions violate most job boards' terms of service and produce
worse outcomes than a human-reviewed application. Auto-apply is explicitly out of scope for
v0.1.0 and is not planned.

---

## Getting help

Check source health and recent errors:

```bash
shortlist sources status

sqlite3 ~/.local/share/shortlist/db.sqlite \
  "SELECT type, payload_json, cost_usd, created_at \
   FROM events ORDER BY created_at DESC LIMIT 20"
```

File issues at `github.com/digitalseraph/shortlist` with error output, OS, and Python version.
