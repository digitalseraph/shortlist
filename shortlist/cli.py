"""Shortlist Typer CLI.

Subcommand groups:
  config  — view config + write defaults
  db      — init / status / backup
  fetch   — pull jobs from enabled sources
  rank    — apply hard filter (Plan 1) / LLM rerank (Plan 2)
  list    — print stored jobs
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime

import typer
from rich.console import Console

from shortlist import paths
from shortlist.store import db as store_db

app = typer.Typer(no_args_is_help=True, help="Shortlist — personal job search.")
console = Console()

# --- db subgroup ----------------------------------------------------------

db_app = typer.Typer(help="Database admin.")
app.add_typer(db_app, name="db")


@db_app.command("init")
def db_init() -> None:
    """Create the SQLite database and apply migrations."""
    target = paths.db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    store_db.migrate(target)
    console.print(f"[green]ok[/green] db at {target}")


@db_app.command("status")
def db_status() -> None:
    """Print schema version + db location."""
    target = paths.db_path()
    if not target.exists():
        console.print(f"db not present at {target}")
        console.print("schema version: 0")
        return
    version = store_db.current_version(target)
    console.print(f"db: {target}")
    console.print(f"schema version: {version}")


@db_app.command("backup")
def db_backup() -> None:
    """Copy the SQLite file to a timestamped backup."""
    src = paths.db_path()
    if not src.exists():
        console.print(f"[yellow]no db at {src}[/yellow]")
        raise typer.Exit(code=1)
    backup_dir = paths.data_dir() / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dst = backup_dir / f"db-{stamp}.sqlite"
    shutil.copy2(src, dst)
    console.print(f"[green]ok[/green] backup at {dst}")
