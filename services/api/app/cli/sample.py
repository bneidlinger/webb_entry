"""Small, explicit test runs without Redis or AI services."""
from __future__ import annotations

import json

import typer

app = typer.Typer(no_args_is_help=True)


@app.command("run")
def run_sample(
    limit: int = typer.Option(3, min=1, max=100),
    max_file_mib: int = typer.Option(16, min=1, max=256),
    max_total_mib: int = typer.Option(32, min=1, max=1024),
) -> None:
    """Preview/analyze the smallest eligible catalog files, downloading each once.

    Ingest metadata first. No AI calls or outbound alerts are made by this command.
    Results and previews are saved in the configured database/storage.
    """
    from app.db import session_scope
    from app.services.samples import process_sample

    with session_scope() as session:
        result = process_sample(
            session, limit=limit, max_file_bytes=max_file_mib * 1024**2,
            max_total_bytes=max_total_mib * 1024**2,
        )
    typer.echo(json.dumps(result))
    if result["errors"]:
        raise typer.Exit(1)


@app.command("benchmark")
def benchmark(
    observations: int = typer.Option(10, min=1, max=10_000),
    products_per_observation: int = typer.Option(10, min=1, max=100),
) -> None:
    """Measure synthetic metadata ingest/replay in an isolated in-memory database."""
    from app.services.samples import benchmark_metadata

    typer.echo(json.dumps(benchmark_metadata(observations, products_per_observation)))
