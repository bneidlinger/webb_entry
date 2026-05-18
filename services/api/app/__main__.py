"""CLI entrypoint: `python -m app ...`

Subcommands:
  ingest mast    Pull JWST observations + products from MAST and upsert.
"""
from __future__ import annotations

import typer

from app.cli import ingest as ingest_cli

app = typer.Typer(help="WebbWatch AI CLI", no_args_is_help=True)
app.add_typer(ingest_cli.app, name="ingest", help="Data ingestion commands.")


if __name__ == "__main__":
    app()
