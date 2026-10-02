"""CLI entrypoint: `python -m app ...`

Subcommands:
  ingest mast    Pull JWST observations + products from MAST and upsert.
"""
from __future__ import annotations

import typer

from app.cli import ingest as ingest_cli
from app.cli import sample as sample_cli

app = typer.Typer(help="WebbWatch AI CLI", no_args_is_help=True)
app.add_typer(ingest_cli.app, name="ingest", help="Data ingestion commands.")
app.add_typer(sample_cli.app, name="sample", help="Bounded science runs and offline benchmarks.")


if __name__ == "__main__":
    app()
